import subprocess
from pathlib import Path
import uuid

from app.core.config import config


def main():

    output_dir = Path("temp/audio")
    output_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    output_file = output_dir / f"{uuid.uuid4()}.mp3"

    url = "https://api.fish.audio/v1/tts"

    command = [
        "curl",
        "-k",
        "-X",
        "POST",
        url,

        "-H",
        f"Authorization: Bearer {config.FISH_API_KEY}",

        "-H",
        "Content-Type: application/json",

        "-H",
        f"model: {config.FISH_TTS_MODEL}",

        "-d",
        (
            "{"
            f'"text":"إزيك يا خالد؟ عامل إيه النهاردة؟ '
            'أهلاً بيك في المساعد الصوتي بتاع e-Tax. '
            'إزاي أقدر أساعدك؟",'
            f'"reference_id":"{config.FISH_TTS_VOICE_ID}",'
            '"format":"mp3"'
            "}"
        ),

        "-o",
        str(output_file),
    ]

    print("Calling Fish Audio...")
    print(f"Model: {config.FISH_TTS_MODEL}")
    print(f"Voice configured: {bool(config.FISH_TTS_VOICE_ID)}")

    result = subprocess.run(
        command,
        capture_output=True,
        text=True
    )

    print("Return code:", result.returncode)

    if result.stdout:
        print("STDOUT:")
        print(result.stdout)

    if result.stderr:
        print("STDERR:")
        print(result.stderr)

    if result.returncode == 0 and output_file.exists():

        size = output_file.stat().st_size

        print("Audio generated:")
        print(output_file)
        print(f"Size: {size} bytes")

    else:
        print("Fish Audio request failed.")


if __name__ == "__main__":
    main()