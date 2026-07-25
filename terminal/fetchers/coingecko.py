"""CoinGecko global market snapshot — keyless broad crypto market stats.

The public `/global` endpoint returns current aggregate market statistics, not
a full historical chart on the free anonymous path. The runner upserts one
daily observation, so these tiles build their own history from the day they are
added.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from terminal.config import Metric
from terminal.fetchers.base import FetchError, Series, http_get, register

URL = "https://api.coingecko.com/api/v3/global"


@register("coingecko")
def fetch(metric: Metric, series_id: str | None = None, since: date | None = None) -> Series:
    field = series_id or metric.series_id
    payload = http_get(URL).json()
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        raise FetchError("unexpected CoinGecko global payload")

    value = extract(data, field)
    return [(datetime.now(UTC).date(), value)]


def extract(data: dict[str, Any], field: str) -> float:
    if field == "total_market_cap_usd":
        return nested_float(data, "total_market_cap", "usd")
    if field == "total_volume_usd":
        return nested_float(data, "total_volume", "usd")
    if field == "btc_dominance":
        return nested_float(data, "market_cap_percentage", "btc")
    if field in {"active_cryptocurrencies", "markets"}:
        return float(data[field])
    raise FetchError(f"unknown CoinGecko global field {field!r}")


def nested_float(data: dict[str, Any], parent: str, child: str) -> float:
    values = data.get(parent)
    if not isinstance(values, dict) or child not in values:
        raise FetchError(f"CoinGecko payload missing {parent}.{child}")
    return float(values[child])
