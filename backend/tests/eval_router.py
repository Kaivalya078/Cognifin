"""Phase 4 eval: numeric router accuracy, and end-to-end chart/citation checks.

Part 1 (no LLM):  venv/Scripts/python.exe tests/eval_router.py
Part 2 (needs a running backend with an LLM key):
                  venv/Scripts/python.exe tests/eval_router.py --e2e [--api http://localhost:8000]
"""
import argparse
import json
import sys
import urllib.request
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from financials.query import get_metric  # noqa: E402
from financials.router import route  # noqa: E402
from query.query_understanding import extract_years  # noqa: E402

CASES = json.loads((BACKEND / "tests" / "router_golden.json").read_text(encoding="utf-8"))
DIV = {"INR": 1e7}


def judge(case, lk) -> str:
    """'' if the route matches the expectation, else a short reason."""
    exp = case["expect"]
    if exp is None:
        return "" if lk is None else f"expected miss, got {[(s.company, s.metric) for s in lk.series]}"
    if lk is None:
        return "expected hit, got None"
    got = {s.company: s.metric for s in lk.series}
    if got != exp["metrics"]:
        return f"metrics {got} != {exp['metrics']}"
    if lk.period.period_type != exp["period_type"]:
        return f"period_type {lk.period.period_type}"
    n = sum(len(s.rows) for s in lk.series)
    if "n_rows" in exp and n != exp["n_rows"]:
        return f"n_rows {n} != {exp['n_rows']}"
    if "basis" in exp and {s.basis for s in lk.series} != {exp["basis"]}:
        return f"basis {[s.basis for s in lk.series]}"
    return ""


def part1() -> None:
    fails, hits = [], 0
    for case in CASES:
        lk = route(case["q"], case["companies"], extract_years(case["q"])[0])
        hits += lk is not None
        if why := judge(case, lk):
            fails.append((case["q"], why))
    print(f"| Router (no LLM) | {len(CASES)} cases | hit rate {hits}/{len(CASES)} | "
          f"exact match {len(CASES) - len(fails)}/{len(CASES)} ({100 * (len(CASES) - len(fails)) / len(CASES):.0f}%) |")
    for q, why in fails:
        print(f"  MISS  {q!r}: {why}")


def _ask(api: str, q: str) -> dict:
    req = urllib.request.Request(f"{api}/chat", data=json.dumps({"question": q}).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=240) as r:
        return json.loads(r.read())


def chart_mismatches(chart: dict, period_type: str) -> list[str]:
    bad = []
    for s in chart["series"]:
        rows = {r.period_end.isoformat(): r for r in get_metric(s["company"], s["metric"], s["basis"], period_type)}
        for p in s["points"]:
            r = rows.get(p["period_end"])
            if r is None or p["value"] != r.value / DIV.get(r.unit, 1):
                bad.append(f"{s['company']} {p['period_end']} {p['value']}")
    return bad


def part2(api: str) -> None:
    print("\n| Question | Router | Chart points | Chart ≠ DB | Numbers checked | Unmatched | All companies cited |")
    print("|---|---|---|---|---|---|---|")
    total_bad = total_unmatched = 0
    for case in (c for c in CASES if c.get("e2e")):
        d = _ask(api, case["q"])
        m = d["metadata"]
        hit = m.get("router", {}).get("hit", False)
        chart, nc = m.get("chart"), m.get("numbers_check") or {}
        bad = chart_mismatches(chart, chart["period_type"]) if chart else []
        unmatched = nc.get("unmatched", [])
        total_bad += len(bad)
        total_unmatched += len(unmatched)
        cited = set(d["citations"])
        covered = all(any(cid in cited and (e["snippet"].split(" | ")[0].endswith(co) if cid.startswith("fin_")
                                             else co in (e.get("document_label") or ""))
                          for e in d["evidence"] for cid in [e["chunk_id"]])
                      for co in case["companies"]) if len(case["companies"]) > 1 else None
        expect_hit = case["expect"] is not None
        router = ("hit" if hit else "miss") + ("" if hit == expect_hit else " ✗")
        npts = sum(len(s["points"]) for s in chart["series"]) if chart else 0
        print(f"| {case['q']} | {router} | {npts} | {len(bad)} | {nc.get('checked', '-')} | "
              f"{', '.join(unmatched) or 0} | {'-' if covered is None else ('yes' if covered else 'NO')} |")
    print(f"\nChart values not equal to the DB: {total_bad}. Unmatched answer numbers: {total_unmatched}.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--e2e", action="store_true")
    ap.add_argument("--api", default="http://localhost:8000")
    a = ap.parse_args()
    part1()
    if a.e2e:
        part2(a.api)
