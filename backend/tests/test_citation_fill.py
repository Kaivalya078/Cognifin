import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from generation.citation_fill import fill_figure_citations  # noqa: E402

CTX = [
    ("fin_1", "Revenue | Q | ₹240,893.0 crore | AR p.17"),
    ("chunk_7", "revenue from operations 2,40,893 for the year"),
    ("chunk_9", "gross NPA 1.24% of advances"),
]


def test_figure_gets_first_matching_passage():
    out, added = fill_figure_citations("Revenue was ₹2,40,893 crore.", CTX)
    assert "[fin_1]" in out
    assert added == ["fin_1"]


def test_chunk_when_no_fin():
    out, added = fill_figure_citations("Revenue was ₹2,40,893 crore.", CTX[1:])
    assert "[chunk_7]" in out
    assert added == ["chunk_7"]


def test_whole_number_only():
    text = "It rose 240 bps."
    out, added = fill_figure_citations(text, [("chunk_1", "code 2408930")])
    assert (out, added) == (text, [])


def test_rounding_one_way():
    out, added = fill_figure_citations("NPA was 1.2%.", CTX)
    assert "[chunk_9]" in out
    text = "NPA was 1.24%."
    assert fill_figure_citations(text, [("chunk_2", "NPA 1.2%")]) == (text, [])


def test_years_and_small_ints_ignored():
    text = "In FY2024 and 2023-24, 3 segments grew."
    ctx = [("chunk_1", "FY2024 2023-24 3 segments 2024 2023")]
    assert fill_figure_citations(text, ctx) == (text, [])


def test_existing_cite_untouched():
    for text in ("Revenue ₹2,40,893 crore [chunk_7].",
                 "Revenue ₹2,40,893 crore (chunk_7).",
                 "Revenue ₹2,40,893 crore [chunk_7, chunk_9]."):
        assert fill_figure_citations(text, CTX) == (text, [])


def test_table_row_marker_in_last_cell():
    text = "| Metric | FY24 |\n|---|---|\n| Revenue | 2,40,893 |"
    out, added = fill_figure_citations(text, CTX)
    assert out.splitlines() == ["| Metric | FY24 |", "|---|---|", "| Revenue | 2,40,893 [fin_1] |"]
    assert added == ["fin_1"]


def test_heading_and_refusal_untouched():
    for text in ("## Revenue 2,40,893", "Not available in the provided documents."):
        assert fill_figure_citations(text, CTX) == (text, [])


def test_at_most_two_markers_per_unit():
    ctx = [("chunk_1", "a 111.5"), ("chunk_2", "b 222.5"), ("chunk_3", "c 333.5")]
    out, added = fill_figure_citations("Values were 111.5, 222.5 and 333.5 overall.", ctx)
    assert added == ["chunk_1", "chunk_2"]
    assert out.count("[chunk_") == 2


def test_multi_sentence_line_fills_each_sentence():
    out, added = fill_figure_citations("Revenue was 2,40,893. NPA was 1.24%.", CTX)
    assert out == "Revenue was 2,40,893 [fin_1]. NPA was 1.24% [chunk_9]."
    assert added == ["fin_1", "chunk_9"]
