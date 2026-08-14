from app.providers.tts.gemini_tts_provider import (
    gemini_tts_provider
)

from app.providers.tts.elevenlabs.elevenlabs_tts_provider import (
    elevenlabs_tts_provider
)

from app.providers.tts.fallback_tts_provider import (
    FallbackTTSProvider
)


# =========================================================
# TTS PROVIDER ROUTER
#
# Current ranking based on latency benchmark:
#
# 1. ElevenLabs -> 3.423s
# 2. Gemini     -> 9.023s
#
# Lower latency is better for a real-time
# voice assistant.
# =========================================================

fallback_tts_provider = FallbackTTSProvider(

    primary=elevenlabs_tts_provider,

    fallback=gemini_tts_provider,

)