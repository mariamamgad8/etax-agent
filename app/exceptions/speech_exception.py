class SpeechException(Exception):
    pass


class ProviderNotFoundException(SpeechException):
    pass


class TranscriptionFailedException(SpeechException):
    pass


class InvalidAudioException(SpeechException):
    pass


class ProviderTimeoutException(SpeechException):
    pass