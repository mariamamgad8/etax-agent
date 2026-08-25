"""
Feature: Gemini is the default/primary TTS provider, then Piper (local/
offline, no key, no rate limit), then edge_tts, then ElevenLabs last resort
(see providers/tts.py's module docstring for why ElevenLabs isn't attempted
first: this project's account 402s on it).

IMPORTANT: never call the real Gemini TTS API from a test. Its free-tier
quota (10 requests/day, shared across whatever keys are configured) is
consumed quickly and is needed for actual usage — every test below either
fakes _PROVIDERS["gemini"] or, for a genuine "does this produce real audio"
live check, calls a non-Gemini provider (_synthesize_piper/_synthesize_edge_tts)
directly rather than going through the default synthesize_speech() chain.

_PROVIDERS is a dict of already-bound function objects built at import time,
so tests patch dict *entries* (monkeypatch.setitem(tts._PROVIDERS, ...))
rather than the module-level _synthesize_* names — patching the name alone
wouldn't affect what's already stored in the dict.
"""
import pytest
from fastapi.testclient import TestClient

import app.chat.providers.tts as tts
from app.chat.config import TTS_PROVIDER_ORDER
from app.chat.providers.base import AllProvidersExhausted, ProviderError
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_tts_cooldown():
    """A provider failure in one test must not leave it cooling down for the next."""
    tts._cooldown._until.clear()
    yield
    tts._cooldown._until.clear()


# --- provider order ----------------------------------------------------------


def test_default_provider_order_is_gemini_first():
    assert TTS_PROVIDER_ORDER[0] == "gemini"


def test_default_provider_order_has_piper_second():
    assert TTS_PROVIDER_ORDER[1] == "piper"


def test_default_order_calls_gemini_and_never_others(monkeypatch):
    calls = []

    def fake_gemini(text):
        calls.append("gemini")
        return b"gemini-audio", "audio/wav"

    def fail_if_called(name):
        def fn(text):
            raise AssertionError(f"{name} must not be called when gemini succeeds first")
        return fn

    monkeypatch.setattr(tts, "TTS_PROVIDER_ORDER", list(TTS_PROVIDER_ORDER))
    monkeypatch.setitem(tts._PROVIDERS, "gemini", fake_gemini)
    monkeypatch.setitem(tts._PROVIDERS, "piper", fail_if_called("piper"))
    monkeypatch.setitem(tts._PROVIDERS, "edge_tts", fail_if_called("edge_tts"))
    monkeypatch.setitem(tts._PROVIDERS, "elevenlabs", fail_if_called("elevenlabs"))

    audio, mime = tts.synthesize_speech("Hello there.")

    assert calls == ["gemini"]
    assert audio == b"gemini-audio"
    assert mime == "audio/wav"


def test_gemini_failure_falls_back_to_piper_before_others(monkeypatch):
    calls = []

    def fail_gemini(text):
        calls.append("gemini")
        raise ProviderError("gemini down")

    def fake_piper(text):
        calls.append("piper")
        return b"piper-audio", "audio/wav"

    def fail_if_called(name):
        def fn(text):
            raise AssertionError(f"{name} must not be called when piper succeeds")
        return fn

    monkeypatch.setattr(tts, "TTS_PROVIDER_ORDER", list(TTS_PROVIDER_ORDER))
    monkeypatch.setitem(tts._PROVIDERS, "gemini", fail_gemini)
    monkeypatch.setitem(tts._PROVIDERS, "piper", fake_piper)
    monkeypatch.setitem(tts._PROVIDERS, "edge_tts", fail_if_called("edge_tts"))
    monkeypatch.setitem(tts._PROVIDERS, "elevenlabs", fail_if_called("elevenlabs"))

    audio, mime = tts.synthesize_speech("Hello there.")

    assert calls == ["gemini", "piper"]
    assert audio == b"piper-audio"


def test_gemini_and_piper_failure_falls_back_to_edge_tts(monkeypatch):
    calls = []

    def fail(name):
        def fn(text):
            calls.append(name)
            raise ProviderError(f"{name} down")
        return fn

    def fake_edge(text):
        calls.append("edge_tts")
        return b"edge-audio", "audio/mpeg"

    def fail_if_called(text):
        raise AssertionError("elevenlabs must not be called when edge_tts succeeds")

    monkeypatch.setattr(tts, "TTS_PROVIDER_ORDER", list(TTS_PROVIDER_ORDER))
    monkeypatch.setitem(tts._PROVIDERS, "gemini", fail("gemini"))
    monkeypatch.setitem(tts._PROVIDERS, "piper", fail("piper"))
    monkeypatch.setitem(tts._PROVIDERS, "edge_tts", fake_edge)
    monkeypatch.setitem(tts._PROVIDERS, "elevenlabs", fail_if_called)

    audio, mime = tts.synthesize_speech("Hello there.")

    assert calls == ["gemini", "piper", "edge_tts"]
    assert audio == b"edge-audio"


def test_custom_fallback_order_still_works(monkeypatch):
    """TTS_PROVIDER_ORDER is just read in sequence — any configured order is honored."""
    calls = []

    def fail_elevenlabs(text):
        calls.append("elevenlabs")
        raise ProviderError("elevenlabs unavailable")

    def fake_gemini(text):
        calls.append("gemini")
        return b"gemini-audio", "audio/wav"

    monkeypatch.setattr(tts, "TTS_PROVIDER_ORDER", ["elevenlabs", "gemini"])
    monkeypatch.setitem(tts._PROVIDERS, "elevenlabs", fail_elevenlabs)
    monkeypatch.setitem(tts._PROVIDERS, "gemini", fake_gemini)

    audio, mime = tts.synthesize_speech("Hello there.")

    assert calls == ["elevenlabs", "gemini"]
    assert audio == b"gemini-audio"


