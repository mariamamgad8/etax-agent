import asyncio

from app.core.enums import Provider
from app.exceptions.speech_exception import SpeechException
from app.services.fallback_service import fallback_service


class FailingProvider:

    async def transcribe(self, audio_path: str) -> str:
        raise SpeechException("Simulated Groq failure")


async def main():

    original_provider = fallback_service

    class TestFallbackService:

        async def transcribe(
            self,
            audio_path: str,
            primary_provider: Provider,
            fallback_provider: Provider,
        ) -> str:

            try:
                failing_provider = FailingProvider()

                return await failing_provider.transcribe(
                    audio_path
                )

            except SpeechException:

                provider = (
                    __import__(
                        "app.providers.provider_factory",
                        fromlist=["provider_factory"]
                    ).provider_factory
                    .get_provider(fallback_provider)
                )

                return await provider.transcribe(
                    audio_path
                )

    test_service = TestFallbackService()

    transcript = await test_service.transcribe(
        audio_path="tests/audio/record.wav",
        primary_provider=Provider.GROQ,
        fallback_provider=Provider.COHERE,
    )

    print("Fallback Transcript:")
    print(transcript)


if __name__ == "__main__":
    asyncio.run(main())