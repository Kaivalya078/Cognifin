import csv
import hashlib
import json
import shutil
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import duckdb

from financials.build import build
from tests.test_fin_pdf_rules import BODY, _head, _pdf

FIX = Path(__file__).parent / "fixtures" / "financials"


class FakeClient:
    def __init__(self, items):
        self.calls, self.items = 0, items
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.calls += 1
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            content=json.dumps({"items": self.items})))])


def _corpus(tmp_path, other_income_printed="10.50"):
    root = tmp_path / "q"
    rows = []

    def add(sym, end, kind, basis, rel, src_path):
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src_path, dst)
        rows.append([sym, end, kind, basis, rel, f"https://x/{rel}",
                     hashlib.sha256(dst.read_bytes()).hexdigest()])

    add("TATASTEEL", "2025-06-30", "INDAS", "consolidated", "TATASTEEL/2025-06_consolidated.html",
        FIX / "indas_q1.html")
    add("TCS", "2025-06-30", "PDF", "", "TCS/2025-06.pdf", _pdf(tmp_path, [_head() + BODY], "a.pdf").path)
    # "Other revenue" is not a rule label -> other_income must come from the LLM
    body = [[(c, t.replace("2 Other income", "2 Other revenue")) for c, t in r] for r in BODY]
    add("INFY", "2025-06-30", "PDF", "", "INFY/2025-06.pdf", _pdf(tmp_path, [_head() + body], "b.pdf").path)
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"not a pdf")
    add("WIPRO", "2025-06-30", "PDF", "", "WIPRO/2025-06.pdf", bad)
    with open(root / "sources.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["symbol", "period_end", "kind", "basis", "file", "url", "sha256"])
        w.writerows(rows)
    item = {"basis": "consolidated", "period_type": "Q", "metric": "other_income",
            "printed": other_income_printed, "column_header": "Quarter ended 30.06.2025",
            "unit_header": "(Rs. in crore, except per share data)", "page": 1}
    return root, FakeClient([item])


def _db(p):
    return duckdb.connect(str(p), read_only=True)


def test_build_fixture_corpus(tmp_path):
    root, fake = _corpus(tmp_path)
    out = tmp_path / "f.duckdb"
    s = build(root, out, client=fake, cache_dir=tmp_path / "cache")
    assert s["files"] == 4 and s["rows"] > 0 and s["llm_calls"] >= 1
    con = _db(out)
    assert con.execute("SELECT method, value FROM financials WHERE company='INFY' AND metric='other_income'"
                       ).fetchall() == [("llm", 10.5e7)]
    assert con.execute("SELECT method FROM financials WHERE company='TCS' AND metric='revenue_from_operations'"
                       ).fetchall() == [("rule",)]
    assert con.execute("SELECT count(*) FROM financials WHERE company='TATASTEEL'").fetchone()[0] >= 6
    statuses = dict(con.execute("SELECT symbol, status FROM filings").fetchall())
    assert statuses["TCS"] == "parsed" and statuses["TATASTEEL"] == "parsed"
    con.close()   # Windows cannot replace a file that is open
    # a second build reuses the cached LLM answer
    s2 = build(root, out, client=fake, cache_dir=tmp_path / "cache")
    assert s2["llm_calls"] == 0 and s2["llm_cached"] >= 1 and s2["rows"] == s["rows"]


def test_llm_value_failing_verbatim_goes_to_review(tmp_path):
    root, fake = _corpus(tmp_path, other_income_printed="99.99")
    out = tmp_path / "f.duckdb"
    build(root, out, client=fake, cache_dir=tmp_path / "cache")
    con = _db(out)
    assert con.execute("SELECT count(*) FROM financials WHERE company='INFY' AND metric='other_income'"
                       ).fetchone()[0] == 0
    [(reason, method)] = con.execute(
        "SELECT reason, method FROM review WHERE company='INFY' AND metric='other_income'").fetchall()
    assert reason.startswith("verbatim") and method == "llm"


def test_broken_file_is_failed_not_fatal(tmp_path):
    root, fake = _corpus(tmp_path)
    s = build(root, tmp_path / "f.duckdb", client=fake, cache_dir=tmp_path / "cache")
    assert s["failed"] == 1
    con = _db(tmp_path / "f.duckdb")
    [(status, reason)] = con.execute("SELECT status, reason FROM filings WHERE symbol='WIPRO'").fetchall()
    assert status == "failed" and reason


def test_no_llm_flag(tmp_path):
    root, fake = _corpus(tmp_path)
    s = build(root, tmp_path / "f.duckdb", use_llm=False, client=fake, cache_dir=tmp_path / "cache")
    assert fake.calls == 0 and s["llm_calls"] == 0


def _cand(metric, value, printed, basis="standalone"):
    from financials.store import Candidate
    return Candidate("NTPC", basis, "Q", date(2025, 4, 1), date(2025, 6, 30), metric, value,
                     "INR" if metric != "solvency_ratio" else "ratio", printed, 3, "rule",
                     "bse_pdf", "NTPC/2025-06.pdf", "https://x", None)


def test_solvency_percent_stored_as_times():
    from financials.build import normalise
    assert normalise(_cand("solvency_ratio", 180.0, "180.00")).value == 1.8
    assert normalise(_cand("solvency_ratio", 1.97, "1.97")).value == 1.97


def test_regulatory_deferral_skips_pbt_minus_tax_rule():
    from financials.build import _check_pdf
    # NTPC: net profit = PBT - tax + deferral movement, so PBT - tax != net profit
    g = [_cand("profit_before_tax", 4336.74e7, "4336.74"), _cand("tax_expense", 821.04e7, "821.04"),
         _cand("net_profit", 4774.68e7, "4774.68")]
    page = ("Profit before tax and regulatory deferral account balances 4336.74 Tax 821.04 "
            "Net movement in regulatory deferral account balances 1258.98 Profit 4774.68")
    keep, bad = _check_pdf(g, {3: page})
    assert len(keep) == 3 and not bad


def test_llm_asked_for_basis_the_rules_missed(tmp_path):
    """Standalone page laid out by rules; the consolidated page states its unit only in a
    footnote, so only the LLM can read it. It must still be asked for consolidated."""
    root = tmp_path / "q"
    (root / "TCS").mkdir(parents=True)
    src = _pdf(tmp_path, [_head("Standalone") + BODY, _head("Consolidated", unit=None) + BODY + [[(0, "Note: all amounts in Rs. crore")]]], "s.pdf")
    shutil.copyfile(src.path, root / "TCS" / "2025-06.pdf")
    with open(root / "sources.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["symbol", "period_end", "kind", "basis", "file", "url", "sha256"])
        w.writerow(["TCS", "2025-06-30", "PDF", "", "TCS/2025-06.pdf", "https://x",
                    hashlib.sha256((root / "TCS" / "2025-06.pdf").read_bytes()).hexdigest()])
    item = {"basis": "consolidated", "period_type": "Q", "metric": "other_income", "printed": "10.50",
            "column_header": "30.06.2025", "unit_header": "(Rs. in crore)", "page": 2}
    build(root, tmp_path / "f.duckdb", client=FakeClient([item]), cache_dir=tmp_path / "c")
    with _db(tmp_path / "f.duckdb") as con:
        assert con.execute("SELECT count(*) FROM financials WHERE basis='consolidated'").fetchone()[0] == 1


def test_llm_value_on_other_sent_page_is_moved_there():
    from financials.build import _check_pdf
    c = _cand("profit_before_tax", 486.21e7, "486.21")
    c.method = "llm"
    keep, bad = _check_pdf([c], {21: "PBT 485.94", 22: "Profit before tax 486.21"})
    assert not bad and keep[0].page == 22


def test_solvency_fraction_and_impossible_values():
    from financials.build import normalise
    from financials.checks import check_ratio
    assert normalise(_cand("solvency_ratio", 0.0196, "0.0196")).value == 1.96
    assert check_ratio(normalise(_cand("solvency_ratio", 14500.0, "14,500")))
    assert check_ratio(normalise(_cand("solvency_ratio", 194.0, "194%"))) is None