def test_all_providers_failing_raises_all_providers_exhausted(monkeypatch):
    def fail(text):
        raise ProviderError("down")

    monkeypatch.setattr(tts, "TTS_PROVIDER_ORDER", ["gemini", "piper", "edge_tts", "elevenlabs"])
    monkeypatch.setitem(tts._PROVIDERS, "gemini", fail)
    monkeypatch.setitem(tts._PROVIDERS, "piper", fail)
    monkeypatch.setitem(tts._PROVIDERS, "edge_tts", fail)
    monkeypatch.setitem(tts._PROVIDERS, "elevenlabs", fail)

    with pytest.raises(AllProvidersExhausted):
        tts.synthesize_speech("Hello there.")


# --- Gemini multi-key rotation (fake keys/clients, never a real call) --------


def test_gemini_rotates_to_next_key_when_first_fails(monkeypatch):
    calls = []

    class FailingModels:
        def generate_content(self, **kwargs):
            calls.append("key1")
            raise Exception("429 rate limited")  # noqa: TRY002 - simulating a provider error

    class SucceedingModels:
        def generate_content(self, **kwargs):
            calls.append("key2")

            class _Part:
                inline_data = type("_D", (), {"data": b"\x00\x01"})()

            class _Content:
                parts = [_Part()]

            class _Candidate:
                content = _Content()

            return type("_R", (), {"candidates": [_Candidate()]})()

    class FakeClient:
        def __init__(self, models):
            self.models = models

    monkeypatch.setattr(tts, "_gemini_clients", [FakeClient(FailingModels()), FakeClient(SucceedingModels())])

    audio, mime = tts._synthesize_gemini("Hello there.")

    assert calls == ["key1", "key2"]
    assert mime == "audio/wav"
    assert len(audio) > 0


def test_gemini_raises_when_no_keys_configured(monkeypatch):
    monkeypatch.setattr(tts, "_gemini_clients", [])
    with pytest.raises(ProviderError):
        tts._synthesize_gemini("Hello there.")


# --- live audio output (real network/local calls — NEVER Gemini, see module docstring) ---


def test_piper_produces_audio_for_english_live():
    audio, mime = tts._synthesize_piper("This is a test of the voice output.")
    assert len(audio) > 0
    assert mime == "audio/wav"


def test_piper_produces_audio_for_arabic_live():
    audio, mime = tts._synthesize_piper("هذا اختبار للصوت.")
    assert len(audio) > 0
    assert mime == "audio/wav"


def test_edge_tts_picks_voice_by_detected_language_live():
    """edge_tts has no single multilingual voice — confirms both language paths produce real audio."""
    en_audio, en_mime = tts._synthesize_edge_tts("This is a test.")
    assert len(en_audio) > 0
    assert en_mime == "audio/mpeg"

    ar_audio, ar_mime = tts._synthesize_edge_tts("هذا اختبار.")
    assert len(ar_audio) > 0
    assert ar_mime == "audio/mpeg"


def test_synthesize_speech_default_chain_produces_audio_without_gemini(monkeypatch):
    """
    Confirms the full fallback chain still works end-to-end when Gemini is
    unavailable — using a fake gemini failure (never a real call) so Piper
    actually runs and produces real local audio.
    """
    def fail_gemini(text):
        raise ProviderError("simulated: gemini not available in this test")

    monkeypatch.setitem(tts._PROVIDERS, "gemini", fail_gemini)

    audio, mime = tts.synthesize_speech("This confirms the fallback chain works.")

    assert len(audio) > 0
    assert mime == "audio/wav"  # piper


# --- TTS failure never affects /chat/message's text response ---------------


@pytest.fixture()
def authed_headers(db, unique_suffix):
    from app.auth.security import create_token
    from app.database.models import User

    username = f"ttstest_{unique_suffix}"
    response = client.post(
        "/auth/signup",
        json={
            "full_name": "TTS Test",
            "username": username,
            "email": f"{username}@example.com",
            "password": "testpass123",
            "confirm_password": "testpass123",
        },
    )
    user_id = response.json()["user"]["id"]
    token = create_token(user_id, "authenticated", 60)

    yield {"Authorization": f"Bearer {token}"}

    db.query(User).filter_by(username=username).delete()
    db.commit()


def test_tts_failure_does_not_affect_chat_message_text_response(authed_headers, monkeypatch):
    reply1 = client.post("/chat/message", headers=authed_headers, json={"message": "Hi"})
    assert reply1.status_code == 200
    assert reply1.json()["reply"]

    def fail(text):
        raise ProviderError("boom")

    monkeypatch.setattr(tts, "TTS_PROVIDER_ORDER", ["gemini", "piper", "edge_tts", "elevenlabs"])
    monkeypatch.setitem(tts._PROVIDERS, "gemini", fail)
    monkeypatch.setitem(tts._PROVIDERS, "piper", fail)
    monkeypatch.setitem(tts._PROVIDERS, "edge_tts", fail)
    monkeypatch.setitem(tts._PROVIDERS, "elevenlabs", fail)

    speak_resp = client.post("/chat/speak", headers=authed_headers, json={"text": "hello"})
    assert speak_resp.status_code == 503

    reply2 = client.post("/chat/message", headers=authed_headers, json={"message": "Hi"})
    assert reply2.status_code == 200
    assert reply2.json()["reply"]
