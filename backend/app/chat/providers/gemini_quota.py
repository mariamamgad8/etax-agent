"""
Classifies a Gemini API failure so callers can decide how long to skip that
(key, model) pair before trying it again, instead of blindly retrying every
configured key on every request regardless of whether it's already known to
be exhausted.

Gemini's 429 response body is structured (confirmed against the installed
google-genai==2.18.1 SDK's raised APIError, whose `.details` is the parsed
JSON error body and whose `.code` is the HTTP status): a QuotaFailure detail
names which quota was hit via `quotaId` (a string containing "PerDay" or
"PerMinute"/"PerSecond"), and a RetryInfo detail gives Google's own
recommended `retryDelay` in seconds. When present, retryDelay is authoritative
and used directly. Otherwise this falls back to skipping a per-day quota
until Google's published reset time (00:00 Pacific = 08:00 UTC) or a short
window for a per-minute quota. Anything that isn't a recognizable quota error
(network blips, auth failures, malformed responses, etc.) gets the caller's
own short generic cooldown instead of a long one, since there's no basis to
assume those need longer.
"""
import re
from datetime import datetime, timedelta, timezone

_QUOTA_RESET_HOUR_UTC = 8  # Gemini free-tier RPD resets at midnight Pacific Time
_MINUTE_QUOTA_BLOCK_SECONDS = 30.0
_UNKNOWN_RATE_LIMIT_BLOCK_SECONDS = 60.0


def _seconds_until_next_utc_reset() -> float:
    now = datetime.now(timezone.utc)
    reset = now.replace(hour=_QUOTA_RESET_HOUR_UTC, minute=0, second=0, microsecond=0)
    if reset <= now:
        reset += timedelta(days=1)
    return (reset - now).total_seconds()


def _parse_retry_delay_seconds(retry_delay) -> float | None:
    """RetryInfo.retryDelay is a protobuf Duration, JSON-encoded as e.g. "45s"."""
    if retry_delay is None:
        return None
    if isinstance(retry_delay, (int, float)):
        return float(retry_delay)
    match = re.match(r"^([\d.]+)s?$", str(retry_delay).strip())
    return float(match.group(1)) if match else None


def gemini_block_seconds(exc: Exception, default_seconds: float) -> tuple[str, float]:
    """
    Returns (reason, seconds_to_block_this_key_for_this_model). `default_seconds`
    is used for anything that isn't a parseable 429 quota error — kept short
    and caller-supplied so it matches whatever generic cooldown the rest of
    the project already uses for non-quota failures.
    """
    code = getattr(exc, "code", None)
    details = getattr(exc, "details", None)
    if code != 429 or not isinstance(details, dict):
        return "other", default_seconds

    inner_error = details.get("error")
    error_body = inner_error if isinstance(inner_error, dict) else details
    detail_items = error_body.get("details") or []

    retry_delay_seconds: float | None = None
    quota_id = ""
    for item in detail_items:
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("@type", ""))
        if item_type.endswith("RetryInfo"):
            retry_delay_seconds = _parse_retry_delay_seconds(item.get("retryDelay"))
        elif item_type.endswith("QuotaFailure"):
            violations = item.get("violations") or []
            if violations and isinstance(violations[0], dict):
                quota_id = violations[0].get("quotaId", "") or violations[0].get("quotaMetric", "")

    if retry_delay_seconds is not None:
        reason = "quota_per_day" if "PerDay" in quota_id else "quota_per_minute"
        return reason, retry_delay_seconds
    if "PerDay" in quota_id:
        return "quota_per_day", _seconds_until_next_utc_reset()
    if quota_id:
        return "quota_per_minute", _MINUTE_QUOTA_BLOCK_SECONDS
    return "rate_limited_unknown", _UNKNOWN_RATE_LIMIT_BLOCK_SECONDS
