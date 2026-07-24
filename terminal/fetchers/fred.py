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
            f"{var} is set but is not a valid FRED key: expected 32 lowercase "
            f"alphanumeric characters, got {len(key)} chars"
            + (" (contains uppercase)" if key.lower() != key else "")
            + (" (contains non-alphanumeric)" if not key.isalnum() else "")
            + (f" (raw value had {len(raw) - len(key)} chars of whitespace)" if raw != key else "")
        )
    raise FetchError(f"no FRED API key found in any of {KEY_ENV_VARS}")


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
