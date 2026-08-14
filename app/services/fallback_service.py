import logging

from app.core.enums import Provider
from app.providers.provider_factory import provider_factory
from app.exceptions.speech_exception import SpeechException


logger = logging.getLogger(__name__)


class FallbackService:

    async def transcribe(
        self,
        audio_path: str,
        providers: list[Provider],
    ) -> str:

        errors = []

        # =========================================================
        # Try providers according to accuracy ranking
        #
        # Current ranking:
        #
        # 1. Cohere
        # 2. Cloudflare
        # 3. Groq
        #
        # Lower WER / CER = better accuracy
        # =========================================================

        for provider_type in providers:

            try:

                logger.info(
                    "STT: Trying provider: %s",
                    provider_type.value,
                )

                provider = (
                    provider_factory.get_provider(
                        provider_type
                    )
                )

                transcript = await provider.transcribe(
                    audio_path
                )

                logger.info(
                    "STT: Provider succeeded: %s",
                    provider_type.value,
                )

                return transcript

            except SpeechException as error:

                logger.warning(
                    "STT: Provider failed: %s | %s",
                    provider_type.value,
                    error,
                )

                errors.append(
                    f"{provider_type.value}: {error}"
                )

            except Exception as error:

                logger.warning(
                    "STT: Unexpected provider failure: "
                    "%s | %s",
                    provider_type.value,
                    error,
                )

                errors.append(
                    f"{provider_type.value}: {error}"
                )

        # =========================================================
        # All providers failed
        # =========================================================

        logger.error(
            "STT: All providers failed"
        )

        raise RuntimeError(
            "All STT providers failed. "
            + " | ".join(errors)
        )


fallback_service = FallbackService()