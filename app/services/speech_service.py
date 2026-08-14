from app.core.enums import Provider
from app.providers.provider_factory import provider_factory


class SpeechService:

    async def transcribe(
        self,
        audio_path: str,
        provider: Provider,
    ) -> str:

        speech_provider = provider_factory.get_provider(
            provider
        )

        return await speech_provider.transcribe(
            audio_path
        )


speech_service = SpeechService()