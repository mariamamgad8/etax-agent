"""
Feature: consistent per-turn assistant response language ("ar" | "en").

state["response_language"] is set exactly once per turn, in route_intent,
from the user's own message — every response-producing node (greeting,
other, clarify_intent, handle_multi_intent, db_response, fraud_response, and
fraud/validation.py's error messages) reads that single value instead of
re-detecting language itself. Internal-only text (prepare_db_question's
English SQL-generation question) is exempt: it never reaches the user, so
it isn't covered here.

Each plain-text chat turn starts a fresh graph run (see graph.run_chat /
routes.py's send_message — a plain message always gets a new thread_id), so
"switching languages mid-conversation" is really just "the next independent
turn detects its own message's language" — covered below both at the
route_intent unit level and via two live run_chat calls.
"""
import uuid

import app.chat.graph as graph
from app.chat.fraud.validation import validate_fraud_features
from app.chat.graph import run_chat
from app.chat.responses import (
    LANGUAGE_NAMES,
    build_fraud_result_text,
    detect_response_language,
)

# --- deterministic language detection ---------------------------------------


def test_arabic_text_input_detected_as_arabic():
    assert detect_response_language("عايز أعرف الضرائب بتاعة الشركة") == "ar"


def test_english_text_input_detected_as_english():
    assert detect_response_language("I want to know my company's taxes.") == "en"


def test_arabic_voice_transcript_detected_as_arabic():
    """STT hands the graph a transcript, not audio — same text-based detection applies."""
    transcript = "عايز اعرف الضريبة المستحقة على شركتي في السنة اللي فاتت"
    assert detect_response_language(transcript) == "ar"


def test_english_voice_transcript_detected_as_english():
    transcript = "how much tax did my company pay last year"
    assert detect_response_language(transcript) == "en"


def test_mixed_terminology_dominant_arabic_with_english_terms():
    # "VAT" and "SQL" are English technical terms embedded in an otherwise
    # Arabic sentence — the dominant language (by script character count)
    # must still be Arabic, not flipped by the embedded terms.
    text = "عايز أعرف قيمة الـ VAT والـ SQL بتاعة الشركة دي بالظبط"
    assert detect_response_language(text) == "ar"


def test_mixed_terminology_dominant_english_with_arabic_company_name():
    # A single Arabic company name inside an otherwise-English question must
    # not flip the whole reply to Arabic.
    text = "What is the total VAT declared by شركة ABC for last year?"
    assert detect_response_language(text) == "en"


# --- switching languages across independent turns ---------------------------


def test_route_intent_switches_arabic_to_english_across_turns():
    arabic_state = graph.route_intent({"normalized_query": "مرحبا", "original_query": "مرحبا"})
    assert arabic_state["response_language"] == "ar"

    english_state = graph.route_intent({"normalized_query": "Hi", "original_query": "Hi"})
    assert english_state["response_language"] == "en"


def test_route_intent_switches_english_to_arabic_across_turns():
    english_state = graph.route_intent({"normalized_query": "Hello", "original_query": "Hello"})
    assert english_state["response_language"] == "en"

    arabic_state = graph.route_intent({"normalized_query": "أهلا", "original_query": "أهلا"})
    assert arabic_state["response_language"] == "ar"


def test_full_turn_switches_language_live():
    """
    Two independent live graph runs (each gets its own fresh thread_id, just
    like two real chat turns) — the second must answer in the language of
    its own message, unaffected by the first. A real UUID user_id is used so
    the test survives regardless of which intent the live classifier picks
    for the second message (e.g. database_query needs a parseable UUID).
    """
    user_id = str(uuid.uuid4())

    state_ar, _ = run_chat("مرحبا", f"{user_id}:1", user_id)
    assert state_ar["response_language"] == "ar"
    assert state_ar["final_response"] in graph.GREETING_TEMPLATES["ar"]

    state_en, _ = run_chat("Can you explain that in English?", f"{user_id}:2", user_id)
    assert state_en["response_language"] == "en"


# --- applied consistently across response-producing surfaces ---------------


def test_unauthorized_message_prompt_is_localized_for_arabic(monkeypatch):
    captured = {}

    def fake_call_llm_text(system_prompt, user_prompt):
        captured["system_prompt"] = system_prompt
        return "رسالة عدم تصريح"

    monkeypatch.setattr(graph, "call_llm_text", fake_call_llm_text)

    state = {
        "original_query": "عايز أعرف ضرايب شركة",
        "response_language": "ar",
        "sql_result": {"error": "unauthorized"},
    }
    result = graph.db_response(state)

    assert LANGUAGE_NAMES["ar"] in captured["system_prompt"]
    assert result["final_response"] == "رسالة عدم تصريح"


