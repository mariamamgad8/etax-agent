import asyncio

from app.providers.tts.tts_router import (
    fallback_tts_provider
)


async def main():

    text = (
        "أهلاً بيك! أنا الـ AI assistant بتاع الشركة. "
        "ممكن أساعدك في checking your account، "
        "وأقدر كمان أشرحلك أي information محتاجها "
        "بطريقة بسيطة وواضحة."
    )

    print("=" * 60)
    print("TTS FALLBACK TEST")
    print("=" * 60)

    print("\nGenerating audio...\n")

    try:

        audio_path = await fallback_tts_provider.synthesize(
            text
        )

        print("=" * 60)
        print("SUCCESS")
        print("=" * 60)

        print("Audio saved to:")
        print(audio_path)

    except Exception as e:

        print("=" * 60)
        print("ERROR")
        print("=" * 60)

        print(e)


if __name__ == "__main__":
    asyncio.run(main())