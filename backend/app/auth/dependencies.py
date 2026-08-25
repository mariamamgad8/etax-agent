import datetime
import uuid

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.security import decode_token
from app.config import SESSION_INACTIVITY_TIMEOUT_MINUTES
from app.database.db import get_db
from app.database.models import User

_bearer = HTTPBearer(auto_error=False)
_INACTIVITY_TIMEOUT = datetime.timedelta(minutes=SESSION_INACTIVITY_TIMEOUT_MINUTES)


def _get_payload(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> dict:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated.")
    try:
        return decode_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired. Sign in again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session.")


def require_stage(*allowed_stages: str):
    """
    Builds a dependency that only accepts a token whose `stage` claim is one
    of `allowed_stages`, and resolves it to the matching User row. This is
    what stops someone with a password-only token from reaching face-verified
    routes, or a stale chat session from surviving past its stage.

    For the "authenticated" stage specifically, this also enforces a
    sliding inactivity window: User.last_active_at is checked against
    SESSION_INACTIVITY_TIMEOUT_MINUTES and then stamped to now() on every
    request. The token's own `exp` (SESSION_TOKEN_TTL_MINUTES, a much
    longer outer ceiling) is deliberately not what ends an active session —
    a JWT's expiry is fixed at issuance and can't slide, so this DB-backed
    check is the real enforcement. pending_enrollment/face_required are
    short, already-fixed-TTL steps within one continuous sign-in flow, not
    "sessions" in this sense, so they're left alone.
    """

    def dependency(payload: dict = Depends(_get_payload), db: Session = Depends(get_db)) -> User:
        if payload.get("stage") not in allowed_stages:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "This step is not available yet in your sign-in sequence.",
            )
        try:
            user_id = uuid.UUID(payload["sub"])
        except (KeyError, ValueError):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session.")

        user = db.get(User, user_id)
        if user is None or not user.is_active:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account not found or inactive.")

        if payload.get("stage") == "authenticated":
            now = datetime.datetime.now(datetime.timezone.utc)
            if user.last_active_at is not None and now - user.last_active_at > _INACTIVITY_TIMEOUT:
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired due to inactivity. Sign in again.")
            user.last_active_at = now
            db.commit()

        return user

    return dependency


require_pending_enrollment = require_stage("pending_enrollment")
require_face_required = require_stage("face_required")
require_authenticated = require_stage("authenticated")
