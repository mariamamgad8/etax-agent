import asyncio
import time

from app.providers.cloudflare_provider import (
    cloudflare_provider
)


AUDIO_PATH = "tests/audio/record.wav"


async def main():

    print("=" * 60)
    print("CLOUDFLARE WHISPER STT TEST")
    print("=" * 60)

    print(f"\nAudio: {AUDIO_PATH}")
    print("Sending audio to Cloudflare...")

    start = time.perf_counter()

    try:

        transcript = await cloudflare_provider.transcribe(
            AUDIO_PATH
        )

        elapsed = time.perf_counter() - start

        print("\n" + "=" * 60)
        print("SUCCESS")
        print("=" * 60)

        print("\nTRANSCRIPT:")
        print(transcript)

        print(f"\nLatency: {elapsed:.2f} seconds")

    except Exception as error:

        elapsed = time.perf_counter() - start

        print("\n" + "=" * 60)
        print("ERROR")
        print("=" * 60)

        print(f"\n{error}")

        print(
            f"\nLatency before failure: "
            f"{elapsed:.2f} seconds"
        )


if __name__ == "__main__":
    asyncio.run(main())