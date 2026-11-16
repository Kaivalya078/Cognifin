"""Canonical metric vocabulary: name -> (group, unit)."""

_ALL = {
    "revenue_from_operations": "INR", "other_income": "INR", "total_income": "INR",
    "total_expenses": "INR", "profit_before_tax": "INR", "tax_expense": "INR",
    "net_profit": "INR", "net_profit_owners": "INR",
    "eps_basic": "INR_per_share", "eps_diluted": "INR_per_share",
}
_BANK = {
    "interest_earned": "INR", "gross_npa_pct": "pct", "net_npa_pct": "pct",
    "capital_adequacy_pct": "pct", "cet1_pct": "pct", "return_on_assets_pct": "pct",
}
_INSURER = {
    "gross_premium": "INR", "net_premium": "INR", "first_year_premium": "INR",
    "renewal_premium": "INR", "single_premium": "INR", "solvency_ratio": "ratio",
}

METRICS: dict[str, tuple[str, str]] = {
    **{m: ("all", u) for m, u in _ALL.items()},
    **{m: ("bank", u) for m, u in _BANK.items()},
    **{m: ("insurer", u) for m, u in _INSURER.items()},
}


def metrics_for(kind: str) -> list[str]:
    """Metrics expected for a filing kind (INDAS, NBFC_INDAS, BANKING, LI)."""
    base = list(_ALL)
    if kind == "BANKING":
        return [m for m in base if m != "revenue_from_operations"] + list(_BANK)
    if kind == "LI":
        return base + list(_INSURER)
    return base
