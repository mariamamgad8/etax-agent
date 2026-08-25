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
    GEMINI_API_KEY,
    GEMINI_LLM_MODELS,
    GROQ_API_KEY,
    GROQ_LLM_MODELS,
    LLM_PROVIDER_ORDER,
    MODEL_COOLDOWN_SECONDS,
)
from app.chat.providers.base import AllProvidersExhausted, CooldownTracker, ProviderError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_cooldown = CooldownTracker(MODEL_COOLDOWN_SECONDS)

_groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
_gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

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
    if _gemini_client is None:
        raise ProviderError("GEMINI_API_KEY is not configured.")
    response = _gemini_client.models.generate_content(
        model=model,
        contents=user,
        config=genai_types.GenerateContentConfig(system_instruction=system, temperature=0.2),
    )
    return response.text or ""


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
            logger.warning("[LLM] text call failed on %s: %s", key, exc)
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
    if _gemini_client is None:
        raise ProviderError("GEMINI_API_KEY is not configured.")
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
    response = _gemini_client.models.generate_content(
        model=model,
        contents=user,
        config=genai_types.GenerateContentConfig(
            system_instruction=system + schema_note,
            temperature=0,
            response_mime_type="application/json",
        ),
    )
    try:
        return response_model.model_validate_json(response.text)
    except ValidationError as exc:
        raise ProviderError(
            f"Gemini model {model} returned invalid JSON for {response_model.__name__}: {exc}"
        ) from exc


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
            logger.warning("[LLM] structured call (%s) failed on %s: %s", response_model.__name__, key, exc)
            _cooldown.mark(key)
            last_error = exc
    raise AllProvidersExhausted(f"Every configured LLM model failed. Last error: {last_error}")
