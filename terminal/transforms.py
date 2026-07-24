"""Derived series: metrics the source publishes as a level but we show as a rate."""

from __future__ import annotations

from datetime import date

Series = list[tuple[date, float]]


def apply(transform: str | None, series: Series) -> Series:
    if transform is None:
        return series
    if transform == "yoy":
        return year_over_year(series)
    if transform == "qoq_annualized":
        return quarter_over_quarter_annualized(series)
    raise ValueError(f"unknown transform {transform!r}")


def year_over_year(series: Series) -> Series:
    """CPI index level -> % change vs the reading ~12 periods earlier.

    Indexed by position, not by calendar date: FRED's monthly series are
    regular, and position-indexing keeps this correct across the odd
    mid-month publication date.
    """
    ordered = sorted(series)
    out: Series = []
    for i in range(12, len(ordered)):
        prior = ordered[i - 12][1]
        if prior:
            out.append((ordered[i][0], (ordered[i][1] / prior - 1.0) * 100.0))
    return out


def quarter_over_quarter_annualized(series: Series) -> Series:
    """Real GDP level -> annualized QoQ growth, the number the BEA headlines."""
    ordered = sorted(series)
    out: Series = []
    for i in range(1, len(ordered)):
        prior = ordered[i - 1][1]
        if prior and ordered[i][1] / prior > 0:
            out.append((ordered[i][0], ((ordered[i][1] / prior) ** 4 - 1.0) * 100.0))
    return out
