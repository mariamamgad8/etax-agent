import asyncio
import requests

from app.core.config import config
from app.providers.base_provider import BaseSpeechProvider
from app.exceptions.speech_exception import TranscriptionFailedException


class CohereProvider(BaseSpeechProvider):

    API_URL = "https://api.cohere.com/v2/audio/transcriptions"

    def __init__(self):

        self.headers = {
            "Authorization": f"Bearer {config.COHERE_API_KEY}",
            "Accept": "application/json",
            "User-Agent": "speech-api/1.0",
        }

        self.model = config.COHERE_MODEL

    async def transcribe(
        self,
        audio_path: str,
    ) -> str:

        def request():

            with open(audio_path, "rb") as audio_file:

                files = {
                    "file": (
                        "audio.wav",
                        audio_file,
                        "audio/wav",
                    )
                }

                data = {
                    "model": self.model,
                    "language": "ar",
                }

                response = requests.post(
                    self.API_URL,
                    headers=self.headers,
                    files=files,
                    data=data,
                    timeout=(20, 120),
                )

            return response

        try:

            response = await asyncio.to_thread(
                request
            )

            if not response.ok:

                raise TranscriptionFailedException(
                    f"Cohere API error "
                    f"{response.status_code}: "
                    f"{response.text}"
                )

            result = response.json()

            if "text" not in result:

                raise TranscriptionFailedException(
                    f"Unexpected Cohere response: {result}"
                )

            return result["text"]

        except TranscriptionFailedException:
            raise

        except Exception as error:

            raise TranscriptionFailedException(
                f"Cohere transcription failed: {error}"
            ) from error


cohere_provider = CohereProvider()