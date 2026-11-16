from core.retriever_pipeline import normalize_text


def test_normalize_keeps_single_newlines():
    assert normalize_text("a  b\nc") == "a b\nc"


def test_normalize_collapses_3plus_newlines():
    assert normalize_text("a\n\n\n\nb") == "a\n\nb"


def test_normalize_strips_nonprintable_and_trailing_space_per_line():
    assert normalize_text("x\x00y \t\nz") == "xy\nz"
