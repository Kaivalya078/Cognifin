from financials.present import build_chart, finish, fmt_value, prepare


def test_fmt_value():
    assert fmt_value(12209900000.0, "INR") == "₹1,221.0 crore"
    assert fmt_value(1.234, "pct") == "1.23%" and fmt_value(1.85, "ratio") == "1.85×"
    assert fmt_value(12.3, "INR_per_share") == "₹12.30"


def test_block_and_ids(fin_db):
    p = prepare("TCS vs ACME net profit", ["TCS", "ACME"], [], db=fin_db)
    assert list(p.ids) == ["fin_1", "fin_2", "fin_3"]
    assert p.block.startswith("VERIFIED FIGURES")
    assert "authoritative" in p.block and "not in verified table: ACME" in p.block
    assert "[fin_1] TCS | net_profit | Q1 FY26 | consolidated |" in p.block


def test_evidence_items(fin_db):
    e = prepare("TCS net profit", ["TCS"], [], db=fin_db).evidence[0]
    assert e["chunk_id"] == "fin_1" and e["pdf_url"].startswith("https://")
    assert e["page_number"] == 2 and e["document_label"].startswith("TCS results")


def test_chart_shape(fin_db):
    c = build_chart(prepare("TCS net profit", ["TCS"], [], db=fin_db))
    assert c["unit"] == "INR" and c["display_unit"] == "₹ crore" and c["period_type"] == "Q"
    s = c["series"][0]
    assert s["company"] == "TCS" and s["metric"] == "net_profit" and s["basis"] == "consolidated"
    assert [p["fin_id"] for p in s["points"]] == ["fin_1", "fin_2", "fin_3"]
    assert s["points"][0]["value"] == 1.0 / 1e7 and s["points"][0]["label"] == "Q1 FY26"


def test_no_chart_for_single_point(fin_db):
    assert build_chart(prepare("TCS net profit Q2 FY26", ["TCS"], [], db=fin_db)) is None


def test_chart_first_metric_only_and_series_name(fin_db):
    c = build_chart(prepare("HDFCBANK vs RELIANCE revenue and EPS", ["HDFCBANK", "RELIANCE"], [], db=fin_db))
    assert {s["requested"] for s in c["series"]} == {"revenue_from_operations"}
    assert any(s["name"] == "HDFCBANK (interest earned, consolidated)" for s in c["series"])
    assert any(s["name"] == "RELIANCE (standalone)" for s in c["series"])


def test_prepare_miss(fin_db):
    assert prepare("TCS strategy", ["TCS"], [], db=fin_db) is None


def test_finish_miss():
    assert finish(None, "x") == {"router": {"hit": False}, "chart": None, "numbers_check": None}


def test_finish_hit_runs_numbers_check(fin_db):
    p = prepare("TCS net profit", ["TCS"], [], db=fin_db)
    out = finish(p, "Profit was ₹500 crore [fin_1].")
    assert out["router"]["hit"] is True and out["router"]["rows"] == 3
    assert out["numbers_check"] == {"checked": 1, "unmatched": ["₹500 crore"]}


def test_assistant_metadata_keeps_chart():
    from financials.present import assistant_metadata
    p = {"citations": ["fin_1"], "evidence": [], "metadata": {"chart": {"series": []}, "numbers_check": None}}
    m = assistant_metadata(p)
    assert m["citations"] == ["fin_1"] and m["evidence"] == []
    assert m["pipeline"] == {"chart": {"series": []}, "numbers_check": None}


def test_metric_label_keeps_acronyms():
    from financials.present import metric_label
    assert metric_label("gross_npa_pct") == "Gross NPA" and metric_label("eps_basic") == "EPS basic"
    assert metric_label("net_profit") == "Net profit"


def test_mixed_bases_label_every_series_and_title_uses_requested_metric(fin_db):
    p = prepare("TCS vs RELIANCE revenue", ["TCS", "RELIANCE"], [], db=fin_db)
    assert p is not None
    p2 = prepare("HDFCBANK vs RELIANCE revenue", ["HDFCBANK", "RELIANCE"], [], db=fin_db)
    c = build_chart(p2)
    names = {s["name"] for s in c["series"]}
    assert names == {"HDFCBANK (interest earned, consolidated)", "RELIANCE (standalone)"}
    assert c["title"] == "Revenue from operations" and c["mixed_basis"] is True
    assert "bases differ" in p2.block


def test_single_basis_names_unchanged(fin_db):
    c = build_chart(prepare("TCS net profit", ["TCS"], [], db=fin_db))
    assert c["series"][0]["name"] == "TCS" and c["mixed_basis"] is False and c["title"] == "Net profit"
