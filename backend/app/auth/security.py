import datetime
from typing import Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHash, VerificationError, VerifyMismatchError

from app.config import JWT_ALGORITHM, JWT_SECRET_KEY

_hasher = PasswordHasher()

# The sign-in sequence a user must climb through, one stage token at a time:
# pending_enrollment (post-signup, no face on file yet) -> face_required
# (password verified, face verification still needed) -> authenticated.
Stage = Literal["pending_enrollment", "face_required", "authenticated"]


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHash):
        return False


def create_token(user_id: str, stage: Stage, ttl_minutes: int) -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub": user_id,
        "stage": stage,
        "iat": now,
        "exp": now + datetime.timedelta(minutes=ttl_minutes),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
