import asyncio
import base64
import requests

from app.core.config import config
from app.providers.base_provider import BaseSpeechProvider
from app.exceptions.speech_exception import (
    TranscriptionFailedException
)


class CloudflareProvider(BaseSpeechProvider):

    def __init__(self):

        self.account_id = config.CLOUDFLARE_ACCOUNT_ID
        self.api_token = config.CLOUDFLARE_API_TOKEN
        self.model = config.CLOUDFLARE_STT_MODEL

        self.api_url = (
            "https://api.cloudflare.com/client/v4/"
            f"accounts/{self.account_id}/ai/run/"
            f"{self.model}"
        )

        self.headers = {
            "Authorization": (
                f"Bearer {self.api_token}"
            ),
            "Content-Type": "application/json",
        }

    async def transcribe(
        self,
        audio_path: str,
    ) -> str:

        def request():

            # =========================
            # Read audio
            # =========================

            with open(audio_path, "rb") as audio_file:
                audio_data = audio_file.read()

            # =========================
            # Convert audio to Base64
            # =========================

            audio_base64 = base64.b64encode(
                audio_data
            ).decode("utf-8")

            # =========================
            # Cloudflare request
            # =========================

            payload = {
                "audio": audio_base64,
                "task": "transcribe",
                "language": "ar",
            }

            response = requests.post(
                self.api_url,
                headers=self.headers,
                json=payload,
                timeout=(20, 120),
            )

            return response

        try:

            response = await asyncio.to_thread(
                request
            )

            if not response.ok:

                raise TranscriptionFailedException(
                    f"Cloudflare API error "
                    f"{response.status_code}: "
                    f"{response.text}"
                )

            result = response.json()

            if not result.get("success"):

                raise TranscriptionFailedException(
                    f"Cloudflare request failed: "
                    f"{result}"
                )

            output = result.get(
                "result",
                {}
            )

            text = output.get("text")

            if not text:

                raise TranscriptionFailedException(
                    f"Unexpected Cloudflare response: "
                    f"{result}"
                )

            return text

        except TranscriptionFailedException:
            raise

        except Exception as error:

            raise TranscriptionFailedException(
                f"Cloudflare transcription failed: "
                f"{error}"
            ) from error


cloudflare_provider = CloudflareProvider()