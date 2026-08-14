import asyncio
import wave
from pathlib import Path

from google import genai

from app.core.config import config


OUTPUT_PATH = Path("playground/gemini_egyptian_test.wav")


def save_wav(filename, pcm_data):
    with wave.open(str(filename), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(pcm_data)


async def main():

    client = genai.Client(
        api_key=config.GEMINI_API_KEY
    )

    text = """
    اتكلم باللهجة المصرية الطبيعية وبصوت ودود.
    إزيك يا خالد؟ عامل إيه النهاردة؟
    إحنا بنجرب دلوقتي المساعد الصوتي المصري بتاعنا،
    والمفروض إنك تقدر تتكلم معاه بشكل طبيعي.
    """

    response = await asyncio.to_thread(
        client.models.generate_content,
        model=config.GEMINI_TTS_MODEL,
        contents=text,
        config={
            "response_modalities": ["AUDIO"],
            "speech_config": {
                "voice_config": {
                    "prebuilt_voice_config": {
                        "voice_name": config.GEMINI_TTS_VOICE
                    }
                }
            }
        },
    )

    audio_data = response.candidates[0].content.parts[0].inline_data.data

    save_wav(
        OUTPUT_PATH,
        audio_data
    )

    print(f"Audio saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())