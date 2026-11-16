from core.retriever_pipeline import normalize_text


def test_normalize_keeps_single_newlines():
    assert normalize_text("a  b\nc") == "a b\nc"


def test_normalize_collapses_3plus_newlines():
    assert normalize_text("a\n\n\n\nb") == "a\n\nb"


def test_normalize_strips_nonprintable_and_trailing_space_per_line():
    assert normalize_text("x\x00y \t\nz") == "xy\nz"


# =============================================================================
# chunk_pdf (core/pdf_chunker.py)
# =============================================================================

import re

import pytest

from core.pdf_chunker import chunk_pdf
from tests.pdf_fixtures import make_pdf

HEADER = ["Particulars", "FY24", "FY23"]
TABLE = [HEADER, ["Revenue", "231456", "198234"], ["Other income", "5432", "4321"]]


def body(chunk):
    """Chunk text without its heading line."""
    return chunk.text.split("\n", 1)[1] if chunk.heading else chunk.text


def sentences(n, start=0):
    return " ".join(f"Sentence number {i} talks about steady growth in revenue." for i in range(start, start + n))


def test_table_becomes_markdown_with_header(tmp_path):
    pdf = make_pdf(tmp_path / "t.pdf", [[("heading", "Segment Revenue"), ("table", TABLE)]])
    tables = [c for c in chunk_pdf(pdf) if c.content_form == "tabular"]
    assert len(tables) == 1
    lines = body(tables[0]).splitlines()
    assert lines[0].startswith("|") and "Particulars" in lines[0]
    assert any("231456" in l and "198234" in l for l in lines)


def test_table_numbers_not_repeated_in_prose(tmp_path):
    pdf = make_pdf(tmp_path / "t.pdf", [[("para", "Intro paragraph about the year."), ("table", TABLE)]])
    assert sum("231456" in c.text for c in chunk_pdf(pdf)) == 1


def test_long_table_splits_on_rows_and_repeats_header(tmp_path):
    rows = [HEADER] + [[f"Line item {i}", str(1000 + i), str(900 + i)] for i in range(42)]
    pdf = make_pdf(tmp_path / "t.pdf", [[("table", rows)]])
    tables = [c for c in chunk_pdf(pdf, target=300) if c.content_form == "tabular"]
    assert len(tables) >= 2
    for c in tables:
        lines = body(c).splitlines()
        assert "Particulars" in lines[0]
        assert all(l.startswith("|") and l.endswith("|") for l in lines)  # no cut rows
        assert len(c.text) <= 1500
    items = [m for c in tables for m in re.findall(r"Line item (\d+)\|", c.text)]
    assert sorted(set(items), key=int) == [str(i) for i in range(42)]


def test_table_across_page_break(tmp_path):
    p2 = [HEADER, ["Finance cost", "777", "666"]]
    pdf = make_pdf(tmp_path / "t.pdf", [[("table", TABLE)], [("table", p2)]])
    tables = [c for c in chunk_pdf(pdf) if c.content_form == "tabular"]
    assert [c.page_number for c in tables] == [1, 2]
    assert all("Particulars" in body(c).splitlines()[0] for c in tables)


def test_prose_splits_on_sentences_with_one_sentence_overlap(tmp_path):
    pdf = make_pdf(tmp_path / "t.pdf", [[("para", sentences(50))]])
    chunks = chunk_pdf(pdf, target=400)
    assert len(chunks) >= 3
    for c in chunks:
        assert c.text.startswith("Sentence") and c.text.endswith(".")
    for a, b in zip(chunks, chunks[1:]):
        last = re.findall(r"Sentence number \d+ [^.]*\.", a.text)[-1]
        assert b.text.startswith(last)


def test_overlong_sentence_split_at_word_boundary(tmp_path):
    words = " ".join(f"word{i}" for i in range(450))  # ~3,500 chars, no full stop
    pdf = make_pdf(tmp_path / "t.pdf", [[("para", words)]])
    chunks = chunk_pdf(pdf)
    assert len(chunks) >= 3
    toks = []
    for c in chunks:
        assert len(c.text) <= 1500
        toks += c.text.split()
    assert all(re.fullmatch(r"word\d+", t) for t in toks)  # nothing cut mid-word
    assert {f"word{i}" for i in range(450)} <= set(toks)


def test_heading_prefix_and_carry_over(tmp_path):
    pdf = make_pdf(tmp_path / "t.pdf", [
        [("heading", "Segment Revenue"), ("para", sentences(3))],
        [("para", sentences(3, 10)), ("heading", "Risk Factors"), ("para", sentences(3, 20))],
    ])
    chunks = chunk_pdf(pdf)
    first_p2 = [c for c in chunks if c.page_number == 2][0]
    assert all(c.text.startswith("Segment Revenue\n") for c in chunks if c.page_number == 1)
    assert first_p2.heading == "Segment Revenue"
    assert chunks[-1].heading == "Risk Factors" and chunks[-1].text.startswith("Risk Factors\n")
    assert all("Sentence number 2 " not in c.text or c.page_number == 1 for c in chunks)


def test_chunk_never_spans_pages(tmp_path):
    pdf = make_pdf(tmp_path / "t.pdf", [[("para", sentences(4))], [("para", sentences(4, 100))]])
    for c in chunk_pdf(pdf):
        nums = {int(n) for n in re.findall(r"Sentence number (\d+)", c.text)}
        assert nums <= set(range(4)) or nums <= set(range(100, 104))


