import asyncio
import time
from pathlib import Path

from app.providers.tts.gemini_tts_provider import (
    gemini_tts_provider
)

from app.providers.tts.elevenlabs.elevenlabs_tts_provider import (
    elevenlabs_tts_provider
)


# =========================================================
# USE A REALISTIC LONG RESPONSE
# =========================================================

TEST_TEXT = """
أهلاً بيك! أنا الـ AI assistant بتاع الشركة.
ممكن أساعدك في checking your account، وأقدر كمان
أشرحلك أي information محتاجها بطريقة بسيطة وواضحة.

لو عندك أي مشكلة، ابعتلي التفاصيل وأنا هحاول
أساعدك خطوة بخطوة.

ممكن كمان أساعدك في مراجعة بيانات الحساب،
والتحقق من الـ transactions، وأوضح لك لو فيه
أي مشكلة أو error حصلت أثناء العملية.

ولو محتاج تعرف حالة الـ account أو أي information
مرتبطة بالـ customer، ابعتلي التفاصيل وأنا هراجعها
وأقولك النتيجة.
"""


# =========================================================
# TEST PROVIDER
# =========================================================

async def test_provider(
    name: str,
    provider,
):

    print("\n")
    print("=" * 75)
    print(f"TESTING: {name}")
    print("=" * 75)

    print(
        f"Characters: {len(TEST_TEXT)}"
    )

    start = time.perf_counter()

    try:

        audio_path = await provider.synthesize(
            TEST_TEXT
        )

        total_time = (
            time.perf_counter()
            - start
        )

        path = Path(audio_path)

        print("\nSUCCESS")

        print(
            f"Total generation time: "
            f"{total_time:.3f}s"
        )

        print(
            f"Audio path: {audio_path}"
        )

        if path.exists():

            size_bytes = path.stat().st_size

            size_kb = (
                size_bytes / 1024
            )

            print(
                f"Audio size: "
                f"{size_kb:.2f} KB"
            )

        else:

            print(
                "WARNING: Audio file not found."
            )

        return {
            "name": name,
            "success": True,
            "latency": total_time,
            "audio_path": str(audio_path),
        }

    except Exception as error:

        total_time = (
            time.perf_counter()
            - start
        )

        print("\nFAILED")

        print(
            f"Time before failure: "
            f"{total_time:.3f}s"
        )

        print(
            f"Error: {error}"
        )

        return {
            "name": name,
            "success": False,
            "latency": total_time,
            "error": str(error),
        }


# =========================================================
# MAIN
# =========================================================

async def main():

    print("=" * 75)
    print("LONG TTS BENCHMARK")
    print("=" * 75)

    print("\nTest text:")
    print("-" * 75)
    print(TEST_TEXT)
    print("-" * 75)

    print(
        f"\nTotal characters: "
        f"{len(TEST_TEXT)}"
    )

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

    results = [
        gemini_result,
        elevenlabs_result,
    ]

    print("\n")
    print("=" * 75)
    print("FINAL COMPARISON")
    print("=" * 75)

    print(
        f"{'Provider':<20}"
        f"{'Success':<12}"
        f"{'Latency':<15}"
        f"{'Audio Size':<15}"
    )

    print("-" * 75)

    for result in results:

        if result["success"]:

            path = Path(
                result["audio_path"]
            )

            if path.exists():

                size_kb = (
                    path.stat().st_size
                    / 1024
                )

                size_text = (
                    f"{size_kb:.2f} KB"
                )

            else:

                size_text = "N/A"

        else:

            size_text = "N/A"


        print(
            f"{result['name']:<20}"
            f"{str(result['success']):<12}"
            f"{result['latency']:.3f}s"
            f"{'':<8}"
            f"{size_text:<15}"
        )

    # =====================================================
    # FASTEST
    # =====================================================

    successful = [
        result
        for result in results
        if result["success"]
    ]

    if successful:

        fastest = min(
            successful,
            key=lambda result: result["latency"]
        )

        print("\n")
        print("=" * 75)
        print("FASTEST PROVIDER")
        print("=" * 75)

        print(
            f"{fastest['name']}"
        )

        print(
            f"Latency: "
            f"{fastest['latency']:.3f}s"
        )

        print("=" * 75)


if __name__ == "__main__":

    asyncio.run(main())