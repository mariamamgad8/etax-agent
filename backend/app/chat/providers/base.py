import threading
import time


class ProviderError(Exception):
    """A single provider/model call failed; the caller should try the next one in the fallback chain."""


class AllProvidersExhausted(Exception):
    """Every configured provider/model in a fallback chain failed."""


class CooldownTracker:
    """
    Tracks which provider/model keys are on a temporary cooldown after a
    failure (rate limit, outage, etc.), so the fallback chain skips them for a
    while instead of retrying a model that just rejected a request. V1 is
    intentionally simple: a flat cooldown per key, no rate/latency/cost
    tracking. Thread-safe since FastAPI serves requests concurrently.
    """

    def __init__(self, seconds: int):
        self._seconds = seconds
        self._until: dict[str, float] = {}
        self._lock = threading.Lock()

    def is_cooling_down(self, key: str) -> bool:
        with self._lock:
            until = self._until.get(key)
            if until is None:
                return False
            if time.monotonic() >= until:
                del self._until[key]
                return False
            return True

    def mark(self, key: str, seconds: float | None = None) -> None:
        """`seconds` overrides the tracker's default — used when a caller knows
        a more accurate block duration for this specific failure (e.g. a
        Gemini quota error's own retryDelay) than the generic cooldown."""
        with self._lock:
            self._until[key] = time.monotonic() + (seconds if seconds is not None else self._seconds)


class RotatingStart:
    """
    Thread-safe rotating start index for a fallback list, so repeated calls
    don't always try the same first candidate. Without this, every request
    hits key #1 first — which drives that one key into its own per-minute
    rate limit while the rest of the pool sits unused — instead of spreading
    load evenly across all configured keys.
    """

    def __init__(self):
        self._next = 0
        self._lock = threading.Lock()

    def rotate(self, items: list) -> list:
        if not items:
            return items
        with self._lock:
            start = self._next % len(items)
            self._next += 1
        return items[start:] + items[:start]
