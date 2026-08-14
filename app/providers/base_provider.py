from abc import ABC, abstractmethod


class BaseSpeechProvider(ABC):

    @abstractmethod
    async def transcribe(self, audio_path: str) -> str:
        pass