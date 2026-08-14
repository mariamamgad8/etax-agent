import asyncio

from app.providers.tts.fish_tts_provider import (
    fish_tts_provider
)


async def main():

    audio_path = await fish_tts_provider.synthesize(
        "إزيك يا خالد؟ عامل إيه النهاردة؟ "
        "أهلاً بيك في المساعد الصوتي بتاع e-Tax. "
        "إزاي أقدر أساعدك؟"
    )

    print("Fish Audio generated:")
    print(audio_path)


if __name__ == "__main__":
    asyncio.run(main())