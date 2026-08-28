"""
Feature: deterministic fraud_assessment pre-router in route_intent, added
after production logs showed the LLM classifier repeatedly losing real
fraud requests — most visibly on Arabic phrasing and on a pasted feature
dump with no framing sentence. See graph.py's route_intent docstring/comments
for the two tiers (field:value dump, then keyword trigger) this covers.

Every case below is a real failure observed in production logs before this
fix: each used to land on tax_conversation, database_query, or unclear
instead of fraud_assessment.
"""
import app.chat.graph as graph
from app.chat.intent import classify_intent


def _fails_if_classifier_called(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("classify_intent must not be called once a deterministic pre-router tier matches")

    monkeypatch.setattr(graph, "classify_intent", fail)


# --- tier 1: pasted field:value dump -----------------------------------


def test_field_dump_detector_matches_the_real_failing_paste():
    text = (
        "Row 7: Net_Profit: 154864.67 Taxable_Income: 141487.4 Declared_Tax: 28708.52 "
        "Previous_Violations: 2 Cash_Transactions_Percentage: 40.34 Invoice_Mismatch: 0 "
        "Tax_Gap: 3126.15 Industry_Risk_ord: High"
    )
    assert graph._looks_like_fraud_field_dump(text)


def test_field_dump_detector_requires_at_least_three_fields():
    assert not graph._looks_like_fraud_field_dump("Net_Profit: 5000")
    assert not graph._looks_like_fraud_field_dump("Net_Profit: 5000 Tax_Gap: 200")
    assert graph._looks_like_fraud_field_dump("Net_Profit: 5000 Tax_Gap: 200 Declared_Tax: 100")


def test_field_dump_detector_ignores_ordinary_prose_mentioning_one_field_name():
    # A normal sentence that happens to mention "Tax_Gap" once must not trip the dump detector.
    assert not graph._looks_like_fraud_field_dump("What's my Tax_Gap for last year?")


def test_route_intent_skips_classifier_for_field_dump(monkeypatch):
    _fails_if_classifier_called(monkeypatch)
    text = (
        "اهلا عايز اشوف صحة ضرايبي Row 7: Net_Profit: 154864.67 Taxable_Income: 141487.4 "
        "Declared_Tax: 28708.52 Previous_Violations: 2 Cash_Transactions_Percentage: 40.34 "
        "Invoice_Mismatch: 0 Tax_Gap: 3126.15 Industry_Risk_ord: High"
    )
    result = graph.route_intent({"normalized_query": text, "original_query": text})
    assert result["intent"] == "fraud_assessment"
    assert result["intent_confidence"] == 1.0


# --- tier 2: fraud-leaning keyword/phrase (Arabic and English) ----------


def test_route_intent_catches_arabic_soundness_phrasing_without_the_classifier(monkeypatch):
    _fails_if_classifier_called(monkeypatch)
    text = "عايز اعرف رأي سليم ولا محتاج أشوف متخصص يفحصه لي، عشان أتأكد أمشي في الإجراءات ولا أراجع الورق."
    result = graph.route_intent({"normalized_query": text, "original_query": text})
    assert result["intent"] == "fraud_assessment"


def test_route_intent_catches_arabic_company_papers_phrasing_without_the_classifier(monkeypatch):
    _fails_if_classifier_called(monkeypatch)
    text = "عايز اشوف ورق الشلركة بتاعتي سليم ولا في مشكلة"
    result = graph.route_intent({"normalized_query": text, "original_query": text})
    assert result["intent"] == "fraud_assessment"


def test_route_intent_catches_check_fraud_without_the_classifier(monkeypatch):
    _fails_if_classifier_called(monkeypatch)
    result = graph.route_intent({"normalized_query": "check fraud", "original_query": "check fraud"})
    assert result["intent"] == "fraud_assessment"


def test_route_intent_catches_want_to_assess_my_company_without_the_classifier(monkeypatch):
    _fails_if_classifier_called(monkeypatch)
    text = "want to assess my company"
    result = graph.route_intent({"normalized_query": text, "original_query": text})
    assert result["intent"] == "fraud_assessment"


def test_fraud_trigger_keyword_list_covers_the_reported_phrases():
    for phrase in ["سليم", "اوراق", "فحص", "تهرب ضريبي", "detect", "sus", "check", "assess"]:
        assert graph._contains_fraud_trigger(phrase), f"expected {phrase!r} to be a recognized fraud trigger"


def test_arabic_transliterated_risk_score_reopens_the_fraud_flow_without_the_classifier(monkeypatch):
    """
    Regression test for a real reported bug: "مخاطر" (the Arabic word) was
    already a trigger, but a user typing the English term "risk score" in
    Arabic script ("الريسك سكور") is a different substring entirely and fell
    through to the classifier, which read the (admittedly half-finished)
    message as "other" instead of reopening the fraud review.
    """
    _fails_if_classifier_called(monkeypatch)
    text = "هو معلش نسيت كان في خطا في البيانات فكنت عايز اعدل في بيانات الريسك سكور"
    result = graph.route_intent({"normalized_query": text, "original_query": text})
    assert result["intent"] == "fraud_assessment"


# --- db-query override: a retrieval verb defers the ambiguous case to the LLM ---


def test_db_query_override_phrase_suppresses_the_keyword_preroute(monkeypatch):
    calls = []

    class FakeResult:
        intent = "database_query"
        confidence = 0.8
        reasoning = "explicit retrieval verb present alongside an ambiguous fraud-adjacent word"

    def fake_classify(query, previous_db_question=None):
        calls.append(query)
        return FakeResult()

    monkeypatch.setattr(graph, "classify_intent", fake_classify)

    # "retrieve" is a DB-override phrase, so even though "check" is present,
    # this must reach the classifier rather than being deterministically
    # forced into fraud_assessment.
    text = "Can you retrieve and check my company's tax records?"
    result = graph.route_intent({"normalized_query": text, "original_query": text})

    assert calls == [text]
    assert result["intent"] == "database_query"


# --- live classifier check for a case the pre-router correctly leaves alone ---


def test_classifier_correctly_routes_ownership_share_question_live():
    """
    Real failure: "I want to know how much share do I have in my company"
    was classified tax_conversation (now removed as an intent entirely).
    Share is a stored fact (tax.company_owners.share) — must be database_query.
    """
    result = classify_intent("I want to know how much share do I have in my company")
    assert result.intent == "database_query"
