"""
The redesigned fraud-assessment flow: every field comes from the user's own
linked tax.fraud_records row (claimed at signup via a 9-digit code), never
typed/pasted into the chat. Only the full 23-field/40-engineered-feature
XGBoost model exists now — the dedicated 8-feature model and the LLM
extraction/validation modules were removed entirely.

None of the graph nodes exercised here (load_fraud_record,
handle_fraud_review_action, predict_fraud, fraud_response,
fraud_no_record_response, flagged_review_response) call an LLM — and
fraud_assessment's intent pre-router is fully deterministic (keyword match,
see app.chat.graph._FRAUD_TRIGGER_PHRASES) — so the end-to-end tests below
run for real via run_chat/resume_chat with no mocking and no live API cost.
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import app.chat.graph as graph
from app.chat.db.seed import seed
from app.chat.fraud.engine import predict
from app.chat.fraud.records import record_to_fields
from app.chat.fraud.schema import ALL_FIELDS, FRAUD_THRESHOLD
from app.chat.graph import resume_chat, run_chat
from app.database.models import User
from app.database.tax_models import FraudRecord
from app.main import app

client = TestClient(app)


@pytest.fixture()
def seeded_record(db):
    """
    An unclaimed row, never one of the 3 demo-linked ones (see
    seed._DEMO_FRAUD_LINKS) — those back the live Ahmed/Sara/Omar accounts
    and must never be reassigned/unlinked by a test.
    """
    seed(db)
    return db.query(FraudRecord).filter(FraudRecord.user_id.is_(None)).order_by(FraudRecord.id).first()


def _unlink_and_delete_user(db, record_id, username):
    """
    tax.fraud_records.user_id has no ON DELETE CASCADE (same as
    tax.taxpayers.user_id — see test_sql_security.py's make_scenario
    teardown), so the link must be cleared before the user row can be
    deleted, or the DELETE raises a foreign-key violation. A raw UPDATE
    (not an ORM attribute set) runs immediately, rather than waiting for a
    flush the `db` fixture's session (autoflush=False) won't trigger on its
    own before the subsequent bulk .delete() issues its own raw SQL.
    """
    db.execute(text("UPDATE tax.fraud_records SET user_id = NULL WHERE id = :id"), {"id": record_id})
    db.query(User).filter_by(username=username).delete()
    db.commit()


# --- prediction engine (real model artifacts, no mocking) -------------------


def test_predict_runs_the_full_model_on_a_complete_seeded_record(seeded_record):
    fields = record_to_fields(seeded_record)
    assert set(fields) == set(ALL_FIELDS)  # always all 23 — no partial-field path exists anymore

    result = predict(fields)

    assert 0.0 <= result["probability"] <= 1.0
    assert result["is_high_risk"] == (result["probability"] >= FRAUD_THRESHOLD)


# --- signup requires a valid, unclaimed 9-digit code ------------------------


def _signup_payload(username, code, **overrides):
    payload = {
        "full_name": "Code Test",
        "username": username,
        "email": f"{username}@example.com",
        "password": "testpass123",
        "confirm_password": "testpass123",
        "tax_record_code": code,
    }
    payload.update(overrides)
    return payload


def test_signup_with_a_valid_unclaimed_code_links_the_fraud_record(db, unique_suffix):
    seed(db)
    record = db.query(FraudRecord).filter(FraudRecord.user_id.is_(None)).first()
    username = f"codetest_{unique_suffix}"

    resp = client.post("/auth/signup", json=_signup_payload(username, record.claim_code))
    assert resp.status_code == 201

    db.expire_all()
    linked = db.get(FraudRecord, record.id)
    assert str(linked.user_id) == resp.json()["user"]["id"]

    _unlink_and_delete_user(db, record.id, username)


def test_signup_with_unknown_code_is_rejected(unique_suffix):
    username = f"codetest_{unique_suffix}"
    resp = client.post("/auth/signup", json=_signup_payload(username, "999999999"))
    assert resp.status_code == 422


def test_signup_with_already_claimed_code_is_rejected(db, unique_suffix):
    seed(db)
    record = db.query(FraudRecord).filter(FraudRecord.user_id.isnot(None)).first()
    username = f"codetest_{unique_suffix}"

    resp = client.post("/auth/signup", json=_signup_payload(username, record.claim_code))

    assert resp.status_code == 409
    assert db.query(User).filter_by(username=username).first() is None


def test_signup_with_malformed_code_fails_validation(unique_suffix):
    username = f"codetest_{unique_suffix}"
    resp = client.post("/auth/signup", json=_signup_payload(username, "123"))
    assert resp.status_code == 422


# --- graph nodes (pure functions — none of these call an LLM) ---------------


def test_load_fraud_record_finds_the_linked_row(seeded_record, db):
    user_id = uuid.uuid4()
    db.execute(text("INSERT INTO auth.users (id, full_name, username, email, password_hash, is_active) "
                     "VALUES (:id, 'x', :u, :e, 'x', true)"), {"id": str(user_id), "u": f"fr_{user_id.hex[:8]}", "e": f"fr_{user_id.hex[:8]}@x.com"})
    seeded_record.user_id = user_id
    db.add(seeded_record)
    db.commit()

    state = graph.load_fraud_record({"user_id": str(user_id)})

    assert state["fraud_record_missing"] is False
    assert state["fraud_record_id"] == seeded_record.id
    assert state["fraud_review_status"] == "pending"
    assert set(state["fraud_record_fields"]) == set(ALL_FIELDS)

    seeded_record.user_id = None
    db.add(seeded_record)
    db.commit()
    db.execute(text("DELETE FROM auth.users WHERE id = :id"), {"id": str(user_id)})
    db.commit()


def test_load_fraud_record_missing_for_unlinked_user():
    state = graph.load_fraud_record({"user_id": str(uuid.uuid4())})
    assert state["fraud_record_missing"] is True


def test_fraud_no_record_response_is_localized():
    en = graph.fraud_no_record_response({"response_language": "en"})
    ar = graph.fraud_no_record_response({"response_language": "ar"})
    assert en["final_response"] != ar["final_response"]
    assert en["final_response"]


def test_predict_fraud_and_fraud_response_use_record_fields(seeded_record):
    fields = record_to_fields(seeded_record)
    state = graph.predict_fraud({"fraud_record_fields": fields})
    assert 0.0 <= state["prediction_probability"] <= 1.0

    result = graph.fraud_response({"response_language": "en", **state})
    assert "Risk score" in result["final_response"]
    assert "suspicious" not in result["final_response"].lower()  # replaced per explicit instruction


def test_handle_fraud_review_action_confirm_routes_to_predict():
    state = graph.handle_fraud_review_action({"fraud_review_action": {"action": "confirm"}})
    assert state["fraud_flagged"] is False
    assert graph._fraud_action_router(state) == "predict_fraud"


def test_handle_fraud_review_action_flag_updates_status_and_routes_to_flagged_response(seeded_record, db):
    state = {
        "user_id": str(uuid.uuid4()),
        "fraud_record_id": seeded_record.id,
        "fraud_review_action": {"action": "flag", "fields": ["Net_Profit", "Tax_Gap"]},
    }

    result = graph.handle_fraud_review_action(state)

    assert result["fraud_flagged"] is True
    assert graph._fraud_action_router(result) == "flagged_review_response"

    db.expire_all()
    refreshed = db.get(FraudRecord, seeded_record.id)
    assert refreshed.review_status == "requested_review"
    assert refreshed.flagged_fields == ["Net_Profit", "Tax_Gap"]

    refreshed.review_status = "pending"
    refreshed.flagged_fields = None
    db.add(refreshed)
    db.commit()


def test_flagged_review_response_is_localized():
    result = graph.flagged_review_response({"response_language": "ar"})
    assert result["final_response"]


# --- end-to-end via the real graph (deterministic pre-router, no LLM) -------


def test_end_to_end_confirm_produces_a_risk_score(db, unique_suffix):
    seed(db)
    record = db.query(FraudRecord).filter(FraudRecord.user_id.is_(None)).first()
    username = f"e2e_{unique_suffix}"
    signup = client.post("/auth/signup", json=_signup_payload(username, record.claim_code))
    user_id = signup.json()["user"]["id"]

    state, interrupt_payload = run_chat("check my company for fraud", f"{user_id}:1", user_id)
    assert interrupt_payload["type"] == "fraud_review"
    assert interrupt_payload["record_id"] == record.id
    assert set(interrupt_payload["record"]) == set(ALL_FIELDS)

    final_state, final_interrupt = resume_chat({"action": "confirm"}, f"{user_id}:1")
    assert final_interrupt is None
    assert "Risk score" in final_state["final_response"]

    _unlink_and_delete_user(db, record.id, username)


def test_end_to_end_flag_sets_requested_review(db, unique_suffix):
    seed(db)
    record = db.query(FraudRecord).filter(FraudRecord.user_id.is_(None)).first()
    username = f"e2e_{unique_suffix}"
    signup = client.post("/auth/signup", json=_signup_payload(username, record.claim_code))
    user_id = signup.json()["user"]["id"]

    _, interrupt_payload = run_chat("check my company for fraud", f"{user_id}:1", user_id)
    assert interrupt_payload["type"] == "fraud_review"

    final_state, final_interrupt = resume_chat({"action": "flag", "fields": ["Net_Profit"]}, f"{user_id}:1")
    assert final_interrupt is None
    assert final_state["final_response"]

    db.expire_all()
    linked = db.get(FraudRecord, record.id)
    assert linked.review_status == "requested_review"

    _unlink_and_delete_user(db, record.id, username)
