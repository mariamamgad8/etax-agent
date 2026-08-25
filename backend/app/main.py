import logging

# Configured before any app import that grabs a logger, and with force=True
# since uvicorn's own startup may have already touched the root handlers —
# without this, our logger.info(...) calls across app/chat/* are silently
# dropped (root logger defaults to WARNING with no handler of its own).
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
    datefmt="%H:%M:%S",
    force=True,
)
# These third-party HTTP clients log every request at INFO and drown out the
# actual pipeline steps (intent, LLM model used, SQL, STT) — keep them quiet.
for _noisy_logger in ("httpx", "httpcore", "urllib3", "google_genai", "groq"):
    logging.getLogger(_noisy_logger).setLevel(logging.WARNING)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth.routes import router as auth_router
from app.chat.config import (
    COHERE_API_KEY,
    ELEVENLABS_API_KEY,
    GEMINI_API_KEY,
    GEMINI_LLM_MODELS,
    GROQ_API_KEY,
    GROQ_LLM_MODELS,
    LLM_PROVIDER_ORDER,
    STT_DETECT_PROVIDER,
    STT_TRANSCRIBE_PROVIDER,
    TTS_PROVIDER_ORDER,
)
from app.chat.db.seed import ensure_ready as ensure_tax_data_ready
from app.chat.routes import router as chat_router
from app.config import ALLOWED_ORIGINS
from app.database.db import init_db
from app.face.routes import router as face_router

logger = logging.getLogger(__name__)

app = FastAPI(title="eTax AI-Assisted Tax Platform API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(face_router)
app.include_router(chat_router)


def _key_status(name: str, value: str) -> str:
    return f"{name}={'set' if value else 'MISSING'}"


@app.on_event("startup")
def on_startup():
    init_db()
    ensure_tax_data_ready()

    logger.info(
        "[STARTUP] API keys: %s",
        " ".join(
            _key_status(n, v)
            for n, v in (
                ("COHERE", COHERE_API_KEY),
                ("GROQ", GROQ_API_KEY),
                ("GEMINI", GEMINI_API_KEY),
                ("ELEVENLABS", ELEVENLABS_API_KEY),
            )
        ),
    )
    logger.info(
        "[STARTUP] LLM fallback chain: %s",
        " -> ".join(
            f"{p}:{m}"
            for p in LLM_PROVIDER_ORDER
            for m in (GROQ_LLM_MODELS if p == "groq" else GEMINI_LLM_MODELS if p == "gemini" else [])
        ),
    )
    logger.info(
        "[STARTUP] STT pipeline: detect language via %s -> transcribe via %s",
        STT_DETECT_PROVIDER,
        STT_TRANSCRIBE_PROVIDER,
    )
    logger.info("[STARTUP] TTS fallback chain: %s", " -> ".join(TTS_PROVIDER_ORDER))


@app.get("/health")
def health():
    return {"ok": True}
