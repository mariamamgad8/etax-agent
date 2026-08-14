import os
import time

from dotenv import load_dotenv
from groq import Groq

load_dotenv()

client = Groq(
    api_key=os.getenv("GROQ_API_KEY")
)

AUDIO_PATH = "tests/audio/record.wav"

start = time.perf_counter()

with open(AUDIO_PATH, "rb") as audio_file:
    transcription = client.audio.transcriptions.create(
        file=audio_file,
        model="whisper-large-v3-turbo",
        temperature=0,
        response_format="verbose_json"
    )

elapsed = time.perf_counter() - start

print("=" * 60)
print("TRANSCRIPT")
print("=" * 60)
print(transcription.text)

print()
print(f"Latency: {elapsed:.2f} seconds")