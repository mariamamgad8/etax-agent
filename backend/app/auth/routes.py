import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import schemas, service
from app.auth.dependencies import require_authenticated
from app.auth.security import create_token, hash_password, verify_password
from app.config import FACE_ENROLLMENT_TOKEN_TTL_MINUTES, FACE_VERIFICATION_TOKEN_TTL_MINUTES
from app.database.db import get_db
from app.database.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


def _user_out(user: User) -> schemas.UserOut:
    return schemas.UserOut(
        id=user.id,
        full_name=user.full_name,
        username=user.username,
        email=user.email,
        is_active=user.is_active,
        face_enrolled=user.face_profile is not None,
    )


@router.post("/signup", response_model=schemas.AuthStageResponse, status_code=status.HTTP_201_CREATED)
def signup(payload: schemas.SignupRequest, db: Session = Depends(get_db)):
    logger.info(f" SIGNUP REQUEST: username={payload.username}, email={payload.email}")
    
    if service.username_or_email_taken(db, payload.username, payload.email):
        logger.warning(f"SIGNUP FAILED: username or email already taken - {payload.username}")
        raise HTTPException(status.HTTP_409_CONFLICT, "That username or email is already registered.")

    user = User(
        full_name=payload.full_name.strip(),
        username=payload.username.strip(),
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    logger.info(f" USER CREATED: id={user.id}, username={user.username}")

    token = create_token(str(user.id), "pending_enrollment", FACE_ENROLLMENT_TOKEN_TTL_MINUTES)
    logger.info(f" TOKEN ISSUED: user_id={user.id}, stage=pending_enrollment")
    
    return schemas.AuthStageResponse(access_token=token, stage="pending_enrollment", user=_user_out(user))


@router.post("/login", response_model=schemas.AuthStageResponse)
def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    logger.info(f" LOGIN ATTEMPT: username={payload.username}")
    
    user = service.get_user_by_username_or_email(db, payload.username.strip())
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        logger.warning(f" LOGIN FAILED: invalid credentials for {payload.username}")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "The username or password is incorrect.")

    logger.info(f" PASSWORD VERIFIED: user_id={user.id}, username={user.username}")

    if user.face_profile is None:
        # Credentials are valid but enrollment was never finished — send them
        # to finish that instead of a face check that has nothing to compare against.
        logger.info(f"  FACE NOT ENROLLED YET: user_id={user.id}, redirecting to enrollment")
        token = create_token(str(user.id), "pending_enrollment", FACE_ENROLLMENT_TOKEN_TTL_MINUTES)
        return schemas.AuthStageResponse(access_token=token, stage="pending_enrollment", user=_user_out(user))

    logger.info(f" TOKEN ISSUED: user_id={user.id}, stage=face_required")
    token = create_token(str(user.id), "face_required", FACE_VERIFICATION_TOKEN_TTL_MINUTES)
    return schemas.AuthStageResponse(access_token=token, stage="face_required", user=_user_out(user))


@router.get("/me", response_model=schemas.UserOut)
def me(user: User = Depends(require_authenticated)):
    return _user_out(user)
