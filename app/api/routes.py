from fastapi import APIRouter, UploadFile, File

router = APIRouter()


@router.get("/")
async def root():
    return {
        "status": "success",
        "message": "Speech API is running 🚀",
    }


@router.get("/health")
async def health():
    return {
        "status": "healthy",
    }


@router.post("/transcribe")
async def transcribe_audio(
    audio: UploadFile = File(...)
):
    return {
        "filename": audio.filename,
        "content_type": audio.content_type,
    }