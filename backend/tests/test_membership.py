"""NIFTY 100 membership snapshot (data/nifty100.csv) and company-name detection over it."""
import csv
from pathlib import Path

import pytest

from query.company_aliases import COMPANY_ALIASES
from query.query_understanding import detect_companies

SNAPSHOT = Path(__file__).resolve().parent.parent / "data" / "nifty100.csv"


def load():
    with open(SNAPSHOT, encoding="utf-8") as f:
        return list(csv.DictReader(f))


SYMBOLS = [r["symbol"] for r in load()] + ["TMPV"]  # TMPV: indexed, left the NIFTY 100

NEAR_DUPES = [
    ("What was Bajaj Holdings' net profit in FY2025?", "BAJAJHLDNG"),
    ("Bajaj Finance loan book growth", "BAJFINANCE"),
    ("Tata Power renewable capacity in FY2026", "TATAPOWER"),
    ("Adani Green Energy operational capacity", "ADANIGREEN"),
    ("Adani Power revenue", "ADANIPOWER"),
    ("Siemens Energy India order book", "ENRIN"),
    ("Siemens revenue from operations", "SIEMENS"),
    ("Vedanta Aluminium production volume", "VAML"),
    ("Hindustan Zinc dividend", "HINDZINC"),
    ("Hindustan Aeronautics order book", "HAL"),
    ("Power Finance Corporation net interest income", "PFC"),
    ("Tata Motors Commercial Vehicles revenue", "TMCV"),
    ("Tata Motors revenue in FY2024", "TMPV"),
    ("Vodafone Idea subscriber base", "IDEA"),
    ("BSE Ltd transaction revenue", "BSE"),
]

# Symbols that are also ordinary words or another entity's name never match bare.
NOT_A_COMPANY = [
    ("Any idea what TCS reported as revenue?", ["TCS"]),
    ("Infosys results as filed on BSE", ["INFY"]),
]


def test_snapshot_has_100_unique_symbols():
    rows = load()
    assert len(rows) == 100
    assert len({r["symbol"] for r in rows}) == 100
    assert sum(r["index"] == "NIFTY Next 50" for r in rows) == 50


def test_every_member_has_aliases():
    missing = [r["symbol"] for r in load() if r["symbol"] not in COMPANY_ALIASES]
    assert missing == []


@pytest.mark.parametrize("q,sym", NEAR_DUPES)
def test_near_duplicate_names_resolve(q, sym):
    assert detect_companies(q, SYMBOLS)[0] == [sym]


@pytest.mark.parametrize("q,expected", NOT_A_COMPANY)
def test_word_like_symbols_do_not_match_bare(q, expected):
    assert detect_companies(q, SYMBOLS)[0] == expected
