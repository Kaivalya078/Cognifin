from datetime import date

import pytest

from financials.sources import import_scratch, load_sources, parse_manifest_date


def _scratch(tmp_path):
    xcache = tmp_path / "xcache"
    xcache.mkdir()
    (xcache / "INTEGRATED_FILING_BANKING_1_iXBRL_WEB.html").write_text("<html>x</html>")
    man = tmp_path / "manifest.csv"
    man.write_text("symbol,kind,basis,period_start,period_end,rounding,url\n"
                   "HDFCBANK,BANKING,Consolidated,01-01-2026,31-03-2026,,"
                   "https://nsearchives.nseindia.com/corporate/ixbrl/INTEGRATED_FILING_BANKING_1_iXBRL_WEB.html\n")
    res = tmp_path / "results"
    (res / "TCS").mkdir(parents=True)
    (res / "TCS" / "2025-06.pdf").write_bytes(b"%PDF-1.4 fake")
    links = res / "links.csv"
    links.write_text("TCS,6/2025,Pname=abc-123.pdf\n")
    return man, xcache, res, links


def test_import_and_load_roundtrip(tmp_path):
    out = tmp_path / "out"
    assert import_scratch(*_scratch(tmp_path), out) == 2
    srcs = sorted(load_sources(out), key=lambda s: s.symbol)
    assert [(s.symbol, s.kind, s.basis, s.period_end) for s in srcs] == [
        ("HDFCBANK", "BANKING", "consolidated", date(2026, 3, 31)),
        ("TCS", "PDF", None, date(2025, 6, 30)),
    ]
    assert srcs[1].url == "https://www.bseindia.com/xml-data/corpfiling/AttachHis/abc-123.pdf"
    assert srcs[0].path == out / "HDFCBANK" / "2026-03_consolidated.html"


def test_hash_mismatch_raises(tmp_path):
    out = tmp_path / "out"
    import_scratch(*_scratch(tmp_path), out)
    (out / "TCS" / "2025-06.pdf").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="2025-06.pdf"):
        load_sources(out)


def test_dates_both_formats():
    assert parse_manifest_date("31-03-2026") == date(2026, 3, 31)
    assert parse_manifest_date("31-Mar-2025") == date(2025, 3, 31)
