import logging
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.auth.dependencies import require_authenticated
from app.chat.fraud.extraction import extract_fraud_features
from app.chat.fraud.validation import validate_fraud_features
from app.chat.graph import resume_chat, run_chat
from app.chat.providers.base import AllProvidersExhausted
from app.chat.providers.stt import transcribe_audio
from app.chat.providers.tts import synthesize_speech
from app.chat.responses import detect_response_language
from app.database.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatMessageRequest(BaseModel):
    # A plain message starts a fresh graph run. A resume submits the
    # confirmed fraud-form fields to a paused run identified by thread_id —
    # exactly one of the two must be set.
    message: str | None = Field(default=None, min_length=1, max_length=4000)
    thread_id: str | None = None
    form_response: dict | None = None


class AwaitingInput(BaseModel):
    type: str
    fields: dict
    errors: list[str]
    schema_: dict = Field(alias="schema")

    model_config = {"populate_by_name": True}


class TablePayload(BaseModel):
    columns: list[str]
    rows: list[list]


class ChatMessageResponse(BaseModel):
    thread_id: str
    reply: str | None = None
    intent: str | None = None
    awaiting: AwaitingInput | None = None
    table: TablePayload | None = None


class TranscribeResponse(BaseModel):
    text: str


class SpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class FraudExtractRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    current_fields: dict = Field(default_factory=dict)


class FraudExtractResponse(BaseModel):
    fields: dict
    errors: list[str]


def _own_thread_id(user: User) -> str:
    return f"{user.id}:{uuid.uuid4().hex}"


def _check_thread_ownership(user: User, thread_id: str) -> None:
    if not thread_id.startswith(f"{user.id}:"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "That conversation does not belong to you.")


@router.post("/message", response_model=ChatMessageResponse)
async def send_message(
    payload: ChatMessageRequest,
    user: User = Depends(require_authenticated),
):
    is_resume = payload.form_response is not None
    if is_resume:
        if not payload.thread_id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "thread_id is required to resume.")
        _check_thread_ownership(user, payload.thread_id)
        thread_id = payload.thread_id
        state, interrupt_payload = await run_in_threadpool(resume_chat, payload.form_response, thread_id)
    else:
        if not payload.message:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "message is required to start a conversation.")
        thread_id = payload.thread_id or _own_thread_id(user)
        _check_thread_ownership(user, thread_id)
        state, interrupt_payload = await run_in_threadpool(run_chat, payload.message, thread_id, str(user.id))

    if interrupt_payload is not None:
        return ChatMessageResponse(
            thread_id=thread_id,
            intent=state.get("intent"),
            awaiting=AwaitingInput(
                type=interrupt_payload["type"],
                fields=interrupt_payload["fields"],
                errors=interrupt_payload["errors"],
                schema_=interrupt_payload["schema"],
            ),
        )

    table_payload = (state.get("response_payload") or {}).get("table")
    return ChatMessageResponse(
        thread_id=thread_id,
        reply=state.get("final_response", ""),
        intent=state.get("intent"),
        table=TablePayload(**table_payload) if table_payload else None,
    )


@router.post("/fraud/extract", response_model=FraudExtractResponse)
async def fraud_extract(
    payload: FraudExtractRequest,
    user: User = Depends(require_authenticated),
):
    """
    Lets the user type/paste more feature text into the chat while the fraud
    form is showing, without submitting it yet — extracts values from the
    text and merges them into the form's current values (a field the new
    text doesn't mention keeps whatever value it already had; never
    overwritten with null), so it "reflects in the menu" immediately. This
    is intentionally stateless (no thread_id, doesn't touch the graph's
    interrupt/resume checkpoint) — the actual submission still goes through
    POST /chat/message's form_response path unchanged.
    """
    logger.info("[FRAUD] /chat/fraud/extract request from user_id=%s", user.id)
    # This endpoint is stateless (no thread_id/graph state — see the docstring
    # above), so unlike the graph's nodes it has no state["response_language"]
    # to read; it detects directly from the text just submitted instead,
    # using the same deterministic per-message logic route_intent uses.
    language = detect_response_language(payload.text)
    extracted = await run_in_threadpool(extract_fraud_features, payload.text)
    new_values = extracted.model_dump(exclude_none=True)
    merged = {**payload.current_fields, **new_values}
    errors = validate_fraud_features(merged, language)
    return FraudExtractResponse(fields=merged, errors=errors)


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe(
    audio: UploadFile = File(...),
    user: User = Depends(require_authenticated),
):
    """Speech-to-text for the composer's mic button — Groq detects the language, Cohere transcribes with it (see app.chat.providers.stt)."""
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "No audio data received.")

    logger.info("[STT] /chat/transcribe request from user_id=%s, %d bytes", user.id, len(audio_bytes))
    try:
        text = await run_in_threadpool(transcribe_audio, audio_bytes, audio.filename or "recording.webm")
    except AllProvidersExhausted as exc:
        logger.warning("[STT] all providers exhausted for user_id=%s: %s", user.id, exc)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Speech-to-text is temporarily unavailable. Try typing your message instead.",
        ) from exc

    return TranscribeResponse(text=text)


@router.post("/speak")
async def speak(
    payload: SpeakRequest,
    user: User = Depends(require_authenticated),
):
    """
    Text-to-speech for the composer's voice-reply toggle — ElevenLabs first,
    Gemini as fallback (see app.chat.providers.tts). The agent's text reply
    from /chat/message always stands on its own; this is a separate,
    on-demand call the frontend only makes when the user has voice replies
    enabled, so a TTS failure never blocks or alters the text response.
    """
    logger.info("[TTS] /chat/speak request from user_id=%s, %d chars", user.id, len(payload.text))
    try:
        audio_bytes, mime_type = await run_in_threadpool(synthesize_speech, payload.text)
    except AllProvidersExhausted as exc:
        logger.warning("[TTS] all providers exhausted for user_id=%s: %s", user.id, exc)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Voice output is temporarily unavailable. The text reply is still shown above.",
        ) from exc

    return Response(content=audio_bytes, media_type=mime_type)