def test_unauthorized_message_prompt_is_localized_for_english(monkeypatch):
    captured = {}

    def fake_call_llm_text(system_prompt, user_prompt):
        captured["system_prompt"] = system_prompt
        return "You are not authorized."

    monkeypatch.setattr(graph, "call_llm_text", fake_call_llm_text)

    state = {
        "original_query": "show me company taxes",
        "response_language": "en",
        "sql_result": {"error": "unauthorized"},
    }
    result = graph.db_response(state)

    assert LANGUAGE_NAMES["en"] in captured["system_prompt"]
    assert result["final_response"] == "You are not authorized."


def test_no_result_message_prompt_uses_state_language_not_query_text(monkeypatch):
    """
    Regression guard: db_response must use state["response_language"], not
    re-detect from original_query — pass a state where they'd disagree and
    confirm the state value wins.
    """
    captured = {}

    def fake_call_llm_text(system_prompt, user_prompt):
        captured["system_prompt"] = system_prompt
        return "not found"

    monkeypatch.setattr(graph, "call_llm_text", fake_call_llm_text)

    state = {
        "original_query": "مرحبا",  # would detect as Arabic if re-detected here
        "response_language": "en",  # but the turn's actual language was English
        "sql_result": {},
    }
    graph.db_response(state)

    assert LANGUAGE_NAMES["en"] in captured["system_prompt"]
    assert LANGUAGE_NAMES["ar"] not in captured["system_prompt"]


def test_fraud_result_text_localized_for_both_languages():
    en_text = build_fraud_result_text("en", "Standard Assessment", 8, 23, "Suspicious", 0.42, 0.195)
    assert "Standard Assessment" in en_text
    assert "Suspicious" in en_text

    ar_text = build_fraud_result_text("ar", "Standard Assessment", 8, 23, "Suspicious", 0.42, 0.195)
    assert "التقييم القياسي" in ar_text
    assert "مشتبه به" in ar_text
    assert "0.42" in ar_text


def test_fraud_response_node_uses_state_language():
    state = {
        "response_language": "ar",
        "prediction_label": "Not suspicious",
        "prediction_probability": 0.05,
        "prediction_tier": "Comprehensive Assessment",
        "fields_provided": 23,
        "fields_total": 23,
    }
    result = graph.fraud_response(state)
    assert "غير مشتبه به" in result["final_response"]
    assert "التقييم الشامل" in result["final_response"]


def test_fraud_validation_errors_localized_arabic():
    errors = validate_fraud_features({}, "ar")
    assert len(errors) == 8  # all 8 required fields missing
    assert all("مطلوب" in e for e in errors)
    assert any("Net_Profit" in e for e in errors)  # field identifier stays as-is


def test_fraud_validation_errors_default_to_english():
    errors = validate_fraud_features({})
    assert any("is required" in e for e in errors)


def test_greeting_response_localized(monkeypatch):
    state_en = graph.route_intent({"normalized_query": "Hi", "original_query": "Hi"})
    reply_en = graph.greeting(state_en)
    assert reply_en["final_response"] in graph.GREETING_TEMPLATES["en"]

    state_ar = graph.route_intent({"normalized_query": "مرحبا", "original_query": "مرحبا"})
    reply_ar = graph.greeting(state_ar)
    assert reply_ar["final_response"] in graph.GREETING_TEMPLATES["ar"]


def test_other_response_localized():
    state_en = {"response_language": "en"}
    state_ar = {"response_language": "ar"}
    assert graph.other(state_en)["final_response"] in graph.OTHER_TEMPLATES["en"]
    assert graph.other(state_ar)["final_response"] in graph.OTHER_TEMPLATES["ar"]


def test_clarify_and_multi_intent_responses_localized():
    for node, pool in ((graph.clarify_intent, graph.CLARIFY_INTENT_TEMPLATES), (graph.handle_multi_intent, graph.MULTI_INTENT_TEMPLATES)):
        assert node({"response_language": "en"})["final_response"] in pool["en"]
        assert node({"response_language": "ar"})["final_response"] in pool["ar"]
