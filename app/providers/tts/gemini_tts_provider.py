import asyncio
import wave
from pathlib import Path
import uuid

from google import genai

from app.core.config import config


class GeminiTTSProvider:

    def __init__(self):
        self.client = genai.Client(
            api_key=config.GEMINI_API_KEY
        )

        self.model = config.GEMINI_TTS_MODEL
        self.voice = config.GEMINI_TTS_VOICE

        self.output_dir = Path("temp/audio")
        self.output_dir.mkdir(
            parents=True,
            exist_ok=True
        )

    def _save_wav(
        self,
        file_path: Path,
        audio_data: bytes
    ):
        with wave.open(str(file_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(24000)
            wf.writeframes(audio_data)

    async def synthesize(
        self,
        text: str
    ) -> str:

        response = await asyncio.to_thread(
            self.client.models.generate_content,
            model=self.model,
            contents=(
                "Speak naturally in Egyptian Arabic. "
                "Use a friendly conversational tone.\n\n"
                f"{text}"
            ),
            config={
                "response_modalities": ["AUDIO"],
                "speech_config": {
                    "voice_config": {
                        "prebuilt_voice_config": {
                            "voice_name": self.voice
                        }
                    }
                }
            }
        )

        audio_data = (
            response
            .candidates[0]
            .content
            .parts[0]
            .inline_data
            .data
        )

        file_path = (
            self.output_dir
            / f"{uuid.uuid4()}.wav"
        )

        self._save_wav(
            file_path,
            audio_data
        )

        return str(file_path)


gemini_tts_provider = GeminiTTSProvider()