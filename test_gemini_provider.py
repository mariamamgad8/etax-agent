import asyncio

from app.providers.tts.gemini_tts_provider import (
    gemini_tts_provider
)


async def main():

    audio_path = await gemini_tts_provider.synthesize(
        "إزيك يا خالد؟ عامل إيه النهاردة؟ إحنا بنجرب دلوقتي المساعد الصوتي المصري بتاعنا."
    )

    print("Audio generated:")
    print(audio_path)


if __name__ == "__main__":
    asyncio.run(main())