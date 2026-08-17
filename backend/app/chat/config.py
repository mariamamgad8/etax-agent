import os
from pathlib import Path

from dotenv import load_dotenv

# In Docker these are all injected directly via docker-compose's `environment:`
# block. This load_dotenv call only matters for running scripts/tests locally
# outside the container, where the root .env is three levels up from here:
# backend/app/chat/config.py -> parents[0]=chat, [1]=app, [2]=backend,
# [3]=repo root. It's a no-op if that file doesn't exist (e.g. inside Docker).
load_dotenv(Path(__file__).resolve().parents[3] / ".env")


def _split_csv(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name)
    if not raw:
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


# --- API keys ---
COHERE_API_KEY = os.getenv("COHERE_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_TTS_KEY", "")

# --- Speech to text ---
# Cohere Transcribe has no auto-detect mode — confirmed live: omitting
# `language` 400s ("missing required field 'language'"), and `language="auto"`
# 400s too ("Unsupported language: 'auto'. Must be one of ['en','fr','de',
# 'es','pt','it','nl','pl','el','ar','ko','ja','vi','zh']"). Groq Whisper, on
# the other hand, reliably auto-detects the spoken language when called with
# response_format="verbose_json" (confirmed live against real English and
# Arabic audio). So STT is a two-role pipeline, not a simple ordered fallback
# list: STT_DETECT_PROVIDER runs first to find the language, then
# STT_TRANSCRIBE_PROVIDER produces the transcript actually returned to the
# user — falling back to the detector's own transcript if the transcriber is
# unavailable. See app/chat/providers/stt.py.
STT_DETECT_PROVIDER = os.getenv("STT_DETECT_PROVIDER", "groq")
STT_TRANSCRIBE_PROVIDER = os.getenv("STT_TRANSCRIBE_PROVIDER", "cohere")
COHERE_STT_MODEL = os.getenv("COHERE_STT_MODEL", "cohere-transcribe-03-2026")
# Only used if language detection itself is unavailable (detector down/not
# configured) — otherwise the detected language is used instead.
COHERE_STT_LANGUAGE = os.getenv("COHERE_STT_LANGUAGE", "ar")
GROQ_STT_MODEL = os.getenv("GROQ_STT_MODEL", "whisper-large-v3-turbo")
GROQ_STT_PROMPT = os.getenv(
    "GROQ_STT_PROMPT",
    "Tax conversation. Preserve Arabic and English words, taxpayer IDs, numbers, "
    "VAT, revenue, expenses, company names and tax terminology.",
)

# --- LLM ---
LLM_PROVIDER_ORDER = _split_csv("LLM_PROVIDER_ORDER", ["groq", "gemini"])
GROQ_LLM_MODELS = _split_csv(
    "GROQ_LLM_MODELS",
    ["openai/gpt-oss-20b", "llama-3.1-8b-instant", "llama-3.3-70b-versatile", "openai/gpt-oss-120b"],
)
GEMINI_LLM_MODELS = _split_csv("GEMINI_LLM_MODELS", ["gemini-flash-latest"])

# --- Provider management ---
MODEL_COOLDOWN_SECONDS = int(os.getenv("MODEL_COOLDOWN_SECONDS", "60"))

# --- TTS ---
# Both providers accept plain multilingual text directly with no separate
# language parameter — ElevenLabs' eleven_multilingual_v2 model and Gemini's
# TTS models both infer the spoken language from the input text itself
# (confirmed live for both English and Arabic input against Gemini TTS).
TTS_PROVIDER_ORDER = _split_csv("TTS_PROVIDER_ORDER", ["elevenlabs", "gemini"])
ELEVENLABS_MODEL = os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "")
GEMINI_TTS_MODEL = os.getenv("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts")
GEMINI_TTS_VOICE = os.getenv("GEMINI_TTS_VOICE", "Kore")

# --- Demo tax database (SQLite, synthetic data) ---
# Deliberately separate from the real Postgres auth DB — see backend/app/chat/db/.
DEMO_DB_PATH = os.getenv("DEMO_DB_PATH", "/workspace/data/demo_tax.db")
# openai/gpt-oss-20b specifically — llama-3.3-70b-versatile reliably wraps
# its SQL in ```sql fences that break execution; gpt-oss-20b doesn't. See
# backend/app/chat/db/query_chain.py.
SQL_CHAIN_MODEL = os.getenv("SQL_CHAIN_MODEL", "openai/gpt-oss-20b")
