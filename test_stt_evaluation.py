import asyncio
import json
import re
import time
from pathlib import Path

from jiwer import wer, cer

from app.core.enums import Provider
from app.providers.provider_factory import provider_factory


# =========================================================
# CONFIGURATION
# =========================================================

AUDIO_PATH = "tests/audio/record.wav"

RESULTS_PATH = "evaluation_results.json"


# =========================================================
# GROUND TRUTH
# =========================================================
#
# This must represent EXACTLY what was said in the audio.
#
# Current reference for tests/audio/record.wav:
#
# "ماشي احنا حاليا بنعمل model detect the face
#  ف عايزين نعرف هل هو فعلا شغال كويس
#  ولا فيه مشاكل و errors"
#
# =========================================================

REFERENCE = (
    "ماشي احنا حاليا بنعمل model detect the face "
    "ف عايزين نعرف هل هو فعلا شغال كويس "
    "ولا فيه مشاكل و errors"
)


# =========================================================
# PROVIDERS
# =========================================================

PROVIDERS = [
    Provider.GROQ,
    Provider.COHERE,
    Provider.CLOUDFLARE,
]


# =========================================================
# TEXT NORMALIZATION
# =========================================================

def normalize_text(text: str) -> str:
    """
    Normalize Arabic/English text before calculating
    WER and CER.

    We don't want punctuation, extra spaces, or Arabic
    diacritics to affect the evaluation.
    """

    if not text:
        return ""

    text = text.strip()

    # -----------------------------------------------------
    # Remove Arabic diacritics
    # -----------------------------------------------------

    text = re.sub(
        r"[\u0617-\u061A\u064B-\u065F\u0670]",
        "",
        text,
    )

    # -----------------------------------------------------
    # Normalize Arabic characters
    # -----------------------------------------------------

    text = text.replace("أ", "ا")
    text = text.replace("إ", "ا")
    text = text.replace("آ", "ا")

    # Normalize Alef Maksura
    text = text.replace("ى", "ي")

    # Normalize Persian/Arabic variants
    text = text.replace("ؤ", "و")
    text = text.replace("ئ", "ي")

    # -----------------------------------------------------
    # Remove punctuation
    # -----------------------------------------------------

    text = re.sub(
        r"[^\w\s]",
        " ",
        text,
        flags=re.UNICODE,
    )

    # -----------------------------------------------------
    # Normalize whitespace
    # -----------------------------------------------------

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip().lower()


# =========================================================
# EVALUATE ONE PROVIDER
# =========================================================

async def evaluate_provider(
    provider_type: Provider,
) -> dict:

    provider = provider_factory.get_provider(
        provider_type
    )

    start_time = time.perf_counter()

    try:

        print(
            f"Testing {provider_type.value.upper()}..."
        )

        # -------------------------------------------------
        # STT
        # -------------------------------------------------

        transcript = await provider.transcribe(
            AUDIO_PATH
        )

        # -------------------------------------------------
        # Latency
        # -------------------------------------------------

        latency = (
            time.perf_counter()
            - start_time
        )

        # -------------------------------------------------
        # Normalize
        # -------------------------------------------------

        normalized_reference = normalize_text(
            REFERENCE
        )

        normalized_transcript = normalize_text(
            transcript
        )

        # -------------------------------------------------
        # WER
        # -------------------------------------------------

        word_error_rate = wer(
            normalized_reference,
            normalized_transcript,
        )

        # -------------------------------------------------
        # CER
        # -------------------------------------------------

        character_error_rate = cer(
            normalized_reference,
            normalized_transcript,
        )

        # -------------------------------------------------
        # Result
        # -------------------------------------------------

        return {
            "provider": provider_type.value,
            "success": True,
            "latency_seconds": round(
                latency,
                3,
            ),
            "wer": round(
                word_error_rate,
                4,
            ),
            "wer_percent": round(
                word_error_rate * 100,
                2,
            ),
            "cer": round(
                character_error_rate,
                4,
            ),
            "cer_percent": round(
                character_error_rate * 100,
                2,
            ),
            "transcript": transcript,
            "normalized_transcript": normalized_transcript,
        }

    except Exception as error:

        latency = (
            time.perf_counter()
            - start_time
        )

        return {
            "provider": provider_type.value,
            "success": False,
            "latency_seconds": round(
                latency,
                3,
            ),
            "wer": None,
            "wer_percent": None,
            "cer": None,
            "cer_percent": None,
            "transcript": None,
            "normalized_transcript": None,
            "error": str(error),
        }


# =========================================================
# SAVE RESULTS
# =========================================================

def save_results(
    results: list[dict],
):
    """
    Save complete evaluation results to JSON.
    """

    output = {
        "audio": AUDIO_PATH,
        "reference": REFERENCE,
        "normalized_reference": normalize_text(
            REFERENCE
        ),
        "results": results,
    }

    with open(
        RESULTS_PATH,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            output,
            file,
            ensure_ascii=False,
            indent=4,
        )


