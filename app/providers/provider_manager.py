from app.providers.groq_provider import groq_provider
from app.providers.cohere_provider import cohere_provider


class ProviderManager:

    async def transcribe(
        self,
        audio_bytes: bytes,
        filename: str,
    ) -> str:

        try:
            return await groq_provider.transcribe(
                audio_bytes,
                filename,
            )

        except Exception as e:

            print(f"Groq failed: {e}")

            return await cohere_provider.transcribe(
                audio_bytes,
                filename,
            )


provider_manager = ProviderManager()