def test_blank_page_yields_no_chunks_and_keeps_numbering(tmp_path):
    pdf = make_pdf(tmp_path / "t.pdf", [[("para", sentences(2))], [], [("para", sentences(2, 50))]])
    assert {c.page_number for c in chunk_pdf(pdf)} == {1, 3}


def test_ids_are_sequential_and_forms_set(tmp_path):
    pdf = make_pdf(tmp_path / "t.pdf", [[("para", sentences(2)), ("table", TABLE)]])
    chunks = chunk_pdf(pdf)
    assert [c.chunk_id for c in chunks] == [f"chunk_{i}" for i in range(len(chunks))]
    assert {c.content_form for c in chunks} == {"narrative", "tabular"}


def test_dot_leaders_removed_from_cells(tmp_path):
    rows = [HEADER, ["Deposits ..........", "44.24", "41.77"],
            ["Loans ..............", "12.00", "10.50"]]
    pdf = make_pdf(tmp_path / "t.pdf", [[("table", rows)]])
    t = [c for c in chunk_pdf(pdf) if c.content_form == "tabular"][0]
    assert "...." not in t.text and "|Deposits|44.24|41.77|" in t.text


def test_running_header_and_footer_not_part_of_tables(tmp_path):
    import fitz
    path = make_pdf(tmp_path / "t.pdf", [[("table", TABLE[1:])]])  # no header row: data starts at once
    doc = fitz.open(path)
    page = doc[0]
    page.insert_text((50, 30), "ACME LTD.", fontsize=8)          # running header row:
    page.insert_text((300, 30), "443", fontsize=8)                # name ... page numbers
    page.insert_text((500, 30), "444", fontsize=8)
    page.insert_text((290, 830), "Annual Report 2024-25   12", fontsize=8)
    doc.save(str(tmp_path / "h.pdf"))
    t = [c for c in chunk_pdf(str(tmp_path / "h.pdf")) if c.content_form == "tabular"][0]
    assert "443" not in t.text and "ACME" not in t.text


def test_repeated_heading_text_not_stacked_twice(tmp_path):
    pdf = make_pdf(tmp_path / "t.pdf", [[("heading", "Board of Directors"), ("heading", "Board of Directors"),
                                         ("para", sentences(2))]])
    assert chunk_pdf(pdf)[0].heading == "Board of Directors"


# =============================================================================
# Ingestion wiring (RetrieverPipeline / CorpusManager)
# =============================================================================

def _three_page_pdf(tmp_path, name="r.pdf"):
    return make_pdf(tmp_path / name, [
        [("heading", "Directors Report"), ("para", sentences(3))],
        [("heading", "Segment Revenue"), ("table", TABLE)],
        [("para", sentences(3, 30))],
    ])


def _corpus():
    from core.corpus_manager import CorpusManager
    from core.retriever_pipeline import RetrieverPipeline
    return CorpusManager(RetrieverPipeline())


def test_cold_start_add_document_has_real_page_numbers(tmp_path):
    cm = _corpus()
    cm.add_document(_three_page_pdf(tmp_path), company="ACME", document_type="Annual_Report", year="2024")
    assert {m.page_number for m in cm.chunk_metadata.values()} == {1, 2, 3}


def test_metadata_gets_heading_and_content_form(tmp_path):
    cm = _corpus()
    cm.add_document(_three_page_pdf(tmp_path), company="ACME", document_type="Annual_Report", year="2024")
    tab = [m for m in cm.chunk_metadata.values() if m.content_form == "tabular"]
    assert len(tab) == 1 and tab[0].section_hint == "Segment Revenue" and tab[0].page_number == 2
    assert all(m.content_form == "narrative" for m in cm.chunk_metadata.values() if m not in tab)


def test_append_path_matches_cold_start_path(tmp_path):
    cm = _corpus()
    pdf = _three_page_pdf(tmp_path)
    cm.add_document(pdf, company="ACME", document_type="Annual_Report", year="2023")
    n = cm.retriever.index.ntotal
    cm.add_document(pdf, company="ACME", document_type="Annual_Report", year="2024")  # append path
    first = [(c.text, c.page_number) for c in cm.retriever.chunks[:n]]
    second = [(c.text, c.page_number) for c in cm.retriever.chunks[n:]]
    assert first == second
    assert [c.chunk_id for c in cm.retriever.chunks] == [f"chunk_{i}" for i in range(2 * n)]


def test_image_only_pdf_is_rejected(tmp_path):
    import fitz
    path = tmp_path / "img.pdf"
    doc = fitz.open(); doc.new_page(); doc.save(str(path))
    with pytest.raises(ValueError, match="no extractable text"):
        _corpus().add_document(str(path), company="ACME", document_type="Annual_Report", year="2024")


def test_embed_texts_returns_float32_from_fp16_model(monkeypatch):
    import numpy as np
    from core.retriever_pipeline import RetrieverPipeline
    p = RetrieverPipeline()
    monkeypatch.setattr(p.model, "encode", lambda texts, **_: np.ones((len(texts), 4), dtype=np.float16))
    out = p.embed_texts(["a", "b"])
    assert out.dtype == np.float32 and abs(float((out[0] ** 2).sum()) - 1.0) < 1e-5