# =========================================================
# PRINT RESULT
# =========================================================

def print_provider_result(
    result: dict,
):

    print()

    print(
        f"Success: "
        f"{'YES' if result['success'] else 'NO'}"
    )

    print(
        f"Latency: "
        f"{result['latency_seconds']:.2f}s"
    )

    if result["success"]:

        print(
            f"WER: "
            f"{result['wer_percent']:.2f}%"
        )

        print(
            f"CER: "
            f"{result['cer_percent']:.2f}%"
        )

        print()

        print(
            "Transcript:"
        )

        print(
            result["transcript"]
        )

    else:

        print()

        print(
            "Error:"
        )

        print(
            result["error"]
        )

    print(
        "-" * 70
    )


# =========================================================
# FINAL COMPARISON
# =========================================================

def print_comparison(
    results: list[dict],
):

    print()

    print(
        "=" * 70
    )

    print(
        "FINAL COMPARISON"
    )

    print(
        "=" * 70
    )

    print()

    print(
        f"{'Provider':<15}"
        f"{'Success':<10}"
        f"{'Latency':<12}"
        f"{'WER':<12}"
        f"{'CER':<12}"
    )

    print(
        "-" * 70
    )

    for result in results:

        provider = result["provider"]

        success = (
            "YES"
            if result["success"]
            else "NO"
        )

        latency = (
            f"{result['latency_seconds']:.2f}s"
        )

        if result["success"]:

            wer_value = (
                f"{result['wer_percent']:.2f}%"
            )

            cer_value = (
                f"{result['cer_percent']:.2f}%"
            )

        else:

            wer_value = "N/A"
            cer_value = "N/A"

        print(
            f"{provider:<15}"
            f"{success:<10}"
            f"{latency:<12}"
            f"{wer_value:<12}"
            f"{cer_value:<12}"
        )


# =========================================================
# BEST RESULTS
# =========================================================

def print_best_results(
    results: list[dict],
):

    successful_results = [
        result
        for result in results
        if result["success"]
    ]

    if not successful_results:

        print()

        print(
            "No provider succeeded."
        )

        return

    # -----------------------------------------------------
    # Best WER
    # -----------------------------------------------------

    best_wer = min(
        successful_results,
        key=lambda result: result["wer"],
    )

    # -----------------------------------------------------
    # Best CER
    # -----------------------------------------------------

    best_cer = min(
        successful_results,
        key=lambda result: result["cer"],
    )

    # -----------------------------------------------------
    # Fastest
    # -----------------------------------------------------

    fastest = min(
        successful_results,
        key=lambda result: result["latency_seconds"],
    )

    print()

    print(
        "=" * 70
    )

    print(
        "BEST RESULTS"
    )

    print(
        "=" * 70
    )

    print()

    print(
        f"Best WER: "
        f"{best_wer['provider']} "
        f"({best_wer['wer_percent']:.2f}%)"
    )

    print(
        f"Best CER: "
        f"{best_cer['provider']} "
        f"({best_cer['cer_percent']:.2f}%)"
    )

    print(
        f"Fastest: "
        f"{fastest['provider']} "
        f"({fastest['latency_seconds']:.2f}s)"
    )


# =========================================================
# MAIN
# =========================================================

async def main():

    print(
        "=" * 70
    )

    print(
        "STT EVALUATION"
    )

    print(
        "=" * 70
    )

    print()

    print(
        "Audio:"
    )

    print(
        AUDIO_PATH
    )

    print()

    print(
        "Reference:"
    )

    print(
        REFERENCE
    )

    print()

    print(
        "=" * 70
    )


    # -----------------------------------------------------
    # Check audio file
    # -----------------------------------------------------

    audio_file = Path(
        AUDIO_PATH
    )

    if not audio_file.exists():

        print()

        print(
            f"ERROR: Audio file not found:"
        )

        print(
            AUDIO_PATH
        )

        return


    # -----------------------------------------------------
    # Run evaluation
    # -----------------------------------------------------

    results = []

    for provider in PROVIDERS:

        result = await evaluate_provider(
            provider
        )

        results.append(
            result
        )

        print_provider_result(
            result
        )


    # -----------------------------------------------------
    # Comparison
    # -----------------------------------------------------

    print_comparison(
        results
    )


    # -----------------------------------------------------
    # Best results
    # -----------------------------------------------------

    print_best_results(
        results
    )


    # -----------------------------------------------------
    # Save JSON
    # -----------------------------------------------------

    save_results(
        results
    )

    print()

    print(
        f"Results saved to:"
    )

    print(
        RESULTS_PATH
    )

    print()


# =========================================================
# ENTRY POINT
# =========================================================

if __name__ == "__main__":

    asyncio.run(
        main()
    )