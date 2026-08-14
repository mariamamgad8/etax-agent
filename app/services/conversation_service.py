import time
from pathlib import Path

from app.core.enums import Provider
from app.services.fallback_service import fallback_service
from app.providers.tts.tts_router import fallback_tts_provider
from app.taya.taya_service import taya_service


class ConversationService:

    def __init__(self):
        # Taya owns the conversation state.
        # We keep this service stateless apart from timing.
        pass

    async def process_audio(
        self,
        session_id: str,
        audio_path: str,
    ):

        total_start = time.perf_counter()

        # =========================================================
        # 1. STT
        #
        # Accuracy ranking from the user's benchmark:
        #   Cohere -> Cloudflare -> Groq
        # =========================================================

        stt_start = time.perf_counter()

        transcript = await fallback_service.transcribe(
            audio_path=audio_path,
            providers=[
                Provider.COHERE,
                Provider.CLOUDFLARE,
                Provider.GROQ,
            ],
        )

        stt_time = (
            time.perf_counter() - stt_start
        )

        # =========================================================
        # 2. TAYA
        #
        # Taya receives ONLY the current transcript.
        # It owns language selection, extraction, state, questions,
        # and feature completion.
        # =========================================================

        taya_start = time.perf_counter()

        taya_result = (
            await taya_service.process_message(
                session_id=session_id,
                user_message=transcript,
            )
        )

        taya_time = (
            time.perf_counter() - taya_start
        )

        response_text = taya_result.get(
            "response",
            "",
        )

        # =========================================================
        # 3. TTS
        #
        # Keep the existing TTS router/fallback architecture.
        # =========================================================

        tts_start = time.perf_counter()

        response_audio = (
            await fallback_tts_provider.synthesize(
                response_text
            )
        )

        tts_time = (
            time.perf_counter() - tts_start
        )

        # =========================================================
        # 4. TOTAL
        # =========================================================

        total_time = (
            time.perf_counter() - total_start
        )

        audio_path_obj = Path(
            response_audio
        )

        audio_filename = (
            audio_path_obj.name
        )

        # =========================================================
        # 5. TIMING LOG
        # =========================================================

        print(
            "\n"
            "==================================================\n"
            "TAYA VOICE PIPELINE\n"
            "==================================================\n"
            f"STT:       {stt_time:.3f}s\n"
            f"TAYA:      {taya_time:.3f}s\n"
            f"TTS:       {tts_time:.3f}s\n"
            f"TOTAL:     {total_time:.3f}s\n"
            "--------------------------------------------------\n"
            f"Transcript: {transcript}\n"
            f"Response:   {response_text}\n"
            f"Audio:      {audio_filename}\n"
            "==================================================\n"
        )

        # =========================================================
        # 6. RETURN FRONTEND-FRIENDLY RESULT
        # =========================================================

        return {
            "success": True,

            "session_id": session_id,

            "transcript": transcript,

            "response": response_text,

            "audio_url": (
                f"/audio/{audio_filename}"
            ),

            "audio_path": str(
                response_audio
            ),

            "extracted": taya_result.get(
                "extracted",
                {},
            ),

            "missing_fields": taya_result.get(
                "missing_fields",
                [],
            ),

            "complete": taya_result.get(
                "complete",
                False,
            ),

            "timings": {
                "stt_seconds": round(
                    stt_time,
                    3,
                ),
                "taya_seconds": round(
                    taya_time,
                    3,
                ),
                "tts_seconds": round(
                    tts_time,
                    3,
                ),
                "total_backend_seconds": round(
                    total_time,
                    3,
                ),
            },
        }


conversation_service = ConversationService()