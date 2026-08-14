import asyncio

from app.services.llm_service import llm_service


async def main():

    messages = [
        {
            "role": "user",
            "content": "السلام عليكم، أنا خالد. ممكن تعرفني بنفسك؟"
        }
    ]

    response = await llm_service.generate_response(
        messages
    )

    print("LLM Response:")
    print(response)


if __name__ == "__main__":
    asyncio.run(main())