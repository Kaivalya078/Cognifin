"""Precision / coverage of financials.duckdb against the hand-checked answer key.

    python -m tests.eval_financials --db index_cache/financials.duckdb --label v1

Precision = stored values matching the key / key values that are stored.
Coverage  = key values that are stored / all key values.
A match is within one rounding unit: Rs 1 lakh (or 0.01% of the value, if larger) for
amounts, 0.006 for EPS, percentages and ratios (printed to 2 decimals).
"""
import argparse
import json
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

import duckdb

from financials.metrics import METRICS

HERE = Path(__file__).parent


def _tol(metric: str, key: float) -> float:
    return max(1e5, abs(key) * 1e-4) if METRICS[metric][1] == "INR" else 0.006


def evaluate(db: str, key_path: Path = HERE / "financials_golden.json") -> dict:
    key = json.loads(Path(key_path).read_text())
    con = duckdb.connect(db, read_only=True)
    tallies = defaultdict(lambda: {"total": 0, "stored": 0, "correct": 0})
    misses, wrong = [], []
    for case in key["cases"]:
        for metric, want in case["values"].items():
            row = con.execute(
                "SELECT value, method FROM financials WHERE company=? AND basis=? AND period_type=? "
                "AND period_end=? AND metric=?",
                [case["company"], case["basis"], case["period_type"],
                 date.fromisoformat(case["period_end"]), metric]).fetchone()
            group = METRICS[metric][0]
            kinds = ["overall", f"group:{group}",
                     "source:ixbrl" if case["source_file"].endswith(".html") else "source:pdf"]
            if row:
                kinds.append(f"method:{row[1]}")
            ok = bool(row) and abs(row[0] - want) <= _tol(metric, want)
            for k in kinds:
                t = tallies[k]
                t["total"] += 1
                t["stored"] += bool(row)
                t["correct"] += ok
            if not row:
                misses.append((case["id"], metric))
            elif not ok:
                wrong.append((case["id"], metric, row[1], row[0], want))
    con.close()
    report = {}
    for k, t in sorted(tallies.items()):
        report[k] = dict(t, precision=t["correct"] / t["stored"] if t["stored"] else None,
                         coverage=t["stored"] / t["total"])
    return {"report": report, "wrong": wrong, "missing": misses}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="index_cache/financials.duckdb")
    ap.add_argument("--label", default="run")
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
    print(f"report: {out}")


if __name__ == "__main__":
    main()
