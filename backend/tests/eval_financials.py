"""Precision / coverage of financials.duckdb against the hand-checked answer key.

    python -m tests.eval_financials --db index_cache/financials.duckdb --label v1

Precision = stored values matching the key / key values that are stored.
Coverage  = key values that are stored / all key values.
A match is within one rounding unit of the stored value as printed: "1,234.56" in crore
allows Rs 1 lakh, "4,082" in millions Rs 10 lakh. Values with no printed text: 0.006.
"""
import argparse
import json
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

import duckdb

from financials.metrics import METRICS
from financials.numbers import parse_number

HERE = Path(__file__).parent


def _tol(value: float, printed: str | None) -> float:
    """One unit of the last printed digit, scaled by the unit the value was stored in."""
    num = parse_number(printed or "")
    if not num:
        return 0.006
    decimals = len(printed.split(".")[1].rstrip(")")) if "." in printed else 0
    return abs(value / num) * 10 ** -decimals * 1.0001   # 1.0001: float slack


def evaluate(db: str, key_path: Path = HERE / "financials_golden.json") -> dict:
    key = json.loads(Path(key_path).read_text())
    con = duckdb.connect(db, read_only=True)
    tallies = defaultdict(lambda: {"total": 0, "stored": 0, "correct": 0})
    misses, wrong = [], []
    for case in key["cases"]:
        for metric, want in case["values"].items():
            row = con.execute(
                "SELECT value, method, printed FROM financials WHERE company=? AND basis=? AND period_type=? "
                "AND period_end=? AND metric=?",
                [case["company"], case["basis"], case["period_type"],
                 date.fromisoformat(case["period_end"]), metric]).fetchone()
            group = METRICS[metric][0]
            kinds = ["overall", f"group:{group}",
                     "source:ixbrl" if case["source_file"].endswith(".html") else "source:pdf"]
            if row:
                kinds.append(f"method:{row[1]}")
            ok = bool(row) and abs(row[0] - want) <= _tol(row[0], row[2])
            for k in kinds:
                t = tallies[k]
                t["total"] += 1
                t["stored"] += bool(row)
                t["correct"] += ok
            if not row:
                misses.append((case["id"], metric))
            elif not ok:
                wrong.append((case["id"], metric, row[1], row[0], want))
    # corpus-wide, beyond the key: one printed figure stored as two metrics of one
    # filing/period is a label misread (basic = diluted EPS, and net profit = owners' share
    # with no minority, are normal)
    suspects = con.execute("""
        SELECT a.company, a.basis, a.period_type, a.period_end, a.printed, a.metric, a.method,
               b.metric, b.method
        FROM financials a JOIN financials b USING (company, basis, period_type, period_end,
                                                   source_file, printed)
        WHERE a.metric < b.metric AND a.unit = b.unit
          AND a.value <> 0
          AND NOT (a.metric = 'eps_basic' AND b.metric = 'eps_diluted')
          AND NOT (a.metric = 'net_profit' AND b.metric = 'net_profit_owners')
        ORDER BY 1, 4""").fetchall()
    con.close()
    report = {}
    for k, t in sorted(tallies.items()):
        report[k] = dict(t, precision=t["correct"] / t["stored"] if t["stored"] else None,
                         coverage=t["stored"] / t["total"])
    return {"report": report, "wrong": wrong, "missing": misses, "suspects": suspects}


def gate_failures(report: dict, min_precision: float, min_coverage: float) -> list[str]:
    """CI gate: overall precision/coverage below the given percents, compared as printed (0.1%)."""
    o, fails = report["overall"], []
    if round(100 * (o["precision"] or 0), 1) < min_precision:
        fails.append(f"precision {o['precision']:.1%} < {min_precision}%")
    if round(100 * o["coverage"], 1) < min_coverage:
        fails.append(f"coverage {o['coverage']:.1%} < {min_coverage}%")
    return fails


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="index_cache/financials.duckdb")
    ap.add_argument("--label", default="run")
    ap.add_argument("--min-precision", type=float, help="fail below this overall precision (%%)")
    ap.add_argument("--min-coverage", type=float, help="fail below this overall coverage (%%)")
    a = ap.parse_args()
    res = evaluate(a.db)
    out = HERE / "eval_reports" / f"{datetime.now():%Y%m%d-%H%M%S}-{a.label}-financials.json"
    out.write_text(json.dumps(res, indent=1, default=str))
    print(f"{'slice':<16}{'values':>7}{'stored':>7}{'right':>7}{'precision':>10}{'coverage':>9}")
    for k, t in res["report"].items():
        p = "-" if t["precision"] is None else f"{t['precision']:.1%}"
        print(f"{k:<16}{t['total']:>7}{t['stored']:>7}{t['correct']:>7}{p:>10}{t['coverage']:>9.1%}")
    for w in res["wrong"]:
        print("WRONG", *w)
    for s in res["suspects"]:
        print("SUSPECT", *s)
    print(f"report: {out}")
    if a.min_precision is not None or a.min_coverage is not None:
        fails = gate_failures(res["report"], a.min_precision or 0, a.min_coverage or 0)
        for f in fails:
            print("GATE FAILED:", f)
        sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
