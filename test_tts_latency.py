import asyncio
import time
from pathlib import Path

from app.providers.tts.gemini_tts_provider import (
    gemini_tts_provider
)

from app.providers.tts.elevenlabs.elevenlabs_tts_provider import (
    elevenlabs_tts_provider
)


TEST_TEXT = """
مساء الخير! أنا مساعد الذكاء الاصطناعي الخاص بالشركة.
ممكن أساعدك في الاستعلام عن حسابك، وأشرح لك أي معلومات
محتاجها بطريقة بسيطة وواضحة.
"""


async def test_provider(
    name: str,
    provider,
):

    print("\n" + "=" * 70)
    print(f"TESTING {name}")
    print("=" * 70)

    print("\nGenerating audio...")

    start = time.perf_counter()

    try:

        audio_path = await provider.synthesize(
            TEST_TEXT
        )

        elapsed = (
            time.perf_counter()
            - start
        )

        print("\nSUCCESS")

        print(
            f"Total latency: {elapsed:.3f}s"
        )

        print(
            f"Audio path: {audio_path}"
        )

        path = Path(audio_path)

        if path.exists():

            size_kb = (
                path.stat().st_size
                / 1024
            )

            print(
                f"Audio size: {size_kb:.2f} KB"
            )

        else:

            print(
                "WARNING: Audio file does not exist."
            )

        return {
            "provider": name,
            "success": True,
            "latency": elapsed,
            "audio_path": str(audio_path),
        }

    except Exception as error:

        elapsed = (
            time.perf_counter()
            - start
        )

        print("\nFAILED")

        print(
            f"Latency before failure: "
            f"{elapsed:.3f}s"
        )

        print(
            f"Error: {error}"
        )

        return {
            "provider": name,
            "success": False,
            "latency": elapsed,
            "error": str(error),
        }


async def main():

    print("=" * 70)
    print("TTS LATENCY COMPARISON")
    print("=" * 70)

    print("\nTest text:")
    print(TEST_TEXT)

    # =====================================================
    # GEMINI
    # =====================================================

    gemini_result = await test_provider(
        "GEMINI",
        gemini_tts_provider,
    )

    # =====================================================
    # ELEVENLABS
    # =====================================================

    elevenlabs_result = await test_provider(
        "ELEVENLABS",
        elevenlabs_tts_provider,
    )

    # =====================================================
    # FINAL COMPARISON
    # =====================================================

    print("\n\n")

    print("=" * 70)
    print("FINAL COMPARISON")
    print("=" * 70)

    print(
        f"{'Provider':<15}"
        f"{'Success':<12}"
        f"{'Latency':<15}"
    )

    print("-" * 70)

    results = [
        gemini_result,
        elevenlabs_result,
    ]

    for result in results:

        print(
            f"{result['provider']:<15}"
            f"{str(result['success']):<12}"
            f"{result['latency']:.3f}s"
        )

    # =====================================================
    # FASTEST
    # =====================================================

    successful_results = [
        result
        for result in results
        if result["success"]
    ]

    if successful_results:

        fastest = min(
            successful_results,
            key=lambda result: result["latency"]
        )

        print("\n" + "=" * 70)

        print(
            f"FASTEST TTS: "
            f"{fastest['provider']}"
        )

        print(
            f"Latency: "
            f"{fastest['latency']:.3f}s"
        )

        print("=" * 70)


if __name__ == "__main__":

    asyncio.run(main())