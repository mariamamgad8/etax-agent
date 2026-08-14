import asyncio

from app.core.enums import Provider
from app.services.speech_service import speech_service


async def main():
    text = await speech_service.transcribe(
        "tests/audio/record.wav",
        Provider.GROQ,
    )

    print("Transcript:")
    print(text)


if __name__ == "__main__":
    asyncio.run(main())