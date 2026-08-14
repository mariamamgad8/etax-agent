import asyncio
import json
import re
import statistics
import time
from pathlib import Path

from jiwer import wer, cer

from app.core.enums import Provider
from app.providers.provider_factory import provider_factory


# =========================================================
# CONFIGURATION
# =========================================================

DATASET_PATH = Path(
    "tests/evaluation/metadata.json"
)

AUDIO_DIR = Path(
    "tests/evaluation/audio"
)

RESULTS_PATH = Path(
    "stt_benchmark_results.json"
)


PROVIDERS = [
    Provider.GROQ,
    Provider.COHERE,
    Provider.CLOUDFLARE,
]


# =========================================================
# TEXT NORMALIZATION
# =========================================================

def normalize_text(text: str) -> str:

    if not text:
        return ""

    text = text.strip()

    # Arabic diacritics
    text = re.sub(
        r"[\u0617-\u061A\u064B-\u065F\u0670]",
        "",
        text,
    )

    # Arabic normalization
    text = text.replace("أ", "ا")
    text = text.replace("إ", "ا")
    text = text.replace("آ", "ا")
    text = text.replace("ى", "ي")
    text = text.replace("ؤ", "و")
    text = text.replace("ئ", "ي")

    # Remove punctuation
    text = re.sub(
        r"[^\w\s]",
        " ",
        text,
        flags=re.UNICODE,
    )

    # Normalize spaces
    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip().lower()


# =========================================================
# LOAD DATASET
# =========================================================

def load_dataset() -> list[dict]:

    if not DATASET_PATH.exists():

        raise FileNotFoundError(
            f"Dataset not found: {DATASET_PATH}"
        )

    with open(
        DATASET_PATH,
        "r",
        encoding="utf-8",
    ) as file:

        dataset = json.load(file)

    if not isinstance(dataset, list):

        raise ValueError(
            "metadata.json must contain a JSON list."
        )

    return dataset


# =========================================================
# EVALUATE ONE AUDIO WITH ONE PROVIDER
# =========================================================

async def evaluate(
    provider_type: Provider,
    audio_path: Path,
    reference: str,
) -> dict:

    provider = provider_factory.get_provider(
        provider_type
    )

    start = time.perf_counter()

    try:

        transcript = await provider.transcribe(
            str(audio_path)
        )

        latency = (
            time.perf_counter()
            - start
        )

        normalized_reference = normalize_text(
            reference
        )

        normalized_transcript = normalize_text(
            transcript
        )

        word_error_rate = wer(
            normalized_reference,
            normalized_transcript,
        )

        character_error_rate = cer(
            normalized_reference,
            normalized_transcript,
        )

        return {
            "success": True,
            "latency": round(
                latency,
                3,
            ),
            "wer": word_error_rate,
            "cer": character_error_rate,
            "transcript": transcript,
        }

    except Exception as error:

        latency = (
            time.perf_counter()
            - start
        )

        return {
            "success": False,
            "latency": round(
                latency,
                3,
            ),
            "wer": None,
            "cer": None,
            "transcript": None,
            "error": str(error),
        }


# =========================================================
# PROVIDER SUMMARY
# =========================================================

def summarize_provider(
    provider_name: str,
    results: list[dict],
) -> dict:

    successful = [
        result
        for result in results
        if result["success"]
    ]

    if not successful:

        return {
            "provider": provider_name,
            "total_tests": len(results),
            "successful": 0,
            "failed": len(results),
            "success_rate": 0.0,
            "avg_latency": None,
            "median_latency": None,
            "avg_wer": None,
            "avg_cer": None,
        }

    latencies = [
        result["latency"]
        for result in successful
    ]

    wers = [
        result["wer"]
        for result in successful
    ]

    cers = [
        result["cer"]
        for result in successful
    ]

    return {
        "provider": provider_name,
        "total_tests": len(results),
        "successful": len(successful),
        "failed": (
            len(results)
            - len(successful)
        ),
        "success_rate": (
            len(successful)
            / len(results)
        ),
        "avg_latency": statistics.mean(
            latencies
        ),
        "median_latency": statistics.median(
            latencies
        ),
        "avg_wer": statistics.mean(
            wers
        ),
        "avg_cer": statistics.mean(
            cers
        ),
    }


# =========================================================
# PRINT SUMMARY
# =========================================================

def print_summary(
    summaries: list[dict],
):

    print()

    print("=" * 90)
    print("FINAL BENCHMARK")
    print("=" * 90)

    print()

    print(
        f"{'Provider':<15}"
        f"{'Success':<12}"
        f"{'Avg Latency':<15}"
        f"{'Median':<12}"
        f"{'WER':<12}"
        f"{'CER':<12}"
    )

    print("-" * 90)

    for summary in summaries:

        if summary["successful"] == 0:

            print(
                f"{summary['provider']:<15}"
                f"{'0%':<12}"
                f"{'N/A':<15}"
                f"{'N/A':<12}"
                f"{'N/A':<12}"
                f"{'N/A':<12}"
            )

            continue

        print(
            f"{summary['provider']:<15}"
            f"{summary['success_rate'] * 100:.1f}%"
            f"{'':<7}"
            f"{summary['avg_latency']:.2f}s"
            f"{'':<9}"
            f"{summary['median_latency']:.2f}s"
            f"{'':<7}"
            f"{summary['avg_wer'] * 100:.2f}%"
            f"{'':<5}"
            f"{summary['avg_cer'] * 100:.2f}%"
        )


