"""
Central text-to-speech access point, mirroring llm.py/stt.py's shape: routes
call synthesize_speech(text) and this module handles provider fallback
(Gemini -> edge_tts -> ElevenLabs by default, TTS_PROVIDER_ORDER) and
cooldown.

Gemini is the default/primary provider: it's what actually serves audio
today (see below), and it accepts plain multilingual text directly — no
separate language parameter, since its TTS models infer the spoken language
from the input text itself (confirmed live for both English and Arabic).
edge_tts (Microsoft Edge's free online voices) is the fallback.

Piper (local/offline ONNX voices) was tried as a fast, rate-limit-proof
fallback but removed after a live, reproducible crash: ONNXRuntime's Reshape
kernel raised "the dimension with value zero exceeds the dimension size of
the input tensor" on real (non-trivial) input text — not an occasional
flake, a real defect in that path. Rather than debug a third-party ONNX
model's internals, it was dropped from the fallback chain entirely; see this
module's git history / the project's CLAUDE.md for the prior integration if
it's ever worth revisiting with a different voice model.

NOTE (live-tested, not guessed): the ElevenLabs key configured in this
project's .env is missing the `voices_read` permission and 402s on any
stock/library voice — "Free users cannot use library voices via the API.
Please upgrade your subscription to use this voice." ElevenLabs is kept
configurable as a last-resort fallback (not deleted — swap TTS_PROVIDER_ORDER
to reorder/drop providers without a code change) rather than attempted first,
since an unnecessary request to an account known to reject it just wastes a
round trip ahead of a provider that actually works.

Gemini's TTS models return raw 16-bit PCM audio (confirmed live: mime type
"audio/L16;codec=pcm;rate=24000"), not a playable container — _pcm_to_wav
wraps it in a WAV header before it's returned to the caller.

Fallback latency: the google-genai SDK retries a failing request itself, by
default, up to 5 attempts with exponential backoff (1s, 2s, 4s, 8s...) on
429/5xx — confirmed live via HttpRetryOptions' own defaults. Against a
rate-limited free-tier key (exactly the common case here) that added ~15s of
pure retry delay INSIDE a single provider attempt before this module's own
fallback loop ever got a chance to move on. Each Gemini client below is
built with retry_options=HttpRetryOptions(attempts=1) (no SDK-level retries
— this module's provider/key fallback already covers that) and an explicit
timeout, so a failing key fails fast instead of slow.
"""
import asyncio
import io
import logging
import time
import wave

import edge_tts
import httpx
from google import genai
from google.genai import types as genai_types

from app.chat.config import (
    EDGE_TTS_VOICE_AR,
    EDGE_TTS_VOICE_EN,
    ELEVENLABS_API_KEY,
    ELEVENLABS_MODEL,
    ELEVENLABS_VOICE_ID,
    GEMINI_TTS_API_KEYS,
    GEMINI_TTS_MODEL,
    GEMINI_TTS_VOICE,
    MODEL_COOLDOWN_SECONDS,
    TTS_PROVIDER_ORDER,
)
from app.chat.providers.base import AllProvidersExhausted, CooldownTracker, ProviderError
from app.chat.responses import detect_response_language

logger = logging.getLogger(__name__)

_cooldown = CooldownTracker(MODEL_COOLDOWN_SECONDS)

# No SDK-level retries (see module docstring) and a tight timeout, so a
# rate-limited/unresponsive key fails in ~10s, not ~15s of backoff on top of
# however long the request itself takes.
_GEMINI_HTTP_OPTIONS = genai_types.HttpOptions(
    timeout=10_000,  # milliseconds
    retry_options=genai_types.HttpRetryOptions(attempts=1),
)
_gemini_clients = [
    genai.Client(api_key=key, http_options=_GEMINI_HTTP_OPTIONS) for key in GEMINI_TTS_API_KEYS
]

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
        timeout=10,
    )
    if response.status_code != 200:
        raise ProviderError(f"ElevenLabs TTS failed ({response.status_code}): {response.text[:300]}")
    return response.content, "audio/mpeg"


