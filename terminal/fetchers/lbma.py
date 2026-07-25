"""LBMA precious-metal benchmark prices — keyless daily JSON.

The London Bullion Market Association publishes its official gold and silver
benchmark auction prices as open JSON, one file per metal, daily back to 1968.
Each row is ``{"d": "YYYY-MM-DD", "v": [USD, GBP, EUR]}`` — we take the USD leg.

This is the actual settled benchmark (the "spot" reference the market quotes
off), not a proxy, and it needs no API key. Series ids are the feed names:
``gold_pm`` (the PM auction, the standard daily reference) and ``silver``.
"""

from __future__ import annotations

from datetime import date, datetime

from terminal.config import Metric
from terminal.fetchers.base import FetchError, Series, http_get, register

BASE = "https://prices.lbma.org.uk/json"


@register("lbma")
def fetch(metric: Metric, series_id: str | None = None, since: date | None = None) -> Series:
    feed = series_id or metric.series_id
    floor = since or date(1990, 1, 1)
    payload = http_get(f"{BASE}/{feed}.json").json()
    if not isinstance(payload, list):
        raise FetchError(f"unexpected LBMA payload for {feed}: {str(payload)[:160]}")

    series: Series = []
    for row in payload:
        values = row.get("v") or []
        usd = values[0] if values else None
        if usd is None:  # holidays / pre-euro rows carry nulls in the array
            continue
        try:
            as_of = datetime.strptime(row["d"], "%Y-%m-%d").date()
        except (KeyError, ValueError, TypeError):
            continue
        if as_of < floor:
            continue
        series.append((as_of, float(usd)))

    if not series:
        raise FetchError(f"no usable LBMA observations for {feed}")
    return series
