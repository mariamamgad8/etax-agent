import asyncio

from app.providers.groq_provider import groq_provider


async def main():
    text = await groq_provider.transcribe(
        "tests/audio/record.wav"
    )

    print(text)


asyncio.run(main())