def _pcm_to_wav(pcm_bytes: bytes, sample_rate: int, channels: int = 1, sample_width: int = 2) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_bytes)
    return buf.getvalue()


def _synthesize_gemini(text: str) -> tuple[bytes, str]:
    if not _gemini_clients:
        raise ProviderError("No Gemini API key is configured for TTS (GEMINI_TTS_API_KEYS/GEMINI_API_KEY).")
    # Short/imperative-sounding input (e.g. "Testing the new voice.", "Ok.")
    # is sometimes read by the model as an instruction to follow rather than
    # content to speak, and it replies conversationally instead of returning
    # audio (400 "Model tried to generate text, but it should only be used
    # for TTS") — confirmed live and deterministic per input. Framing the
    # text as something to read aloud fixes it; confirmed live across short
    # text, questions, and Arabic.
    prompt = f"Read this aloud, with no commentary: {text}"
    config = genai_types.GenerateContentConfig(
        response_modalities=["AUDIO"],
        speech_config=genai_types.SpeechConfig(
            voice_config=genai_types.VoiceConfig(
                prebuilt_voice_config=genai_types.PrebuiltVoiceConfig(voice_name=GEMINI_TTS_VOICE)
            )
        ),
    )

    last_exc: Exception | None = None
    for i, client in enumerate(_gemini_clients):
        try:
            response = client.models.generate_content(model=GEMINI_TTS_MODEL, contents=prompt, config=config)
            candidates = response.candidates or []
            parts = candidates[0].content.parts if candidates and candidates[0].content else []
            inline_data = parts[0].inline_data if parts else None
            if inline_data is None or not inline_data.data:
                raise ProviderError("Gemini TTS returned no audio data.")
            return _pcm_to_wav(inline_data.data, sample_rate=24000), "audio/wav"
        except Exception as exc:  # noqa: BLE001 - try the next key before giving up on Gemini entirely
            logger.warning("[TTS] gemini key #%d/%d failed: %s", i + 1, len(_gemini_clients), exc)
            last_exc = exc
    raise ProviderError(f"All {len(_gemini_clients)} configured Gemini TTS key(s) failed. Last error: {last_exc}")


async def _edge_tts_stream(text: str, voice: str) -> bytes:
    communicate = edge_tts.Communicate(text, voice)
    chunks = bytearray()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            chunks.extend(chunk["data"])
    return bytes(chunks)


def _synthesize_edge_tts(text: str) -> tuple[bytes, str]:
    # edge_tts has no single multilingual voice like Gemini/ElevenLabs — its
    # voices are per-language, so the same deterministic detector the rest of
    # the chatbot uses picks the matching one here rather than guessing again.
    voice = EDGE_TTS_VOICE_AR if detect_response_language(text) == "ar" else EDGE_TTS_VOICE_EN
    audio_bytes = asyncio.run(_edge_tts_stream(text, voice))
    if not audio_bytes:
        raise ProviderError("edge_tts returned no audio data.")
    return audio_bytes, "audio/mpeg"


_PROVIDERS = {
    "gemini": _synthesize_gemini,
    "edge_tts": _synthesize_edge_tts,
    "elevenlabs": _synthesize_elevenlabs,
}


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
        started = time.perf_counter()
        try:
            audio_bytes, mime_type = fn(text)
            latency_ms = (time.perf_counter() - started) * 1000
            logger.info(
                "[TTS] synthesized %d chars -> %d bytes via %s in %.0fms",
                len(text), len(audio_bytes), provider, latency_ms,
            )
            return audio_bytes, mime_type
        except Exception as exc:  # noqa: BLE001 - any provider failure just moves to the next candidate
            latency_ms = (time.perf_counter() - started) * 1000
            logger.warning("[TTS] call failed on %s after %.0fms: %s", provider, latency_ms, exc)
            _cooldown.mark(provider)
            last_error = exc
    raise AllProvidersExhausted(f"Every configured TTS provider failed. Last error: {last_error}")
