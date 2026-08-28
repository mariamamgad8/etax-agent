"""
Feature: sliding inactivity session timeout for the "authenticated" stage.
A plain JWT's `exp` is fixed at issuance and can't slide, so the real
enforcement lives in app.auth.dependencies.require_stage, which stamps
auth.users.last_active_at on every authenticated request and rejects the
request once more than SESSION_INACTIVITY_TIMEOUT_MINUTES has passed since
the last one. SESSION_TOKEN_TTL_MINUTES is deliberately a much longer outer
ceiling on the token itself, so these tests manipulate last_active_at
directly (simulating time passing) rather than waiting on the token's own
expiry, which is not what ends an active session here.
"""
import datetime
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.security import create_token
from app.config import SESSION_INACTIVITY_TIMEOUT_MINUTES
from app.database.models import User
from app.main import app

client = TestClient(app)


@pytest.fixture()
def authed_user(db, unique_suffix, next_fraud_code):
    username = f"inactivity_{unique_suffix}"
    response = client.post(
        "/auth/signup",
        json={
            "full_name": "Inactivity Test",
            "username": username,
            "email": f"{username}@example.com",
            "password": "testpass123",
            "confirm_password": "testpass123",
            "tax_record_code": next_fraud_code(),
        },
    )
    user_id = response.json()["user"]["id"]
    token = create_token(user_id, "authenticated", 480)

    yield user_id, {"Authorization": f"Bearer {token}"}

    db.execute(text("UPDATE tax.fraud_records SET user_id = NULL WHERE user_id = :uid"), {"uid": user_id})
    db.query(User).filter_by(username=username).delete()
    db.commit()


def _set_last_active_at(db, user_id: str, when: datetime.datetime) -> None:
    db.execute(text("UPDATE auth.users SET last_active_at = :t WHERE id = :id"), {"t": when, "id": user_id})
    db.commit()


def test_first_authenticated_request_succeeds_with_no_prior_activity(authed_user):
    """A freshly-signed-up user has last_active_at = NULL — must not be treated as 'already expired'."""
    _, headers = authed_user
    resp = client.get("/auth/me", headers=headers)
    assert resp.status_code == 200


def test_authenticated_request_stamps_last_active_at(authed_user, db):
    user_id, headers = authed_user
    before = client.get("/auth/me", headers=headers)
    assert before.status_code == 200

    db.expire_all()
    user = db.get(User, uuid.UUID(user_id))
    assert user.last_active_at is not None


def test_request_well_within_the_inactivity_window_still_succeeds(authed_user, db):
    user_id, headers = authed_user
    client.get("/auth/me", headers=headers)  # stamps last_active_at

    recent = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        minutes=SESSION_INACTIVITY_TIMEOUT_MINUTES / 2
    )
    _set_last_active_at(db, user_id, recent)

    resp = client.get("/auth/me", headers=headers)
    assert resp.status_code == 200


def test_request_past_the_inactivity_window_is_rejected(authed_user, db):
    user_id, headers = authed_user
    client.get("/auth/me", headers=headers)  # stamps last_active_at, token is otherwise still valid

    stale = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        minutes=SESSION_INACTIVITY_TIMEOUT_MINUTES + 5
    )
    _set_last_active_at(db, user_id, stale)

    resp = client.get("/auth/me", headers=headers)
    assert resp.status_code == 401
    assert "inactivity" in resp.json()["detail"].lower()


def test_activity_slides_the_window_forward(authed_user, db):
    """Two requests each within the window of the PREVIOUS one must both succeed, even if their combined span exceeds the window."""
    user_id, headers = authed_user
    client.get("/auth/me", headers=headers)

    almost_stale = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        minutes=SESSION_INACTIVITY_TIMEOUT_MINUTES - 5
    )
    _set_last_active_at(db, user_id, almost_stale)

    # This request is still within the window (5 min short of the limit) —
    # must succeed AND refresh last_active_at back to "now".
    resp = client.get("/auth/me", headers=headers)
    assert resp.status_code == 200

    db.expire_all()
    user = db.get(User, uuid.UUID(user_id))
    assert user.last_active_at > almost_stale


def test_pending_enrollment_stage_is_not_subject_to_inactivity_check(db, unique_suffix, next_fraud_code):
    """Only the 'authenticated' stage has sliding-session semantics — sign-in steps are unaffected."""
    username = f"inactivity_pending_{unique_suffix}"
    response = client.post(
        "/auth/signup",
        json={
            "full_name": "Pending Test",
            "username": username,
            "email": f"{username}@example.com",
            "password": "testpass123",
            "confirm_password": "testpass123",
            "tax_record_code": next_fraud_code(),
        },
    )
    token = response.json()["access_token"]
    user_id = response.json()["user"]["id"]

    stale = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
    _set_last_active_at(db, user_id, stale)

    # A real (if trivial) JPEG — face_engine.detect() only guarantees a clean
    # 422 (NoFaceDetected) for a decodable-but-faceless image; garbage bytes
    # fail earlier at Pillow's own decode step with an unrelated 500. The
    # point of this test is the 401 vs. 422 distinction, not image decoding.
    import io
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (32, 32), color="white").save(buf, format="JPEG")

    resp = client.post(
        "/face/enroll",
        headers={"Authorization": f"Bearer {token}"},
        files={"image": ("x.jpg", buf.getvalue(), "image/jpeg")},
    )
    # Rejected for not containing a detectable face (422), never for
    # "session expired" (401) — pending_enrollment tokens aren't subject to
    # this check at all.
    assert resp.status_code != 401

    db.execute(text("UPDATE tax.fraud_records SET user_id = NULL WHERE user_id = :uid"), {"uid": user_id})
    db.query(User).filter_by(username=username).delete()
    db.commit()
