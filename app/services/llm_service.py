from groq import AsyncGroq

from app.core.config import config


class LLMService:

    def __init__(self):
        self.client = AsyncGroq(
            api_key=config.GROQ_API_KEY
        )

        self.model = config.LLM_MODEL

        self.system_prompt = """
You are a helpful Arabic conversational assistant.

Respond naturally and concisely.
Prefer Egyptian Arabic when the user speaks Arabic.
Do not mention internal systems, providers, models, or APIs.
"""

    async def generate_response(
        self,
        messages: list[dict],
    ) -> str:

        conversation = [
            {
                "role": "system",
                "content": self.system_prompt,
            },
            *messages,
        ]

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=conversation,
            temperature=0.3,
        )

        return response.choices[0].message.content


llm_service = LLMService()