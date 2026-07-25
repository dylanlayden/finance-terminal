"""DeFiLlama public APIs — keyless DeFi and stablecoin history."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from terminal.config import Metric
from terminal.fetchers.base import FetchError, Series, http_get, register

URLS = {
    "defi_tvl_usd": "https://api.llama.fi/charts",
    "stablecoin_supply_usd": "https://stablecoins.llama.fi/stablecoincharts/all",
}


@register("defillama")
def fetch(metric: Metric, series_id: str | None = None, since: date | None = None) -> Series:
    field = series_id or metric.series_id
    if field not in URLS:
        raise FetchError(f"unknown DeFiLlama series {field!r}")

    payload = http_get(URLS[field]).json()
    if not isinstance(payload, list):
        raise FetchError("unexpected DeFiLlama payload")
    floor = since or date(1990, 1, 1)

    series: Series = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        as_of = parse_date(item.get("date"))
        if as_of is None or as_of < floor:
            continue
        value = parse_value(item, field)
        if value is not None:
            series.append((as_of, value))

    if not series:
        raise FetchError(f"no usable DeFiLlama observations for {field}")
    return series


def parse_date(raw: Any) -> date | None:
    try:
        return datetime.fromtimestamp(int(raw), UTC).date()
    except (TypeError, ValueError, OSError):
        return None


def parse_value(item: dict[str, Any], field: str) -> float | None:
    if field == "defi_tvl_usd":
        raw = item.get("totalLiquidityUSD")
    else:
        total = item.get("totalCirculatingUSD")
        raw = total.get("peggedUSD") if isinstance(total, dict) else None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None