# =========================================================
# BEST PROVIDERS
# =========================================================

def print_best_providers(
    summaries: list[dict],
):

    valid = [
        summary
        for summary in summaries
        if summary["successful"] > 0
    ]

    if not valid:
        return

    best_wer = min(
        valid,
        key=lambda x: x["avg_wer"],
    )

    best_cer = min(
        valid,
        key=lambda x: x["avg_cer"],
    )

    fastest = min(
        valid,
        key=lambda x: x["avg_latency"],
    )

    most_reliable = max(
        valid,
        key=lambda x: x["success_rate"],
    )

    print()

    print("=" * 90)
    print("BEST RESULTS")
    print("=" * 90)

    print()

    print(
        f"Best average WER: "
        f"{best_wer['provider']} "
        f"({best_wer['avg_wer'] * 100:.2f}%)"
    )

    print(
        f"Best average CER: "
        f"{best_cer['provider']} "
        f"({best_cer['avg_cer'] * 100:.2f}%)"
    )

    print(
        f"Fastest average latency: "
        f"{fastest['provider']} "
        f"({fastest['avg_latency']:.2f}s)"
    )

    print(
        f"Most reliable: "
        f"{most_reliable['provider']} "
        f"({most_reliable['success_rate'] * 100:.1f}%)"
    )


# =========================================================
# MAIN
# =========================================================

async def main():

    print("=" * 90)
    print("STT MULTI-RECORDING BENCHMARK")
    print("=" * 90)

    dataset = load_dataset()

    print()

    print(
        f"Dataset size: {len(dataset)} recordings"
    )

    print()

    all_results = []

    # -----------------------------------------------------
    # Test every provider on every recording
    # -----------------------------------------------------

    for provider in PROVIDERS:

        print()
        print("=" * 70)

        print(
            f"PROVIDER: {provider.value.upper()}"
        )

        print("=" * 70)

        provider_results = []

        for index, sample in enumerate(
            dataset,
            start=1,
        ):

            sample_id = sample["id"]

            audio_filename = sample["audio"]

            reference = sample["reference"]

            audio_path = (
                AUDIO_DIR
                / audio_filename
            )

            print()

            print(
                f"[{index}/{len(dataset)}] "
                f"{sample_id}"
            )

            if not audio_path.exists():

                print(
                    f"Audio not found: "
                    f"{audio_path}"
                )

                result = {
                    "success": False,
                    "latency": 0,
                    "wer": None,
                    "cer": None,
                    "transcript": None,
                    "error": "Audio file not found",
                }

            else:

                result = await evaluate(
                    provider_type=provider,
                    audio_path=audio_path,
                    reference=reference,
                )

            result["id"] = sample_id

            result["category"] = sample.get(
                "category",
                "unknown",
            )

            result["reference"] = reference

            provider_results.append(
                result
            )

            all_results.append(
                {
                    "provider": provider.value,
                    **result,
                }
            )

            if result["success"]:

                print(
                    f"Latency: "
                    f"{result['latency']:.2f}s"
                )

                print(
                    f"WER: "
                    f"{result['wer'] * 100:.2f}%"
                )

                print(
                    f"CER: "
                    f"{result['cer'] * 100:.2f}%"
                )

                print(
                    f"Transcript: "
                    f"{result['transcript']}"
                )

            else:

                print(
                    f"ERROR: "
                    f"{result['error']}"
                )


        # -------------------------------------------------
        # Provider summary
        # -------------------------------------------------

        summary = summarize_provider(
            provider.value,
            provider_results,
        )

        print()

        print(
            f"Average WER: "
            f"{summary['avg_wer'] * 100:.2f}%"
            if summary["avg_wer"] is not None
            else "Average WER: N/A"
        )

        print(
            f"Average CER: "
            f"{summary['avg_cer'] * 100:.2f}%"
            if summary["avg_cer"] is not None
            else "Average CER: N/A"
        )

        print(
            f"Average Latency: "
            f"{summary['avg_latency']:.2f}s"
            if summary["avg_latency"] is not None
            else "Average Latency: N/A"
        )

        # Store summary separately
        all_results.append(
            {
                "type": "summary",
                **summary,
            }
        )


    # =====================================================
    # BUILD SUMMARY LIST
    # =====================================================

    summaries = [
        result
        for result in all_results
        if result.get("type") == "summary"
    ]


    # =====================================================
    # PRINT FINAL RESULTS
    # =====================================================

    print_summary(
        summaries
    )

    print_best_providers(
        summaries
    )


    # =====================================================
    # SAVE RESULTS
    # =====================================================

    output = {
        "dataset": str(
            DATASET_PATH
        ),
        "dataset_size": len(dataset),
        "providers": [
            provider.value
            for provider in PROVIDERS
        ],
        "summaries": summaries,
        "results": [
            result
            for result in all_results
            if result.get("type") != "summary"
        ],
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


    print()

    print(
        f"Results saved to: "
        f"{RESULTS_PATH}"
    )


# =========================================================
# ENTRY POINT
# =========================================================

if __name__ == "__main__":

    asyncio.run(
        main()
    )