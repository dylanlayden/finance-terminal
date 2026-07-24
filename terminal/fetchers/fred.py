"""FRED — the workhorse. One free API key covers ~20 of the metrics.

Uses API v1 `series/observations`: we want specific series one at a time,
which is exactly what v1 is shaped for.
"""

from __future__ import annotations

import os
import re
from datetime import date, datetime

from terminal.config import Metric
from terminal.fetchers.base import FetchError, Series, http_get, register

API_URL = "https://api.stlouisfed.org/fred/series/observations"

# The secret is named FRED_API (not FRED_API_KEY) — that's how it was saved
# in GitHub Actions secrets. Both are accepted so a local .env can use either.
KEY_ENV_VARS = ("FRED_API", "FRED_API_KEY")


KEY_PATTERN = re.compile(r"^[a-z0-9]{32}$")


def api_key() -> str:
    """Return the key, or fail with a diagnosis that never prints the key itself.

    FRED rejects malformed keys with a bare HTTP 400, which shows up as ~20
    identical failures and tells you nothing. Checking the shape locally turns
    that into one actionable message.
    """
    for var in KEY_ENV_VARS:
        raw = os.environ.get(var)
        if not raw:
            continue
        key = raw.strip()
        if KEY_PATTERN.match(key):
            return key
        raise FetchError(
            f"{var} is set but is not a valid FRED key "
            f"(expected 32 lowercase alphanumeric chars): {_diagnose(raw, key)}. "
            "A FRED key is the bare 32-char string only — no URL, no 'api_key=', no quotes."
        )
    raise FetchError(f"no FRED API key found in any of {KEY_ENV_VARS}")


def _diagnose(raw: str, key: str) -> str:
    """Characterise a bad key WITHOUT revealing it — the value is a secret."""
    clues = [f"got {len(key)} chars"]
    lowered = key.lower()
    if lowered.startswith(("http://", "https://")):
        clues.append("looks like a URL")
    if "api_key=" in lowered:
        clues.append("contains 'api_key=' — you pasted the whole query string")
    if "=" in key:
        clues.append("contains '='")
    if "&" in key or "?" in key:
        clues.append("contains URL punctuation (?/&)")
    if raw != key:
        clues.append("has surrounding whitespace/newlines")
    if any(c in key for c in "\"'`"):
        clues.append("contains quote characters")
    if key.lower() != key and key.isalnum():
        clues.append("contains uppercase")
    if not key.isalnum() and "=" not in key:
        clues.append("contains non-alphanumeric characters")
    return "; ".join(clues)


@register("fred")
def fetch(metric: Metric, series_id: str | None = None, since: date | None = None) -> Series:
    response = http_get(
        API_URL,
        params={
            "series_id": series_id or metric.series_id,
            "api_key": api_key(),
            "file_type": "json",
            "observation_start": (since or date(1990, 1, 1)).isoformat(),
        },
    )
    payload = response.json()
    if "observations" not in payload:
        raise FetchError(f"unexpected FRED payload: {str(payload)[:160]}")

    series: Series = []
    for observation in payload["observations"]:
        # FRED marks missing readings with "." — holidays, pre-publication gaps.
        raw = observation.get("value", ".")
        if raw in (".", "", None):
            continue
        try:
            value = float(raw)
        except ValueError:
            continue
        series.append((datetime.strptime(observation["date"], "%Y-%m-%d").date(), value))

    if not series:
        raise FetchError(f"no usable observations for {series_id or metric.series_id}")
    return series
