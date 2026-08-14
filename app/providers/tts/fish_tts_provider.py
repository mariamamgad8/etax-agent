import asyncio
from pathlib import Path
import uuid

import requests

from app.core.config import config


class FishTTSProvider:

    def __init__(self):
        self.api_key = config.FISH_API_KEY
        self.model = config.FISH_TTS_MODEL
        self.voice_id = config.FISH_TTS_VOICE_ID

        self.url = "https://api.fish.audio/v1/tts"

        self.output_dir = Path("temp/audio")
        self.output_dir.mkdir(
            parents=True,
            exist_ok=True
        )

    async def synthesize(self, text: str) -> str:

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "model": self.model,
        }

        payload = {
            "text": text,
            "reference_id": self.voice_id,
            "format": "mp3",
        }

        def request():

            response = requests.post(
                self.url,
                headers=headers,
                json=payload,
                timeout=60,
                verify=False,
            )

            if not response.ok:
                raise RuntimeError(
                    f"Fish Audio API error "
                    f"{response.status_code}: "
                    f"{response.text}"
                )

            return response.content

        audio_data = await asyncio.to_thread(request)

        file_path = (
            self.output_dir
            / f"{uuid.uuid4()}.mp3"
        )

        file_path.write_bytes(audio_data)

        return str(file_path)


fish_tts_provider = FishTTSProvider()