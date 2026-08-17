"""
Central speech-to-text access point, called via transcribe_audio(...).

This is a two-role pipeline, not a simple ordered fallback list — see
config.py's STT_DETECT_PROVIDER/STT_TRANSCRIBE_PROVIDER comment for why:
Cohere Transcribe requires an explicit ISO-639-1 language and has no
auto-detect mode, while Groq Whisper reliably auto-detects the spoken
language via response_format="verbose_json". So every request first runs the
detector (Groq) to find the language, then calls the transcriber (Cohere)
with that language for the transcript actually returned — a user speaking
English, Arabic, or switching between them across messages still gets an
accurate transcript instead of silently-wrong text from a fixed/mismatched
language hint. If the transcriber is unavailable, the detector's own
transcript is used directly rather than wasting a second call.

The returned transcript is used as-is. Numbers, taxpayer IDs, and mixed
Arabic/English tax terminology are never normalized or rewritten here — that
preserves exactly what the user said for the LLM layer to work from.
"""
import io
import logging

import cohere
from groq import Groq

from app.chat.config import (
    COHERE_API_KEY,
    COHERE_STT_LANGUAGE,
    COHERE_STT_MODEL,
    GROQ_API_KEY,
    GROQ_STT_MODEL,
    GROQ_STT_PROMPT,
    MODEL_COOLDOWN_SECONDS,
    STT_DETECT_PROVIDER,
    STT_TRANSCRIBE_PROVIDER,
)
from app.chat.providers.base import AllProvidersExhausted, CooldownTracker, ProviderError

logger = logging.getLogger(__name__)

_cooldown = CooldownTracker(MODEL_COOLDOWN_SECONDS)

_cohere_client = cohere.ClientV2(api_key=COHERE_API_KEY) if COHERE_API_KEY else None
_groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# Cohere Transcribe's fixed language list (confirmed live via its own 400
# error message) mapped from Whisper's full language names — the vocabulary
# Groq's verbose_json response gives us (e.g. "Arabic", "English"), lowercased.
_WHISPER_NAME_TO_COHERE_CODE = {
    "english": "en",
    "french": "fr",
    "german": "de",
    "spanish": "es",
    "portuguese": "pt",
    "italian": "it",
    "dutch": "nl",
    "polish": "pl",
    "greek": "el",
    "arabic": "ar",
    "korean": "ko",
    "japanese": "ja",
    "vietnamese": "vi",
    "chinese": "zh",
}


def _detect_language_groq(audio_bytes: bytes, filename: str) -> tuple[str, str]:
    """Returns (transcript, cohere_language_code) using Groq Whisper's own language detection."""
    if _groq_client is None:
        raise ProviderError("GROQ_API_KEY is not configured.")
    result = _groq_client.audio.transcriptions.create(
        model=GROQ_STT_MODEL,
        file=(filename, io.BytesIO(audio_bytes)),
        prompt=GROQ_STT_PROMPT,
        response_format="verbose_json",
    )
    text = getattr(result, "text", None)
    if not text:
        raise ProviderError("Groq transcription returned no text.")
    detected = (getattr(result, "language", "") or "").strip().lower()
    code = _WHISPER_NAME_TO_COHERE_CODE.get(detected, COHERE_STT_LANGUAGE)
    logger.info(
        "[STT] groq detected language=%s -> cohere code=%s%s",
        detected or "unknown",
        code,
        "" if detected in _WHISPER_NAME_TO_COHERE_CODE else " (unmapped, using COHERE_STT_LANGUAGE default)",
    )
    return text, code


def _transcribe_cohere(audio_bytes: bytes, filename: str, language: str) -> str:
    if _cohere_client is None:
        raise ProviderError("COHERE_API_KEY is not configured.")
    result = _cohere_client.audio.transcriptions.create(
        model=COHERE_STT_MODEL,
        language=language,
        file=(filename, io.BytesIO(audio_bytes)),
    )
    text = getattr(result, "text", None)
    if not text:
        raise ProviderError("Cohere transcription returned no text.")
    return text


_DETECTORS = {"groq": _detect_language_groq}


def transcribe_audio(audio_bytes: bytes, filename: str = "audio.wav") -> str:
    """Detects the spoken language, then transcribes with that language, with graceful fallback."""
    detected_text: str | None = None
    language = COHERE_STT_LANGUAGE

    detect_fn = _DETECTORS.get(STT_DETECT_PROVIDER)
    if detect_fn is None:
        logger.warning("Unknown STT_DETECT_PROVIDER: %s", STT_DETECT_PROVIDER)
    elif _cooldown.is_cooling_down(STT_DETECT_PROVIDER):
        logger.info("[STT] skipping %s detection (cooling down after a recent failure)", STT_DETECT_PROVIDER)
    else:
        try:
            detected_text, language = detect_fn(audio_bytes, filename)
        except Exception as exc:  # noqa: BLE001 - detection failure still allows a transcribe-only attempt below
            logger.warning("[STT] language detection failed on %s: %s", STT_DETECT_PROVIDER, exc)
            _cooldown.mark(STT_DETECT_PROVIDER)

    if STT_TRANSCRIBE_PROVIDER == STT_DETECT_PROVIDER:
        # Same provider for both roles (e.g. Groq-only setups) — the
        # detection pass already produced the transcript, no second call.
        if detected_text is not None:
            return detected_text
    elif STT_TRANSCRIBE_PROVIDER == "cohere":
        if _cooldown.is_cooling_down("cohere"):
            logger.info("[STT] skipping cohere transcription (cooling down after a recent failure)")
        else:
            try:
                text = _transcribe_cohere(audio_bytes, filename, language)
                logger.info("[STT] transcribed by cohere (language=%s) -> %r", language, text)
                return text
            except Exception as exc:  # noqa: BLE001
                logger.warning("[STT] call failed on cohere: %s", exc)
                _cooldown.mark("cohere")
    else:
        logger.warning("Unknown STT_TRANSCRIBE_PROVIDER: %s", STT_TRANSCRIBE_PROVIDER)

    if detected_text is not None:
        logger.info("[STT] using %s's own transcript (transcriber unavailable) -> %r", STT_DETECT_PROVIDER, detected_text)
        return detected_text

    raise AllProvidersExhausted("Every configured STT provider failed (language detection and transcription both unavailable).")
