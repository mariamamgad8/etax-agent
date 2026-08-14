from groq import Groq

from app.core.config import config
from app.providers.base_provider import BaseSpeechProvider


class GroqProvider(BaseSpeechProvider):

    def __init__(self):
        self.client = Groq(
            api_key=config.GROQ_API_KEY
        )

        self.model = config.GROQ_MODEL

    async def transcribe(
        self,
        audio_path: str,
    ) -> str:

        with open(audio_path, "rb") as audio_file:

            result = self.client.audio.transcriptions.create(
                file=audio_file,
                model=self.model,
                language="ar",
                temperature=0,
                response_format="verbose_json",
            )

        return result.text


groq_provider = GroqProvider()