"""
Central text-to-speech access point, mirroring llm.py/stt.py's shape: routes
call synthesize_speech(text) and this module handles provider fallback
(ElevenLabs -> Gemini by default, TTS_PROVIDER_ORDER) and cooldown.

Both providers accept plain multilingual text directly — no separate
language parameter is needed, since ElevenLabs' eleven_multilingual_v2 model
and Gemini's TTS models both infer the spoken language from the input text
itself (confirmed live for both English and Arabic against Gemini TTS).

NOTE (live-tested, not guessed): the ElevenLabs key configured in this
project's .env is missing the `voices_read` permission and 402s on any
stock/library voice — "Free users cannot use library voices via the API.
Please upgrade your subscription to use this voice." ElevenLabs stays first
in TTS_PROVIDER_ORDER because that's this project's stated preference, and it
will start working the moment the account has an eligible voice/plan; Gemini
is what actually serves audio today, via the fallback below.

Gemini's TTS models return raw 16-bit PCM audio (confirmed live: mime type
"audio/L16;codec=pcm;rate=24000"), not a playable container — _pcm_to_wav
wraps it in a WAV header before it's returned to the caller.
"""
import io
import logging
import wave

import httpx
from google import genai
from google.genai import types as genai_types

from app.chat.config import (
    ELEVENLABS_API_KEY,
    ELEVENLABS_MODEL,
    ELEVENLABS_VOICE_ID,
    GEMINI_API_KEY,
    GEMINI_TTS_MODEL,
    GEMINI_TTS_VOICE,
    MODEL_COOLDOWN_SECONDS,
    TTS_PROVIDER_ORDER,
)
from app.chat.providers.base import AllProvidersExhausted, CooldownTracker, ProviderError

logger = logging.getLogger(__name__)

_cooldown = CooldownTracker(MODEL_COOLDOWN_SECONDS)

_gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# ElevenLabs' public "Rachel" voice — used only if ELEVENLABS_VOICE_ID isn't
# set; a library voice still requires a paid plan per the module docstring.
_ELEVENLABS_DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"


def _synthesize_elevenlabs(text: str) -> tuple[bytes, str]:
    if not ELEVENLABS_API_KEY:
        raise ProviderError("ELEVENLABS_TTS_KEY is not configured.")
    voice_id = ELEVENLABS_VOICE_ID or _ELEVENLABS_DEFAULT_VOICE_ID
    response = httpx.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        headers={"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"},
        json={"text": text, "model_id": ELEVENLABS_MODEL},
        timeout=30,
    )
    if response.status_code != 200:
        raise ProviderError(f"ElevenLabs TTS failed ({response.status_code}): {response.text[:300]}")
    return response.content, "audio/mpeg"


def _pcm_to_wav(pcm_bytes: bytes, sample_rate: int = 24000, channels: int = 1, sample_width: int = 2) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_bytes)
    return buf.getvalue()


def _synthesize_gemini(text: str) -> tuple[bytes, str]:
    if _gemini_client is None:
        raise ProviderError("GEMINI_API_KEY is not configured.")
    # Short/imperative-sounding input (e.g. "Testing the new voice.", "Ok.")
    # is sometimes read by the model as an instruction to follow rather than
    # content to speak, and it replies conversationally instead of returning
    # audio (400 "Model tried to generate text, but it should only be used
    # for TTS") — confirmed live and deterministic per input. Framing the
    # text as something to read aloud fixes it; confirmed live across short
    # text, questions, and Arabic.
    response = _gemini_client.models.generate_content(
        model=GEMINI_TTS_MODEL,
        contents=f"Read this aloud, with no commentary: {text}",
        config=genai_types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=genai_types.SpeechConfig(
                voice_config=genai_types.VoiceConfig(
                    prebuilt_voice_config=genai_types.PrebuiltVoiceConfig(voice_name=GEMINI_TTS_VOICE)
                )
            ),
        ),
    )
    candidates = response.candidates or []
    parts = candidates[0].content.parts if candidates and candidates[0].content else []
    inline_data = parts[0].inline_data if parts else None
    if inline_data is None or not inline_data.data:
        raise ProviderError("Gemini TTS returned no audio data.")
    return _pcm_to_wav(inline_data.data), "audio/wav"


_PROVIDERS = {"elevenlabs": _synthesize_elevenlabs, "gemini": _synthesize_gemini}


def synthesize_speech(text: str) -> tuple[bytes, str]:
    """Text-to-speech with provider fallback and cooldown. Returns (audio_bytes, mime_type)."""
    last_error: Exception | None = None
    for provider in TTS_PROVIDER_ORDER:
        fn = _PROVIDERS.get(provider)
        if fn is None:
            logger.warning("Unknown TTS provider in TTS_PROVIDER_ORDER: %s", provider)
            continue
        if _cooldown.is_cooling_down(provider):
            logger.info("[TTS] skipping %s (cooling down after a recent failure)", provider)
            continue
        try:
            audio_bytes, mime_type = fn(text)
            logger.info("[TTS] synthesized %d chars -> %d bytes via %s", len(text), len(audio_bytes), provider)
            return audio_bytes, mime_type
        except Exception as exc:  # noqa: BLE001 - any provider failure just moves to the next candidate
            logger.warning("[TTS] call failed on %s: %s", provider, exc)
            _cooldown.mark(provider)
            last_error = exc
    raise AllProvidersExhausted(f"Every configured TTS provider failed. Last error: {last_error}")
