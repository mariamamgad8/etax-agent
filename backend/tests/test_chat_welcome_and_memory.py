"""
Feature: a personalized session-start voice/text welcome (GET /chat/welcome,
app.chat.responses.build_welcome_text) and short-term cross-turn memory for
database_query (AgentState.last_db_question_en, read/written only by
graph.prepare_db_question — see that function's docstring).

The memory test is live (a real query-planning-adjacent LLM call, via
prepare_db_question) — this project's "a couple of live calls per file"
convention (see test_query_planning.py) — run against the real seeded ahmed
account (majority owner of Bright Future Academy), never a scenario built
just for this test, since the whole point is proving cross-turn state
actually persists on the real checkpointer between two separate run_chat
calls sharing one thread_id.
"""
import datetime
import uuid

import pytest
from fastapi.testclient import TestClient

from app.auth.security import create_token
from app.chat.graph import run_chat
from app.chat.intent import classify_intent
from app.chat.responses import build_welcome_text
from app.database.db import SessionLocal
from app.database.models import User
from app.main import app

client = TestClient(app)


@pytest.fixture()
def ahmed_headers():
    """
    Mints a real authenticated token for the seeded ahmed account and, since
    require_stage's sliding-inactivity check (see test_session_inactivity.py)
    would otherwise 401 on a stale last_active_at left over from a previous
    test run, stamps it fresh first — same fix already applied live for this
    exact failure mode (see app/face/routes.py, which now stamps it at
    token-issuance time too).
    """
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(username="ahmed").one()
        user.last_active_at = datetime.datetime.now(datetime.timezone.utc)
        db.add(user)
        db.commit()
        token = create_token(str(user.id), "authenticated", 60)
        return {"Authorization": f"Bearer {token}"}, str(user.id), user.full_name
    finally:
        db.close()


# --- build_welcome_text (pure) -----------------------------------------------


def test_build_welcome_text_includes_the_name_in_english():
    text = build_welcome_text("en", "Ahmed Ali")
    assert "Ahmed Ali" in text
    assert "tax assistant" in text.lower()


def test_build_welcome_text_includes_the_name_in_arabic():
    text = build_welcome_text("ar", "Ahmed Ali")
    assert "Ahmed Ali" in text
    assert text != build_welcome_text("en", "Ahmed Ali")


def test_build_welcome_text_defaults_to_english_for_an_unknown_language():
    assert build_welcome_text("fr", "Ahmed Ali") == build_welcome_text("en", "Ahmed Ali")


# --- GET /chat/welcome --------------------------------------------------------


def test_welcome_endpoint_returns_the_account_full_name(ahmed_headers):
    headers, _user_id, full_name = ahmed_headers
    resp = client.get("/chat/welcome?language=en", headers=headers)
    assert resp.status_code == 200
    assert full_name in resp.json()["text"]


def test_welcome_endpoint_respects_arabic_language_param(ahmed_headers):
    headers, _user_id, _full_name = ahmed_headers
    resp = client.get("/chat/welcome?language=ar", headers=headers)
    assert resp.status_code == 200
    en_resp = client.get("/chat/welcome?language=en", headers=headers)
    assert resp.json()["text"] != en_resp.json()["text"]


def test_welcome_endpoint_requires_authentication():
    resp = client.get("/chat/welcome?language=en")
    assert resp.status_code == 401


def test_welcome_endpoint_boot_id_is_stable_within_the_same_process(ahmed_headers):
    """
    The frontend uses boot_id to decide whether a persisted conversation is
    still valid (see ChatPage.jsx) — it must be the same value across calls
    within one running process (only a real process restart changes it), or
    a valid conversation would get discarded on every single page load.
    """
    headers, _user_id, _full_name = ahmed_headers
    first = client.get("/chat/welcome?language=en", headers=headers).json()["boot_id"]
    second = client.get("/chat/welcome?language=en", headers=headers).json()["boot_id"]
    assert first
    assert first == second


# --- classify_intent is memory-aware for ambiguous follow-ups (live) --------


def test_classify_intent_uses_previous_question_for_an_ambiguous_followup():
    """
    Without context, "what about the taxes" is genuinely ambiguous on its
    own. With the previous turn's question given as context, the classifier
    must still land on database_query — otherwise a terse follow-up never
    even reaches prepare_db_question's own memory handling at all.
    """
    result = classify_intent("what about the taxes", previous_db_question="What are the sales for Bright Future Academy?")
    assert result.intent == "database_query"


def test_classify_intent_ignores_previous_question_when_new_message_stands_alone():
    result = classify_intent("Hi", previous_db_question="What are the sales for Bright Future Academy?")
    assert result.intent == "greeting"


# --- cross-turn database_query memory (live) ---------------------------------


def test_follow_up_question_inherits_the_previously_mentioned_company(ahmed_headers):
    """
    Regression coverage for the explicitly requested behavior: "get me the
    sales in Bright company" then, in a separate turn on the SAME thread,
    "what about the taxes" — the second turn names no company at all, so
    prepare_db_question must resolve it against the first turn's question
    (persisted via AgentState.last_db_question_en on the real checkpointer)
    rather than asking about taxes with no company context at all.
    """
    _headers, user_id, _full_name = ahmed_headers
    thread_id = f"{user_id}:{uuid.uuid4().hex}"

    first_state, first_interrupt = run_chat("get me the sales in Bright Future Academy", thread_id, user_id)
    assert first_interrupt is None
    assert "bright" in first_state["db_question_en"].lower()

    second_state, second_interrupt = run_chat("what about the taxes", thread_id, user_id)
    assert second_interrupt is None
    # The follow-up mentioned no company at all — memory must have carried
    # "Bright Future Academy" forward into the fully-resolved question.
    assert "bright" in second_state["db_question_en"].lower()
    assert "tax" in second_state["db_question_en"].lower()
