import os
import requests

from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("ELEVENLABS_API_KEY")

if not api_key:
    raise RuntimeError("ELEVENLABS_API_KEY is missing")

url = "https://api.elevenlabs.io/v1/models"

print("=" * 60)
print("ELEVENLABS CONNECTION TEST")
print("=" * 60)

try:
    response = requests.get(
        url,
        headers={
            "xi-api-key": api_key,
        },
        timeout=20,
    )

    print("HTTP Status:", response.status_code)
    print("Response:", response.text[:500])

except Exception as e:
    print("ERROR:", repr(e))