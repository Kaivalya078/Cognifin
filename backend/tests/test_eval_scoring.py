from types import SimpleNamespace

from core.metadata_schema import RetrievalResult
from tests.eval_retrieval import chunk_location, score_case, summarize

CASE = {"id": "x", "kind": "table", "company": "TCS", "year": "2024", "answer_pages": [12, 13]}


def meta(company, year, page):
    return SimpleNamespace(company=company, year=year, page_number=page)


def r(vid):
    return RetrievalResult(chunk_id=f"chunk_{vid}", score=0.5, snippet="")


def test_hit_requires_company_year_and_page():
    md = {1: meta("TCS", "2023", 12)}  # right page, wrong year
    row = score_case(CASE, [r(1)], [r(1)], md)
    assert not row["hit3"] and not row["hit8"] and row["rr"] == 0.0


def test_hit3_vs_hit8():
    md = {i: meta("TCS", "2024", 99) for i in range(8)}
    md[4] = meta("TCS", "2024", 13)  # rank 5
    final = [r(i) for i in range(8)]
    row = score_case(CASE, final, final, md)
    assert row["hit3"] is False and row["hit8"] is True
    assert row["rr"] == 0.2


def test_expanded_chunk_id_is_scored():
    md = {7: meta("TCS", "2024", 12)}
    assert chunk_location("[expanded]chunk_7", md) == ("TCS", "2024", 12)
    hit = RetrievalResult(chunk_id="[expanded]chunk_7", score=1, snippet="")
    assert score_case(CASE, [hit], [hit], md)["hit3"] is True


def test_recall60_uses_candidates_not_final():
    md = {1: meta("TCS", "2024", 12), 2: meta("INFY", "2024", 12)}
    row = score_case(CASE, [r(2), r(1)], [r(2)], md)
    assert row["recall60"] is True and row["hit8"] is False


def test_summarize_splits_by_kind_and_reports_p95():
    rows = [
        {"id": "a", "kind": "table", "hit3": True, "hit8": True, "rr": 1.0, "recall60": True},
        {"id": "b", "kind": "table", "hit3": False, "hit8": False, "rr": 0.0, "recall60": True},
        {"id": "c", "kind": "narrative", "hit3": False, "hit8": True, "rr": 0.25, "recall60": True},
    ]
    s = summarize(rows, [100.0] * 19 + [1000.0])
    assert s["overall"]["n"] == 3 and abs(s["overall"]["hit8"] - 2 / 3) < 1e-9
    assert s["by_kind"]["table"]["hit3"] == 0.5
    assert s["by_kind"]["narrative"]["mrr"] == 0.25
    assert s["latency_ms"]["p50"] == 100.0 and s["latency_ms"]["p95"] >= 100.0


def test_threshold_recalibration_maps_same_percentile():
    from tests.calibrate_thresholds import percentile_rank, value_at_rank
    old = [0.1, 0.2, 0.3, 0.4]          # threshold 0.25 → half the scores below it
    new = [0.6, 0.7, 0.8, 0.9]
    rank = percentile_rank(old, 0.25)
    assert rank == 0.5
    assert 0.7 <= value_at_rank(new, rank) <= 0.8
    assert value_at_rank(new, 1.0) > 0.9   # a threshold nothing reached stays unreached


def test_page_map_overrides_metadata_page():
    md = {7: meta("TCS", "2024", 1)}  # legacy index: every page_number is 1
    assert chunk_location("chunk_7", md, page_map={7: 12}) == ("TCS", "2024", 12)


def test_legacy_page_lookup_by_start_offset():
    from tests.legacy_page_map import page_of, page_starts
    pages = ["alpha beta", "", "gamma", "delta"]      # page 2 is blank
    full, starts = page_starts(pages)
    assert full == "alpha beta gamma delta"
    assert page_of(starts, full.index("gamma")) == 3
    assert page_of(starts, full.index("beta")) == 1
    assert page_of(starts, full.index("delta")) == 4
