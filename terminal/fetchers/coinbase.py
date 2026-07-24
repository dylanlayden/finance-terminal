"""Coinbase Exchange public API — keyless daily candles.

Replaces Stooq for crypto. The endpoint caps each response at 300 candles, so
we page backwards until we reach the history floor or the data runs out.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from terminal.config import Metric
from terminal.fetchers.base import FetchError, Series, http_get, register

BASE = "https://api.exchange.coinbase.com/products"
MAX_CANDLES = 300
DAY = 86_400
MAX_PAGES = 40  # ~33 years of daily candles; far past any real start date


@register("coinbase")
def fetch(metric: Metric, series_id: str | None = None, since: date | None = None) -> Series:
    product = (series_id or metric.series_id).upper()
    floor = since or date(1990, 1, 1)

    collected: dict[date, float] = {}
    window_end = datetime.now(UTC).date()

    for _ in range(MAX_PAGES):
        window_start = max(floor, window_end - timedelta(days=MAX_CANDLES - 1))
        candles = http_get(
            f"{BASE}/{product}/candles",
            params={
                "granularity": DAY,
                "start": window_start.isoformat(),
                "end": window_end.isoformat(),
            },
        ).json()

        if not isinstance(candles, list):
            raise FetchError(f"unexpected Coinbase payload: {str(candles)[:160]}")
        if not candles:
            break

        for candle in candles:
            # [time, low, high, open, close, volume]
            collected[datetime.fromtimestamp(candle[0], UTC).date()] = float(candle[4])

        if window_start <= floor:
            break
        window_end = window_start - timedelta(days=1)

    if not collected:
        raise FetchError(f"Coinbase returned no candles for {product}")
    return sorted(collected.items())
