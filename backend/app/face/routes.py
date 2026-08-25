import datetime
import logging
import numpy as np
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import require_face_required, require_pending_enrollment
from app.auth.security import create_token
from app.config import MATCH_THRESHOLD, SESSION_TOKEN_TTL_MINUTES
from app.database.db import get_db
from app.database.models import FaceProfile, User
from app.face import face_engine, liveness_engine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/face", tags=["face"])


class FaceStageResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    stage: str


def _detect_and_verify_live(image_bytes: bytes):
    """
    Shared pipeline for enroll and verify: detect the face, then REQUIRE it
    to pass the liveness check before any identity logic runs. A failed
    liveness check never reaches the embedding code below it.
    """
    try:
        img_bgr, face = face_engine.detect(image_bytes)
    except face_engine.NoFaceDetected:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "No face detected. Position your face inside the frame.",
        )

    is_live, confidence = liveness_engine.check_liveness(img_bgr, face.bbox)
    if not is_live:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Liveness check failed. This looks like a photo, screen, or other spoof rather than a live face.",
        )
    return face, confidence


@router.post("/enroll", response_model=FaceStageResponse)
async def enroll(
    image: UploadFile = File(...),
    user: User = Depends(require_pending_enrollment),
    db: Session = Depends(get_db),
):
    logger.info(f"FACE ENROLLMENT REQUEST: user_id={user.id}, username={user.username}")
    
    existing = db.execute(
        select(FaceProfile).where(FaceProfile.user_id == user.id)
    ).scalar_one_or_none()
    if existing is not None:
        logger.warning(f"ENROLLMENT FAILED: Face already enrolled for user_id={user.id}")
        raise HTTPException(status.HTTP_409_CONFLICT, "A face is already enrolled for this account.")

    logger.info(f"📷 Reading image data for user_id={user.id}")
    image_bytes = await image.read()
    
    logger.info(f"Detecting face for user_id={user.id}")
    face, _confidence = await run_in_threadpool(_detect_and_verify_live, image_bytes)
    
    logger.info(f"Face detected and liveness verified for user_id={user.id}")
    embedding = face.normed_embedding.astype("float32")
    
    logger.info(f"Saving face embedding (512-dim vector) to database for user_id={user.id}")
    profile = FaceProfile(user_id=user.id, embedding=embedding.tolist())
    db.add(profile)
    db.commit()
    logger.info(f" FACE PROFILE SAVED: user_id={user.id}")

    user.last_active_at = datetime.datetime.now(datetime.timezone.utc)
    db.commit()

    token = create_token(str(user.id), "authenticated", SESSION_TOKEN_TTL_MINUTES)
    logger.info(f" AUTHENTICATED TOKEN ISSUED: user_id={user.id}")

    return FaceStageResponse(access_token=token, stage="authenticated")


@router.post("/verify", response_model=FaceStageResponse)
async def verify(
    image: UploadFile = File(...),
    user: User = Depends(require_face_required),
    db: Session = Depends(get_db),
):
    logger.info(f"FACE VERIFICATION REQUEST: user_id={user.id}, username={user.username}")
    
    # The user is already known from the token issued at password login —
    # this compares against that one account's embedding only, never a
    # nearest-neighbor search across every enrolled person.
    profile = db.execute(
        select(FaceProfile).where(FaceProfile.user_id == user.id)
    ).scalar_one_or_none()
    if profile is None:
        logger.error(f"VERIFICATION FAILED: No enrolled face found for user_id={user.id}")
        raise HTTPException(status.HTTP_409_CONFLICT, "No enrolled face found for this account.")

    logger.info(f"Reading image data for user_id={user.id}")
    image_bytes = await image.read()
    
    logger.info(f"Detecting face for verification for user_id={user.id}")
    face, _confidence = await run_in_threadpool(_detect_and_verify_live, image_bytes)
    
    logger.info(f"Face detected and liveness verified for user_id={user.id}")
    captured = face.normed_embedding.astype("float32")
    enrolled = np.array(profile.embedding, dtype="float32")
    similarity = float(np.dot(captured, enrolled))
    
    logger.info(f"FACE SIMILARITY SCORE: user_id={user.id}, similarity={similarity:.4f}, threshold={MATCH_THRESHOLD}")

    if similarity < MATCH_THRESHOLD:
        logger.warning(f"VERIFICATION FAILED: Face match score too low ({similarity:.4f}) for user_id={user.id}")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Face does not match this account.")

    logger.info(f" FACE VERIFIED: user_id={user.id}, similarity={similarity:.4f}")

    user.last_active_at = datetime.datetime.now(datetime.timezone.utc)
    db.commit()

    token = create_token(str(user.id), "authenticated", SESSION_TOKEN_TTL_MINUTES)
    logger.info(f"AUTHENTICATED TOKEN ISSUED: user_id={user.id}")
    
    return FaceStageResponse(access_token=token, stage="authenticated")
