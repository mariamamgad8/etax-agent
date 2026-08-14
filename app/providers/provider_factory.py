from app.core.enums import Provider
from app.exceptions.speech_exception import ProviderNotFoundException
from app.providers.base_provider import BaseSpeechProvider

from app.providers.groq_provider import groq_provider
from app.providers.cohere_provider import cohere_provider
from app.providers.cloudflare_provider import cloudflare_provider


class ProviderFactory:

    def __init__(self):

        self.providers = {
            Provider.GROQ: groq_provider,
            Provider.COHERE: cohere_provider,
            Provider.CLOUDFLARE: cloudflare_provider,
        }

    def get_provider(
        self,
        provider: Provider,
    ) -> BaseSpeechProvider:

        if provider not in self.providers:

            raise ProviderNotFoundException(
                f"Provider '{provider}' is not registered."
            )

        return self.providers[provider]


provider_factory = ProviderFactory()