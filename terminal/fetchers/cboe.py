"""Cboe — VIX history (clean CSV) and the put/call ratio (knowingly fragile).

VIX_History.csv is a stable public CDN file going back to 1990.

The put/call ratio has no API and no FRED mirror. The daily market-statistics
page is a Next.js app, but the numbers ship inside the server-rendered payload,
so they can be read straight out of the HTML. This is expected to break when
Cboe changes their front end — that's accepted. When it does, the resilience
contract sends this one tile stale and touches nothing else.

Note it yields ONE observation (today's), not a history: this is the only
metric whose sparkline accumulates from our own daily pulls rather than
arriving complete from the source.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from io import StringIO

import pandas as pd

from terminal.config import Metric
from terminal.fetchers.base import FetchError, Series, http_get, register

VIX_HISTORY_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"
MARKET_STATS_URL = "https://www.cboe.com/us/options/market_statistics/daily/"

RATIO_PATTERN = re.compile(
    r'\{\\?"name\\?":\\?"(?P<name>[A-Z0-9 +/]*PUT/CALL RATIO)\\?",'
    r'\\?"value\\?":\\?"(?P<value>[0-9.]+)\\?"\}'
)
DATE_PATTERN = re.compile(r"(20\d{2}-\d{2}-\d{2})")


@register("cboe")
def fetch(metric: Metric, series_id: str | None = None, since: date | None = None) -> Series:
    key = series_id or metric.series_id
    if key == "vix_history":
        return _vix_history(since or date(1990, 1, 1))
    if key == "total_put_call":
        return _total_put_call()
    raise FetchError(f"unknown Cboe series {key!r}")


def _vix_history(since: date) -> Series:
    frame = pd.read_csv(StringIO(http_get(VIX_HISTORY_URL).text))
    frame.columns = [c.strip().upper() for c in frame.columns]
    if "DATE" not in frame.columns or "CLOSE" not in frame.columns:
        raise FetchError(f"unexpected VIX_History columns: {list(frame.columns)[:6]}")

    parsed = pd.to_datetime(frame["DATE"], format="mixed", errors="coerce")
    frame = frame.assign(_d=parsed).dropna(subset=["_d", "CLOSE"])
    return [
        (row._d.date(), float(row.CLOSE))
        for row in frame.itertuples()
        if row._d.date() >= since
    ]


def _total_put_call() -> Series:
    html = http_get(MARKET_STATS_URL).text
    ratios = {m.group("name"): m.group("value") for m in RATIO_PATTERN.finditer(html)}
    if "TOTAL PUT/CALL RATIO" not in ratios:
        raise FetchError(
            f"TOTAL PUT/CALL RATIO not found in Cboe page (found {len(ratios)} ratios) "
            "— front end likely changed"
        )
    return [(_stated_date(html), float(ratios["TOTAL PUT/CALL RATIO"]))]


def _stated_date(html: str) -> date:
    """Prefer the date Cboe states; fall back to today."""
    match = DATE_PATTERN.search(html)
    if match:
        try:
            return datetime.strptime(match.group(1), "%Y-%m-%d").date()
        except ValueError:
            pass
    return date.today()
