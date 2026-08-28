"""
Live tests for query_planning.extract_query_plan — the one LLM call in the
new database_query pipeline that turns free-form text into a structured
plan (company mentions + field/metric names only, never a company_id/share/
access decision). Uses the exact phrasings from real reported failures.
Everything security/authorization-relevant (resolve_company_mentions,
authorize_plan, the AST validator) is deterministic and covered without any
LLM in test_sql_security.py — this file only checks the LLM extraction
itself is reasonably accurate, matching this project's "a couple of live
calls per file" convention.
"""
from app.chat.services.query_planning import FIELDS, METRICS, extract_query_plan


def test_extracts_fields_for_item_level_request_ignoring_the_taxpayer_id_mention():
    plan = extract_query_plan("get me each item sold, price, quantity for taxpayer id 2")
    assert {"item_price", "quantity"} <= set(plan.fields)
    # The taxpayer id mention must never become a company_mention (or
    # anything else authorization-relevant) — see authorize_plan, which
    # never trusts taxpayer/company identifiers out of free text anyway.
    assert plan.company_mentions == [] or all("2" not in m for m in plan.company_mentions)


def test_extracts_company_mentions_and_share_field():
    plan = extract_query_plan("i want to know the amount of shares i have in Bright future academy and city medical center")
    joined = " ".join(m.lower() for m in plan.company_mentions)
    assert "bright" in joined
    assert "city medical" in joined
    assert "share" in plan.fields


def test_extracts_sales_and_units_sold_metrics_for_a_named_company():
    plan = extract_query_plan("i want to get the sales and item sold for bright future")
    assert any("bright" in m.lower() for m in plan.company_mentions)
    assert "total_sales" in plan.metrics or "sales" in plan.fields
    assert "units_sold" in plan.metrics or "quantity" in plan.fields


def test_only_ever_uses_known_field_and_metric_names():
    """Even on live output, every returned name must be from the fixed vocabulary — never invented."""
    plan = extract_query_plan("show me everything about my companies including sales, taxes, and how many invoices")
    assert set(plan.fields) <= set(FIELDS)
    assert set(plan.metrics) <= set(METRICS)


def test_wants_profile_info_true_for_identity_question():
    plan = extract_query_plan("what is my taxpayer id and which companies do I own")
    assert plan.wants_profile_info is True


def test_wants_fraud_status_true_for_review_status_question():
    plan = extract_query_plan("has my tax record been reviewed yet")
    assert plan.wants_fraud_status is True


def test_arabic_taxes_question_maps_to_taxes_field():
    """
    Regression test for a real reported bug: "عايز اشوف ضرايبي" ("I want to
    see my taxes") returned an "unclear" database status — extract_query_plan
    had zero Arabic examples for database_query at all, only for
    fraud_assessment, so it mapped nothing even though "taxes" is directly in
    the fixed vocabulary.
    """
    plan = extract_query_plan("عايز اشوف ضرايبي")
    assert "taxes" in plan.fields


def test_arabic_item_price_and_quantity_question_maps_to_the_right_fields():
    plan = extract_query_plan("عايز اعرف سعر القطعة وكمية اللي اتباع منها في برايت فيوتشر")
    assert {"item_price", "quantity"} <= set(plan.fields)
    assert any("برايت" in m for m in plan.company_mentions)


def test_avg_taxes_maps_to_the_average_taxes_metric():
    """
    Regression test for a real reported bug: this phrasing used to map to
    NOTHING (no average_taxes metric existed), which authorize_plan then
    misread as an ownership-summary question — see test_sql_security.py's
    section 20 for the full failure story and the authorize_plan-level fix.
    """
    plan = extract_query_plan("get me the avg taxes between both of my companies")
    assert "average_taxes" in plan.metrics
