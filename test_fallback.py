import asyncio

from app.core.enums import Provider
from app.services.fallback_service import fallback_service


async def main():

    transcript = await fallback_service.transcribe(
        audio_path="tests/audio/record.wav",
        primary_provider=Provider.GROQ,
        fallback_provider=Provider.COHERE,
    )

    print("Final Transcript:")
    print(transcript)


if __name__ == "__main__":
    asyncio.run(main())