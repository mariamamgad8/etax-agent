from pathlib import Path
import shutil
import uuid

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.services.conversation_service import conversation_service


app = FastAPI(
    title="Taya Voice Assistant API",
    version="1.0.0",
)


BASE_DIR = Path(
    __file__
).resolve().parent.parent

FRONTEND_DIR = (
    BASE_DIR / "app" / "frontend"
)

INPUT_DIR = (
    BASE_DIR / "temp" / "input"
)

AUDIO_DIR = (
    BASE_DIR / "temp" / "audio"
)

INPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

AUDIO_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


app.mount(
    "/frontend",
    StaticFiles(
        directory=FRONTEND_DIR
    ),
    name="frontend",
)


@app.get("/")
async def root():

    return FileResponse(
        FRONTEND_DIR / "index.html"
    )


@app.get("/health")
async def health():

    return {
        "status": "healthy",
        "service": "taya-voice-assistant",
    }


@app.post("/chat")
async def chat(
    session_id: str,
    audio: UploadFile = File(...),
):

    if not audio.filename:
        raise HTTPException(
            status_code=400,
            detail="Audio filename is required.",
        )

    suffix = Path(
        audio.filename
    ).suffix or ".wav"

    audio_path = (
        INPUT_DIR
        / f"{uuid.uuid4()}{suffix}"
    )

    try:

        with open(
            audio_path,
            "wb",
        ) as buffer:

            shutil.copyfileobj(
                audio.file,
                buffer,
            )

        result = (
            await conversation_service.process_audio(
                session_id=session_id,
                audio_path=str(
                    audio_path
                ),
            )
        )

        return result

    finally:

        try:
            audio_path.unlink(
                missing_ok=True
            )
        except Exception:
            pass


@app.get("/audio/{filename}")
async def get_audio(
    filename: str,
):

    # Prevent path traversal.
    safe_name = Path(
        filename
    ).name

    audio_path = (
        AUDIO_DIR / safe_name
    )

    if not audio_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Audio file not found.",
        )

    suffix = (
        audio_path.suffix.lower()
    )

    media_types = {
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".ogg": "audio/ogg",
        ".webm": "audio/webm",
        ".m4a": "audio/mp4",
    }

    media_type = media_types.get(
        suffix,
        "application/octet-stream",
    )

    return FileResponse(
        audio_path,
        media_type=media_type,
        filename=safe_name,
    )