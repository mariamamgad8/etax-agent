import os
import requests

from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("ELEVENLABS_API_KEY")
voice_id = os.getenv("ELEVENLABS_VOICE_ID")

if not api_key:
    raise RuntimeError("ELEVENLABS_API_KEY is missing")

if not voice_id:
    raise RuntimeError("ELEVENLABS_VOICE_ID is missing")

url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

headers = {
    "xi-api-key": api_key,
    "Content-Type": "application/json",
}

payload = {
    "text": "أهلاً بيك، ده اختبار للصوت المصري والإنجليزي.",
    "model_id": "eleven_multilingual_v2",
}

print("=" * 60)
print("ELEVENLABS TTS AUTH TEST")
print("=" * 60)

try:
    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=30,
    )

    print("HTTP Status:", response.status_code)
    print("Content-Type:", response.headers.get("content-type"))

    if response.status_code == 200:
        output_path = "temp/audio/elevenlabs_auth_test.mp3"

        with open(output_path, "wb") as f:
            f.write(response.content)

        print("SUCCESS!")
        print("Audio saved to:", output_path)

    else:
        print("Response:")
        print(response.text[:1000])

except Exception as e:
    print("ERROR:", repr(e))