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

# Every Gemini key currently on hand, from however many of these env vars are
# set. No fixed naming scheme — new keys get added one at a time under
# whatever ad-hoc label was used when they were obtained (GEMINI_API_KEY_1,
# mam_/sal_/far_/saf_GEMINI_API_KEY, ...) — so this is an explicit, growable
# list of the var NAMES, not a dynamic scan of the whole environment (keeps
# it obvious which vars actually matter, and easy to extend as more arrive).
# GEMINI_KEY_NAMES maps each key's VALUE back to the var it came from, so a
# per-key failure can be logged as e.g. "mam_GEMINI_API_KEY" instead of a
# meaningless index — providers/llm.py and providers/tts.py both only ever
# see the key string itself, never which of these vars supplied it.
_GEMINI_KEY_ENV_VARS = [
    "GEMINI_API_KEY",
    "GEMINI_API_KEY_1",
    "mam_GEMINI_API_KEY",
    "sal_GEMINI_API_KEY",
    "far_GEMINI_API_KEY",
    "saf_GEMINI_API_KEY",
]
GEMINI_KEY_NAMES: dict[str, str] = {
    value: name for name in _GEMINI_KEY_ENV_VARS if (value := os.getenv(name, "").strip())
}
_ALL_GEMINI_KEYS = list(GEMINI_KEY_NAMES)  # de-duplicated, first-seen order (dict preserves insertion order)


def gemini_key_label(key: str) -> str:
    """A safe-to-log identifier for a Gemini key — its source env var name when
    known, otherwise a masked suffix (never the full key)."""
    name = GEMINI_KEY_NAMES.get(key)
    if name:
        return name
    return f"key ending in ...{key[-4:]}" if len(key) >= 4 else "unknown key"


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
# All available Gemini keys, rotated through independently of TTS's own pool
# below (each service tries the whole pool on its own — see providers/llm.py)
# — previously the LLM's Gemini calls used a single hardcoded key with no
# fallback at all, unlike TTS. Override with GEMINI_LLM_API_KEYS explicitly
# if a different subset is ever wanted.
GEMINI_LLM_API_KEYS = _split_csv("GEMINI_LLM_API_KEYS", _ALL_GEMINI_KEYS)

# --- Provider management ---
# Kept deliberately short: this only ever gates trying the SAME provider
# again too soon after it just failed — the fallback chain has already moved
# on to the next provider within the same request regardless of this value.
# A long cooldown (formerly 60s) just meant a provider that recovered
# quickly stayed skipped for a full minute for no benefit.
MODEL_COOLDOWN_SECONDS = int(os.getenv("MODEL_COOLDOWN_SECONDS", "2"))

# --- TTS ---
# Gemini is the default/primary provider — confirmed live as the one that
# actually serves audio for this project's accounts (see providers/tts.py's
# module docstring for the ElevenLabs plan limitation that ruled it out as
# the first attempt). Piper (local ONNX voices) was removed after live
# ONNXRuntime crashes on real input ("Reshape node ... dimension with value
# zero exceeds the dimension size of the input tensor") — not just a
# fallback-order demotion, the code path is gone entirely (see
# providers/tts.py). edge_tts is the second attempt, ElevenLabs stays
# configurable as a last resort rather than deleted, per this project's
# fallback-abstraction convention — swap TTS_PROVIDER_ORDER to reorder/drop
# providers without code changes.
TTS_PROVIDER_ORDER = _split_csv("TTS_PROVIDER_ORDER", ["gemini", "edge_tts", "elevenlabs"])

# Gemini's free TTS quota is small (10 requests/day, confirmed live) and
# shared across however many keys are configured here. Multiple comma-
# separated keys let providers/tts.py rotate to the next one when a key is
# rate-limited/exhausted rather than falling through to edge_tts immediately
# — only once every key is exhausted does the provider itself fail. Defaults
# to the same full key pool the LLM uses (see GEMINI_LLM_API_KEYS above) —
# override with GEMINI_TTS_API_KEYS explicitly for a different subset.
GEMINI_TTS_API_KEYS = _split_csv("GEMINI_TTS_API_KEYS", _ALL_GEMINI_KEYS)
GEMINI_TTS_MODEL = os.getenv("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts")
GEMINI_TTS_VOICE = os.getenv("GEMINI_TTS_VOICE", "Kore")

EDGE_TTS_VOICE_EN = os.getenv("EDGE_TTS_VOICE_EN", "en-US-AriaNeural")
EDGE_TTS_VOICE_AR = os.getenv("EDGE_TTS_VOICE_AR", "ar-EG-SalmaNeural")
ELEVENLABS_MODEL = os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "")

# --- database_query: tax schema lives in the same Postgres DB as auth (app.config.DATABASE_URL) ---
# openai/gpt-oss-20b specifically — llama-3.3-70b-versatile reliably wraps
# its SQL in ```sql fences that break execution; gpt-oss-20b doesn't. See
# backend/app/chat/db/query_chain.py.
SQL_CHAIN_MODEL = os.getenv("SQL_CHAIN_MODEL", "openai/gpt-oss-20b")
