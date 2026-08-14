import asyncio
import time

from app.core.enums import Provider
from app.providers.provider_factory import provider_factory


AUDIO_PATH = "tests/audio/record.wav"


async def benchmark_provider(provider_name):
    provider = provider_factory.get_provider(provider_name)

    start_time = time.perf_counter()

    try:
        transcript = await provider.transcribe(AUDIO_PATH)

        latency = time.perf_counter() - start_time

        return {
            "provider": provider_name.value,
            "success": True,
            "latency": latency,
            "transcript": transcript,
        }

    except Exception as error:

        latency = time.perf_counter() - start_time

        return {
            "provider": provider_name.value,
            "success": False,
            "latency": latency,
            "error": str(error),
        }


async def main():

    providers = [
        Provider.GROQ,
        Provider.COHERE,
    ]

    print("=" * 70)
    print("SPEECH PROVIDER BENCHMARK")
    print("=" * 70)

    results = []

    for provider in providers:

        print(f"\nTesting {provider.value}...")

        result = await benchmark_provider(provider)

        results.append(result)

        print(f"Success: {result['success']}")
        print(f"Latency: {result['latency']:.2f} seconds")

        if result["success"]:
            print(f"Transcript: {result['transcript']}")
        else:
            print(f"Error: {result['error']}")

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    for result in results:

        print(
            f"{result['provider']:10} | "
            f"Success: {str(result['success']):5} | "
            f"Latency: {result['latency']:.2f}s"
        )


if __name__ == "__main__":
    asyncio.run(main())