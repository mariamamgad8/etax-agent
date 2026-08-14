import asyncio
from pathlib import Path
import uuid

from elevenlabs.client import ElevenLabs

from app.core.config import config


class ElevenLabsTTSProvider:

    def __init__(self):
        self.client = ElevenLabs(
            api_key=config.ELEVENLABS_API_KEY
        )

        self.model = config.ELEVENLABS_MODEL
        self.voice_id = config.ELEVENLABS_VOICE_ID

        self.output_dir = Path("temp/audio")
        self.output_dir.mkdir(
            parents=True,
            exist_ok=True
        )

    async def synthesize(
        self,
        text: str
    ) -> str:

        audio = await asyncio.to_thread(
            self.client.text_to_speech.convert,
            voice_id=self.voice_id,
            model_id=self.model,
            text=text,
            output_format="mp3_44100_128",
        )

        file_path = (
            self.output_dir
            / f"{uuid.uuid4()}.mp3"
        )

        with open(file_path, "wb") as f:
            for chunk in audio:
                f.write(chunk)

        return str(file_path)


elevenlabs_tts_provider = ElevenLabsTTSProvider()