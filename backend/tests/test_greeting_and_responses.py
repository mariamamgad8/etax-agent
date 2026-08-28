"""
Feature: greeting intent + deterministic response templates for
greeting/other (no response-generation LLM call for either). Covers: the
greeting intent exists and routes correctly, the deterministic pre-router in
graph.py only ever fires on a full-message match (never misclassifying a
greeting attached to a real request), the template pools are genuinely
bilingual/varied, and the classifier prompt itself (not just the
pre-router) handles greetings and compound messages correctly.

"other" is the collapsed replacement for what used to be three separate
intents (assistant_identity/tax_conversation/off_topic) — see intent.py's
module docstring for why they were merged (the LLM classifier unreliably
split them apart, and worse, sometimes used one of them to swallow a real
fraud_assessment/database_query request).
"""
from typing import get_args

import app.chat.graph as graph
from app.chat.intent import INTENT_ROUTING, Intent, classify_intent
from app.chat.responses import (
    GREETING_TEMPLATES,
    OTHER_TEMPLATES,
    detect_response_language,
    pick_template,
)


# --- intent wiring -----------------------------------------------------------


def test_greeting_is_a_valid_intent():
    assert "greeting" in get_args(Intent)


def test_greeting_routes_to_the_greeting_node():
    assert INTENT_ROUTING["greeting"] == "greeting"


def test_intent_set_is_exactly_six_values():
    """assistant_identity/tax_conversation/off_topic were collapsed into "other"."""
    assert set(get_args(Intent)) == {
        "greeting", "fraud_assessment", "database_query", "other", "unclear", "multi_intent",
    }


# --- deterministic pre-router: full-message match only, never brittle -------


def test_pure_greetings_match_english_and_arabic():
    for text in ["Hi", "hello", "Hey!", "Hi there.", "Good morning!", "مرحبا", "مرحبًا", "السلام عليكم"]:
        assert graph._pure_greeting_match(text), f"expected {text!r} to match as a pure greeting"


def test_compound_message_does_not_match_pure_greeting():
    for text in [
        "Hi, show me my company's taxes.",
        "Hello, is this company suspicious?",
        "hi how much tax did I pay",
        "مرحبا, عايز أعرف الضرايب بتاعتي",
    ]:
        assert not graph._pure_greeting_match(text), f"expected {text!r} NOT to match as a pure greeting"


