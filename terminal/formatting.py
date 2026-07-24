"""Number rendering, inferred from a metric's `unit` (D9).

One formatter driven by the unit column, with a per-metric override escape
hatch. Change is rendered in the metric's native unit (D6): a yield moving
4.10 -> 4.28 is "+0.18 pp", never "+4.4%".
"""

from __future__ import annotations

from terminal.config import Metric

EMPTY = "—"


def format_value(value: float | None, metric: Metric) -> str:
    if value is None:
        return EMPTY
    if metric.format:
        return format(value, metric.format)

    unit = metric.unit
    if unit == "%":
        return f"{value:,.2f}%"
    if unit == "bps":
        # FRED ships T10Y2Y in percentage points; the tile speaks bps.
        return f"{value * 100:,.0f} bps"
    if unit.startswith("$/") or unit == "$" or unit == "price" or unit == "index $":
        return f"${value:,.2f}"
    if unit == "thousands SAAR":
        return f"{value:,.0f}k"
    if unit == "count":
        return f"{value:,.0f}"
    if unit == "ratio":
        return f"{value:,.2f}"
    if unit == "index":
        return f"{value:,.2f}" if value < 100 else f"{value:,.0f}"
    return f"{value:,.2f}"


def format_change(current: float | None, previous: float | None, metric: Metric) -> str:
    """Delta vs the previous *available* reading, in the metric's own unit."""
    if current is None or previous is None:
        return EMPTY

    delta = current - previous
    if metric.change_style == "pp":
        return f"{delta:+,.2f} pp"
    if metric.change_style == "bps":
        return f"{delta * 100:+,.0f} bps"
    if previous == 0:
        return EMPTY
    return f"{delta / abs(previous) * 100:+,.2f}%"


def change_direction(current: float | None, previous: float | None) -> str:
    """Direction only — no good/bad polarity (D7). up | down | flat | none."""
    if current is None or previous is None:
        return "none"
    if current > previous:
        return "up"
    if current < previous:
        return "down"
    return "flat"


def change_period_label(frequency: str) -> str:
    return {
        "daily": "vs prev day",
        "weekly": "vs last week",
        "monthly": "vs last month",
        "quarterly": "vs last quarter",
    }[frequency]


def sparkline_label(frequency: str, years: int) -> str:
    plural = "yr" if years == 1 else "yrs"
    return f"{years} {plural}"
