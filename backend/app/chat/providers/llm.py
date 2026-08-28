"""
Central LLM access point. Nodes never talk to Groq/Gemini directly — they
call call_llm_text(...) or call_llm_structured(..., response_model=...) and
this module handles provider/model priority, fallback and cooldown behind
that interface. See LLM_PROVIDER_ORDER / GROQ_LLM_MODELS / GEMINI_LLM_MODELS
in app.chat.config for the priority configuration.
"""

import json
import logging
from typing import TypeVar

from google import genai
from google.genai import types as genai_types
from groq import Groq
from pydantic import BaseModel, ValidationError

from app.chat.config import (
    GEMINI_LLM_API_KEYS,
    GEMINI_LLM_MODELS,
    GROQ_API_KEY,
    GROQ_LLM_MODELS,
    LLM_PROVIDER_ORDER,
    MODEL_COOLDOWN_SECONDS,
    gemini_key_label,
)
from app.chat.providers.base import AllProvidersExhausted, CooldownTracker, ProviderError, RotatingStart
from app.chat.providers.gemini_quota import gemini_block_seconds

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_cooldown = CooldownTracker(MODEL_COOLDOWN_SECONDS)

# No SDK-level retries and a tight timeout — same fast-fail rationale as
# providers/tts.py's _GEMINI_HTTP_OPTIONS: without this, a rate-limited key
# eats the SDK's default ~5 retries with exponential backoff (1s,2s,4s,8s,
# 16s ≈ 31s) INSIDE a single key attempt, before this module's own key/model
# fallback ever gets a chance to move on. This module previously had no
# http_options at all (unlike TTS), which was the larger of the two sources
# of multi-second stalls when a key/model was exhausted.
_GEMINI_HTTP_OPTIONS = genai_types.HttpOptions(
    timeout=10_000,  # milliseconds
    retry_options=genai_types.HttpRetryOptions(attempts=1),
)

_groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
# One client per configured Gemini key (GEMINI_LLM_API_KEYS) — previously a
# single hardcoded key with no fallback at all, unlike TTS's own key
# rotation. Each (key, client) pair is tried in order on every Gemini call;
# see _call_gemini_text/_call_gemini_structured.
_gemini_clients = [(key, genai.Client(api_key=key, http_options=_GEMINI_HTTP_OPTIONS)) for key in GEMINI_LLM_API_KEYS]

# Per-(key, model) quota state — shared between _call_gemini_text and
# _call_gemini_structured since both hit the same underlying generateContent
# quota for a given key/model. A key/model blocked here is skipped with NO
# network call at all on the next attempt, instead of re-eating a timeout
# every single request until it happens to succeed again. Block duration is
# set per-failure from the real 429 response (see gemini_quota.py) — a
# per-day quota is skipped until Google's own reset, a per-minute quota for a
# short window, anything else for the same short generic cooldown as before.
_gemini_key_quota = CooldownTracker(MODEL_COOLDOWN_SECONDS)
# Spreads which key gets tried first across calls instead of always starting
# at GEMINI_API_KEY — see RotatingStart's docstring.
_gemini_rotation = RotatingStart()

# Groq models known to support strict response_format={"type": "json_schema"}.
# Others still get asked for JSON (json_object mode + an inline schema
# description), since strict mode 400s on models that don't support it.
_GROQ_JSON_SCHEMA_MODELS = {"openai/gpt-oss-20b", "openai/gpt-oss-120b"}


def _candidates():
    """Yields (provider, model) pairs in configured fallback order."""
    for provider in LLM_PROVIDER_ORDER:
        if provider == "groq":
            for model in GROQ_LLM_MODELS:
                yield "groq", model
        elif provider == "gemini":
            for model in GEMINI_LLM_MODELS:
                yield "gemini", model
        else:
            logger.warning("Unknown LLM provider in LLM_PROVIDER_ORDER: %s", provider)


def _call_groq_text(model: str, system: str, user: str) -> str:
    if _groq_client is None:
        raise ProviderError("GROQ_API_KEY is not configured.")
    completion = _groq_client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.2,
    )
    return completion.choices[0].message.content or ""


def _call_gemini_text(model: str, system: str, user: str) -> str:
    if not _gemini_clients:
        raise ProviderError("No Gemini API key is configured (GEMINI_LLM_API_KEYS/GEMINI_API_KEY).")
    last_exc: Exception | None = None
    attempted = False
    for key, client in _gemini_rotation.rotate(_gemini_clients):
        quota_key = f"{key}:{model}"
        if _gemini_key_quota.is_cooling_down(quota_key):
            continue
        attempted = True
        try:
            response = client.models.generate_content(
                model=model,
                contents=user,
                config=genai_types.GenerateContentConfig(system_instruction=system, temperature=0.2),
            )
            return response.text or ""
        except Exception as exc:  # noqa: BLE001 - try the next key before giving up on this model
            reason, block_seconds = gemini_block_seconds(exc, MODEL_COOLDOWN_SECONDS)
            _gemini_key_quota.mark(quota_key, seconds=block_seconds)
            logger.warning(
                "[LLM] gemini:%s failed on %s — %s: %s (%s, skipping this key for %.0fs)",
                model, gemini_key_label(key), type(exc).__name__, exc, reason, block_seconds,
            )
            last_exc = exc
    if not attempted:
        raise ProviderError(
            f"All {len(_gemini_clients)} configured Gemini key(s) are currently quota-blocked for model {model}."
        )
    raise ProviderError(f"All attempted Gemini key(s) failed for model {model}. Last error: {last_exc}")


