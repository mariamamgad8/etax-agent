from dotenv import load_dotenv
import os

load_dotenv()


class Config:

    # =========================
    # Groq - Speech to Text
    # =========================

    GROQ_API_KEY = os.getenv(
        "GROQ_API_KEY"
    )

    GROQ_MODEL = os.getenv(
        "GROQ_MODEL",
        "whisper-large-v3"
    )


    # =========================
    # Cohere - Speech to Text
    # =========================

    COHERE_API_KEY = os.getenv(
        "COHERE_API_KEY"
    )

    COHERE_MODEL = os.getenv(
        "COHERE_MODEL",
        "cohere-transcribe-arabic-07-2026"
    )


    # =========================
    # Cloudflare - Speech to Text
    # =========================

    CLOUDFLARE_API_TOKEN = os.getenv(
        "CLOUDFLARE_API_TOKEN"
    )

    CLOUDFLARE_ACCOUNT_ID = os.getenv(
        "CLOUDFLARE_ACCOUNT_ID"
    )

    CLOUDFLARE_STT_MODEL = os.getenv(
        "CLOUDFLARE_STT_MODEL",
        "@cf/openai/whisper-large-v3-turbo"
    )


    # =========================
    # LLM
    # =========================

    LLM_MODEL = os.getenv(
        "LLM_MODEL",
        "openai/gpt-oss-20b"
    )


    # =========================
    # Gemini TTS
    # =========================

    GEMINI_API_KEY = os.getenv(
        "GEMINI_API_KEY"
    )

    GEMINI_TTS_MODEL = os.getenv(
        "GEMINI_TTS_MODEL",
        "gemini-2.5-flash-preview-tts"
    )

    GEMINI_TTS_VOICE = os.getenv(
        "GEMINI_TTS_VOICE",
        "Kore"
    )


    # =========================
    # ElevenLabs TTS
    # =========================

    ELEVENLABS_API_KEY = os.getenv(
        "ELEVENLABS_API_KEY"
    )

    ELEVENLABS_MODEL = os.getenv(
        "ELEVENLABS_MODEL",
        "eleven_multilingual_v2"
    )

    ELEVENLABS_VOICE_ID = os.getenv(
        "ELEVENLABS_VOICE_ID"
    )


    # =========================
    # Fish Audio TTS
    # =========================

    FISH_API_KEY = os.getenv(
        "FISH_API_KEY"
    )

    FISH_TTS_MODEL = os.getenv(
        "FISH_TTS_MODEL",
        "s2.1-pro-free"
    )

    FISH_TTS_VOICE_ID = os.getenv(
        "FISH_TTS_VOICE_ID"
    )


config = Config()