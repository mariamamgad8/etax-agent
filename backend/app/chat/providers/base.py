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

    def mark(self, key: str) -> None:
        with self._lock:
            self._until[key] = time.monotonic() + self._seconds
