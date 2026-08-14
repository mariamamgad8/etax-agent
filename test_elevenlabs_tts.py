import asyncio
import time

from app.providers.tts.elevenlabs_tts_provider import (
    elevenlabs_tts_provider
)


async def main():

    text = (
        "أهلاً بيك! أنا الـ AI assistant بتاع الشركة. "
        "ممكن أساعدك في checking your account، "
        "وأقدر كمان أشرحلك أي information محتاجها "
        "بطريقة بسيطة وواضحة. "
        "لو عندك أي مشكلة، ابعتلي التفاصيل "
        "وأنا هحاول أساعدك خطوة بخطوة."
    )

    print("=" * 60)
    print("ELEVENLABS TTS TEST")
    print("=" * 60)

    print("\nText:")
    print(text)

    print("\nGenerating audio...")

    start = time.perf_counter()

    try:

        audio_path = await elevenlabs_tts_provider.synthesize(
            text
        )

        elapsed = time.perf_counter() - start

        print("\n" + "=" * 60)
        print("SUCCESS")
        print("=" * 60)

        print("Audio saved to:")
        print(audio_path)

        print(f"\nLatency: {elapsed:.2f} seconds")

    except Exception as e:

        elapsed = time.perf_counter() - start

        print("\n" + "=" * 60)
        print("ERROR")
        print("=" * 60)

        print(f"Error: {e}")
        print(f"Latency before failure: {elapsed:.2f} seconds")


if __name__ == "__main__":
    asyncio.run(main())