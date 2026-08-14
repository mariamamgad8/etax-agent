from pathlib import Path

import keyboard
import sounddevice as sd
import soundfile as sf

SAMPLE_RATE = 16000
CHANNELS = 1

OUTPUT_PATH = Path("tests/audio/record.wav")
OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

print("🎤 Press ENTER to start recording...")
keyboard.wait("enter")

print("🔴 Recording...")
recording = []


def callback(indata, frames, time, status):
    recording.append(indata.copy())


with sd.InputStream(
    samplerate=SAMPLE_RATE,
    channels=CHANNELS,
    callback=callback,
):
    print("⏹ Press ENTER again to stop recording...")
    keyboard.wait("enter")

audio = b""

import numpy as np

audio = np.concatenate(recording, axis=0)

sf.write(OUTPUT_PATH, audio, SAMPLE_RATE)

print(f"✅ Audio saved to: {OUTPUT_PATH}")