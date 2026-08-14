import asyncio

from app.services.conversation_service import conversation_service


async def main():

    result = await conversation_service.process_audio(
        session_id="test-session",
        audio_path="tests/audio/record.wav",
    )

    print("\nTRANSCRIPT:")
    print(result["transcript"])

    print("\nLLM RESPONSE:")
    print(result["response"])

    print("\nAUDIO:")
    print(result["audio_path"])


if __name__ == "__main__":
    asyncio.run(main())