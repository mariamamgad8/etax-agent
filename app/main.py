from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import db, face_engine, liveness_engine
from app.config import MATCH_THRESHOLD

app = FastAPI(title="Face Recognition Service (ArcFace/InsightFace + pgvector)")

# Live-camera capture UI. Served at /ui so it doesn't collide with the API
# routes below (which stay at the root path).
app.mount("/ui", StaticFiles(directory="app/static", html=True), name="ui")


class RecognizeResponse(BaseModel):
    status: str  # "known" | "unknown"
    name: str | None = None
    person_id: int | None = None
    similarity: float | None = None
    liveness_confidence: float


class RegisterResponse(BaseModel):
    person_id: int
    name: str
    liveness_confidence: float


@app.on_event("startup")
def on_startup():
    db.init_db()


@app.get("/health")
def health():
    return {"ok": True}


def _detect_and_verify_live(image_bytes: bytes):
    """
    Shared pipeline for both endpoints: detect the face, then REQUIRE it to
    pass the liveness check before any identity logic runs. Raises
    HTTPException (422 no face / 403 spoof suspected) on failure.

    This is a hard gate, not a soft signal: a failed liveness check never
    reaches the embedding-matching code below it, in either endpoint.
    """
    try:
        img_bgr, face = face_engine.detect(image_bytes)
    except face_engine.NoFaceDetected:
        raise HTTPException(status_code=422, detail="No face detected in the image.")

    is_live, confidence = liveness_engine.check_liveness(img_bgr, face.bbox)
    if not is_live:
        raise HTTPException(
            status_code=403,
            detail=f"Liveness check failed (confidence={confidence:.3f}). "
            "This looks like a photo, screen, or other spoof rather than a live face.",
        )
    return face, confidence


@app.post("/recognize", response_model=RecognizeResponse)
async def recognize(image: UploadFile = File(...)):
    """
    Upload a single face photo. Returns the matching enrolled person if the
    best match's cosine similarity clears MATCH_THRESHOLD, otherwise "unknown"
    so the caller (voice agent / frontend) can trigger enrollment instead.

    Every call is first gated by a liveness check — see _detect_and_verify_live.
    """
    image_bytes = await image.read()
    face, liveness_confidence = await run_in_threadpool(_detect_and_verify_live, image_bytes)
    embedding = face.normed_embedding.astype("float32")

    match = await run_in_threadpool(db.find_closest, embedding)
    if match is None:
        return RecognizeResponse(status="unknown", liveness_confidence=liveness_confidence)

    person, similarity = match
    if similarity >= MATCH_THRESHOLD:
        return RecognizeResponse(
            status="known",
            name=person.name,
            person_id=person.id,
            similarity=similarity,
            liveness_confidence=liveness_confidence,
        )
    return RecognizeResponse(
        status="unknown", similarity=similarity, liveness_confidence=liveness_confidence
    )


@app.post("/register", response_model=RegisterResponse)
async def register(name: str = Form(...), image: UploadFile = File(...)):
    """
    Enroll a new person: stores their name + face embedding.
    Call this after /recognize returns "unknown" and the user has confirmed
    their name (e.g. via the voice agent).

    Also liveness-gated: you cannot enroll a spoofed face, which matters
    just as much as gating /recognize — an attacker enrolling a photo of
    someone else would otherwise plant a false identity in the database.
    """
    image_bytes = await image.read()
    face, liveness_confidence = await run_in_threadpool(_detect_and_verify_live, image_bytes)
    embedding = face.normed_embedding.astype("float32")

    # Refuse to enroll if this face already matches someone in the DB, to
    # avoid duplicate identities.
    existing = await run_in_threadpool(db.find_closest, embedding)
    if existing is not None:
        person, similarity = existing
        if similarity >= MATCH_THRESHOLD:
            raise HTTPException(
                status_code=409,
                detail=f"This face is already enrolled as '{person.name}' (similarity={similarity:.3f}).",
            )

    person_id = await run_in_threadpool(db.register_person, name, embedding)
    return RegisterResponse(person_id=person_id, name=name, liveness_confidence=liveness_confidence)
