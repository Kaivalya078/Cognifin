from core.citation_verifier import verify_citations
from generation.prompt_builder import extract_citations

IDS = ["[expanded]chunk_12", "[TCS]:chunk_7", "chunk_3"]
ANSWER = "Revenue rose 7% [chunk_12]. Margins held at 24% (chunk_7). Costs fell sharply [chunk_3]."


def test_extract_citations_matches_prefixed_context_ids():
    assert extract_citations(ANSWER, IDS) == ["[expanded]chunk_12", "[TCS]:chunk_7", "chunk_3"]


def test_verify_citations_accepts_prefixed_context_ids():
    r = verify_citations(ANSWER, IDS)
    assert r["invalid_citations"] == [] and r["verified"] is True
    assert set(r["valid_citations"]) == {"chunk_12", "chunk_7", "chunk_3"}


def test_hallucinated_citation_still_flagged():
    r = verify_citations(ANSWER + " Also chunk_99 says so.", IDS)
    assert r["invalid_citations"] == ["chunk_99"]
    assert extract_citations("see chunk_99", IDS) == []
