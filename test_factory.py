from app.core.enums import Provider
from app.exceptions.speech_exception import ProviderNotFoundException
from app.providers.provider_factory import provider_factory


provider = provider_factory.get_provider(Provider.GROQ)

print("Provider:", provider)


try:
    provider_factory.get_provider(Provider.COHERE)
except ProviderNotFoundException as error:
    print("Caught:", error)