def test_route_intent_skips_classifier_for_pure_greeting(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("classify_intent must not be called for an obvious pure greeting")

    monkeypatch.setattr(graph, "classify_intent", fail_if_called)

    result = graph.route_intent({"normalized_query": "Hi", "original_query": "Hi"})

    assert result["intent"] == "greeting"
    assert result["intent_confidence"] == 1.0
    assert result["response_language"] == "en"


def test_route_intent_clears_a_stale_response_payload_from_a_previous_turn(monkeypatch):
    """
    Regression test for a real reported bug: once the frontend started
    reusing one thread_id for the whole session (for database_query memory),
    langgraph's checkpointer persists AgentState across turns — a branch
    that never touches response_payload itself (fraud_response, the
    templated greeting/other/clarify nodes) kept silently re-returning the
    PREVIOUS turn's table forever. route_intent is the one node every turn
    always passes through, so it's what must reset this.
    """
    stale_state = {
        "normalized_query": "Hi",
        "original_query": "Hi",
        "response_payload": {"table": {"columns": ["Company Name"], "rows": [["Bright Future Academy"]]}},
    }

    def fail_if_called(*args, **kwargs):
        raise AssertionError("classify_intent must not be called for an obvious pure greeting")

    monkeypatch.setattr(graph, "classify_intent", fail_if_called)
    result = graph.route_intent(stale_state)
    assert result["response_payload"] == {}

    # Same guarantee on the classifier path (a message that doesn't match
    # any deterministic pre-router tier).
    class FakeResult:
        intent = "other"
        confidence = 0.9
        reasoning = "not a specific request"

    monkeypatch.setattr(graph, "classify_intent", lambda *a, **k: FakeResult())
    stale_state["normalized_query"] = "What's the weather like?"
    stale_state["original_query"] = "What's the weather like?"
    result2 = graph.route_intent(stale_state)
    assert result2["response_payload"] == {}


def test_route_intent_still_calls_classifier_for_compound_message(monkeypatch):
    calls = []

    class FakeResult:
        intent = "database_query"
        confidence = 0.9
        reasoning = "explicit retrieval request follows the greeting"

    def fake_classify(query, previous_db_question=None):
        calls.append(query)
        return FakeResult()

    monkeypatch.setattr(graph, "classify_intent", fake_classify)

    query = "Hi, show me my company's taxes."
    result = graph.route_intent({"normalized_query": query, "original_query": query})

    assert calls == [query]
    assert result["intent"] == "database_query"
    assert result["response_language"] == "en"


# --- template pools ------------------------------------------------------


def test_all_template_pools_are_bilingual_with_multiple_variations():
    for pool in (GREETING_TEMPLATES, OTHER_TEMPLATES):
        assert set(pool.keys()) == {"en", "ar"}
        for language, variations in pool.items():
            assert len(variations) >= 3, f"{language} pool has too few variations to avoid feeling identical"
            assert len(set(variations)) == len(variations), "variations must be distinct"


def test_other_templates_only_describe_real_capabilities():
    """Must not claim unimplemented functionality."""
    for variations in OTHER_TEMPLATES.values():
        for text in variations:
            assert "wired up" not in text.lower()


def test_pick_template_always_returns_a_pool_member():
    pool = GREETING_TEMPLATES["en"]
    for _ in range(20):
        assert pick_template(pool) in pool


def test_detect_response_language():
    assert detect_response_language("Hello, how are you?") == "en"
    assert detect_response_language("مرحبا") == "ar"
    assert detect_response_language("Hi مرحبا") == "ar"  # Arabic dominant (5 Arabic chars vs. 2 Latin)


# --- node behavior --------------------------------------------------------
# Nodes read state["response_language"] directly (set once in route_intent)
# rather than re-detecting from original_query — see test_response_language.py
# for the full per-turn-language-consistency feature coverage.


def test_greeting_node_replies_in_detected_language():
    state = {"original_query": "مرحبا", "normalized_query": "مرحبا", "response_language": "ar"}
    result = graph.greeting(state)
    assert result["final_response"] in GREETING_TEMPLATES["ar"]


def test_other_node_replies_in_detected_language():
    state = {"original_query": "who are you?", "normalized_query": "who are you?", "response_language": "en"}
    result = graph.other(state)
    assert result["final_response"] in OTHER_TEMPLATES["en"]

    state_ar = {
        "original_query": "ايه رأيك في الطقس النهارده؟",
        "normalized_query": "ايه رأيك في الطقس النهارده؟",
        "response_language": "ar",
    }
    result_ar = graph.other(state_ar)
    assert result_ar["final_response"] in OTHER_TEMPLATES["ar"]


# --- live classifier prompt check (one live call, project convention) -----


def test_classifier_handles_greeting_and_compound_message_live():
    """
    Confirms the updated system prompt itself (not just the deterministic
    pre-router) correctly separates a pure greeting from a greeting attached
    to a substantive request.
    """
    greeting_result = classify_intent("Good morning, hope you're doing well today.")
    assert greeting_result.intent == "greeting"

    compound_result = classify_intent("Hi, show me my company's taxes.")
    assert compound_result.intent == "database_query"


def test_classifier_handles_arabic_item_price_question_live():
    """
    Regression test for a real reported bug: this exact Arabic phrasing (item
    price/quantity, no English retrieval verb) was classified as "other" —
    the system prompt had rich Arabic examples for fraud_assessment but none
    at all for database_query.
    """
    result = classify_intent("عايز اعرف سعر القطعة واتباع منها قد ايه في برايت فيوتشر")
    assert result.intent == "database_query"
