import logging


logger = logging.getLogger(__name__)


class FallbackTTSProvider:

    def __init__(
        self,
        primary,
        fallback,
    ):
        self.primary = primary
        self.fallback = fallback

    async def synthesize(
        self,
        text: str,
    ) -> str:

        # =========================
        # Try Primary: Gemini
        # =========================

        try:

            logger.info(
                "TTS: Trying primary provider: %s",
                self.primary.__class__.__name__,
            )

            audio_path = await self.primary.synthesize(
                text
            )

            logger.info(
                "TTS: Primary provider succeeded"
            )

            return audio_path

        except Exception as primary_error:

            logger.warning(
                "TTS: Primary provider failed: %s",
                primary_error,
            )

        # =========================
        # Try Fallback: ElevenLabs
        # =========================

        try:

            logger.info(
                "TTS: Switching to fallback provider: %s",
                self.fallback.__class__.__name__,
            )

            audio_path = await self.fallback.synthesize(
                text
            )

            logger.info(
                "TTS: Fallback provider succeeded"
            )

            return audio_path

        except Exception as fallback_error:

            logger.error(
                "TTS: Fallback provider also failed: %s",
                fallback_error,
            )

            raise RuntimeError(
                "Both TTS providers failed."
            ) from fallback_error