def call_llm_text(system: str, user: str) -> str:
    """Plain text completion with provider/model fallback and cooldown."""
    last_error: Exception | None = None
    for provider, model in _candidates():
        key = f"{provider}:{model}"
        if _cooldown.is_cooling_down(key):
            logger.info("[LLM] skipping %s (cooling down after a recent failure)", key)
            continue
        try:
            text = _call_groq_text(model, system, user) if provider == "groq" else _call_gemini_text(model, system, user)
            logger.info("[LLM] text call answered by %s", key)
            return text
        except Exception as exc:  # noqa: BLE001 - any provider failure just moves to the next candidate
            logger.warning("[LLM] text call failed on %s — %s: %s", key, type(exc).__name__, exc)
            _cooldown.mark(key)
            last_error = exc
    raise AllProvidersExhausted(f"Every configured LLM model failed. Last error: {last_error}")


def _call_groq_structured(model: str, system: str, user: str, response_model: type[T]) -> T:
    if _groq_client is None:
        raise ProviderError("GROQ_API_KEY is not configured.")
    schema = response_model.model_json_schema()
    if model in _GROQ_JSON_SCHEMA_MODELS:
        # Strict mode requires every property to be listed in "required",
        # including ones whose type already permits null (e.g. Optional
        # fields with no value stated) — omitting them from "required" is
        # how Pydantic marks "has a default", not what this dialect expects.
        strict_schema = {**schema, "required": list(schema.get("properties", {}))}
        completion = _groq_client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0,
            response_format={
                "type": "json_schema",
                "json_schema": {"name": response_model.__name__, "schema": strict_schema, "strict": True},
            },
        )
    else:
        schema_note = (
            "\n\nRespond with ONLY a single JSON object matching this JSON schema, "
            f"no other text before or after it:\n{json.dumps(schema)}"
        )
        completion = _groq_client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system + schema_note},
                {"role": "user", "content": user},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
    raw = completion.choices[0].message.content or ""
    try:
        return response_model.model_validate_json(raw)
    except ValidationError as exc:
        raise ProviderError(
            f"Groq model {model} returned invalid JSON for {response_model.__name__}: {exc}"
        ) from exc


def _call_gemini_structured(model: str, system: str, user: str, response_model: type[T]) -> T:
    if not _gemini_clients:
        raise ProviderError("No Gemini API key is configured (GEMINI_LLM_API_KEYS/GEMINI_API_KEY).")
    # Passing response_schema=response_model directly lets the SDK derive a
    # schema from Pydantic, but Pydantic's "additionalProperties" keyword
    # (from extra="forbid") has no equivalent in Gemini's Schema proto and
    # the request 400s. JSON mode + the schema spelled out in the prompt
    # sidesteps that dialect mismatch and matches the loose-mode fallback
    # already used for Groq models that don't support strict json_schema.
    schema = response_model.model_json_schema()
    schema_note = (
        "\n\nRespond with ONLY a single JSON object matching this JSON schema, "
        f"no other text before or after it:\n{json.dumps(schema)}"
    )
    config = genai_types.GenerateContentConfig(
        system_instruction=system + schema_note,
        temperature=0,
        response_mime_type="application/json",
    )

    # Only an API-call failure (auth/rate-limit/network) rotates to the next
    # key — a malformed-JSON response is a model/prompt problem, not a key
    # problem, so it's raised immediately rather than retried against every
    # other key for no benefit (same prompt, same model, same bad output).
    last_exc: Exception | None = None
    attempted = False
    for key, client in _gemini_rotation.rotate(_gemini_clients):
        quota_key = f"{key}:{model}"
        if _gemini_key_quota.is_cooling_down(quota_key):
            continue
        attempted = True
        try:
            response = client.models.generate_content(model=model, contents=user, config=config)
        except Exception as exc:  # noqa: BLE001 - try the next key before giving up on this model
            reason, block_seconds = gemini_block_seconds(exc, MODEL_COOLDOWN_SECONDS)
            _gemini_key_quota.mark(quota_key, seconds=block_seconds)
            logger.warning(
                "[LLM] gemini:%s (structured) failed on %s — %s: %s (%s, skipping this key for %.0fs)",
                model, gemini_key_label(key), type(exc).__name__, exc, reason, block_seconds,
            )
            last_exc = exc
            continue
        try:
            return response_model.model_validate_json(response.text)
        except ValidationError as exc:
            raise ProviderError(
                f"Gemini model {model} returned invalid JSON for {response_model.__name__}: {exc}"
            ) from exc
    if not attempted:
        raise ProviderError(
            f"All {len(_gemini_clients)} configured Gemini key(s) are currently quota-blocked for model {model}."
        )
    raise ProviderError(f"All attempted Gemini key(s) failed for model {model}. Last error: {last_exc}")


def call_llm_structured(system: str, user: str, response_model: type[T]) -> T:
    """Structured JSON completion validated into `response_model`, with provider/model fallback."""
    last_error: Exception | None = None
    for provider, model in _candidates():
        key = f"{provider}:{model}"
        if _cooldown.is_cooling_down(key):
            logger.info("[LLM] skipping %s (cooling down after a recent failure)", key)
            continue
        try:
            result = (
                _call_groq_structured(model, system, user, response_model)
                if provider == "groq"
                else _call_gemini_structured(model, system, user, response_model)
            )
            logger.info("[LLM] structured call (%s) answered by %s", response_model.__name__, key)
            return result
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[LLM] structured call (%s) failed on %s — %s: %s",
                response_model.__name__, key, type(exc).__name__, exc,
            )
            _cooldown.mark(key)
            last_error = exc
    raise AllProvidersExhausted(f"Every configured LLM model failed. Last error: {last_error}")
