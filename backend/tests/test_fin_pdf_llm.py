import json
from datetime import date
from types import SimpleNamespace

from financials.pdf_llm import extract_llm
from financials.sources import Source

PAGES = {3: "Statement of Consolidated Results (Rs. in crore)\nRevenue from operations 1,234.50",
         9: "Notes to accounts: the board met on 12 July"}


class FakeClient:
    def __init__(self, items):
        self.calls, self.prompts = 0, []
        self.items = items
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.calls += 1
        self.prompts.append(json.dumps(kw["messages"]))
        assert kw["temperature"] == 0 and kw["response_format"] == {"type": "json_object"}
        content = json.dumps({"items": self.items})
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


ITEM = {"basis": "consolidated", "period_type": "Q", "metric": "revenue_from_operations",
        "printed": "1,234.50", "column_header": "Quarter ended 30.06.2025",
        "unit_header": "(Rs. in crore)", "page": 3}
WANT = [("consolidated", "Q", "revenue_from_operations")]


def _src(tmp_path):
    p = tmp_path / "r.pdf"
    p.write_bytes(b"x")
    return Source("TCS", date(2025, 6, 30), "PDF", None, p, "https://bse/x.pdf", "abc123")


def test_parses_fake_response(tmp_path):
    fake = FakeClient([ITEM])
    [c] = extract_llm(_src(tmp_path), {3: PAGES[3]}, WANT, tmp_path / "cache", client=fake)
    assert c.value == 1234.5e7 and c.method == "llm" and c.page == 3 and c.printed == "1,234.50"
    assert c.period_start == date(2025, 4, 1) and c.source_kind == "bse_pdf"


def test_cache_hit_skips_client(tmp_path):
    fake = FakeClient([ITEM])
    a = extract_llm(_src(tmp_path), {3: PAGES[3]}, WANT, tmp_path / "cache", client=fake)
    b = extract_llm(_src(tmp_path), {3: PAGES[3]}, WANT, tmp_path / "cache", client=fake)
    assert fake.calls == 1 and [c.value for c in a] == [c.value for c in b]


def test_unknown_metric_dropped(tmp_path):
    fake = FakeClient([dict(ITEM, metric="ebitda")])
    assert extract_llm(_src(tmp_path), {3: PAGES[3]}, WANT, tmp_path / "c", client=fake) == []


def test_missing_unit_header_dropped(tmp_path):
    fake = FakeClient([dict(ITEM, unit_header="")])
    assert extract_llm(_src(tmp_path), {3: PAGES[3]}, WANT, tmp_path / "c", client=fake) == []


def test_unwanted_or_bad_page_dropped(tmp_path):
    fake = FakeClient([dict(ITEM, metric="other_income"), dict(ITEM, page=7)])
    assert extract_llm(_src(tmp_path), {3: PAGES[3]}, WANT, tmp_path / "c", client=fake) == []


def test_only_statement_pages_sent(tmp_path):
    fake = FakeClient([ITEM])
    extract_llm(_src(tmp_path), {3: PAGES[3]}, WANT, tmp_path / "c", client=fake)
    assert "1,234.50" in fake.prompts[0] and "board met" not in fake.prompts[0]
