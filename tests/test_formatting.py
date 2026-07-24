"""Change semantics are the easiest thing to get quietly wrong (D6, D7, D9)."""

from __future__ import annotations

import pytest

from terminal.config import Metric
from terminal.formatting import (
    EMPTY,
    change_direction,
    format_change,
    format_value,
)


def metric(**overrides) -> Metric:
    base = dict(
        id="m",
        dashboard="macro",
        label="M",
        source="fred",
        series_id="X",
        unit="%",
        frequency="daily",
        change_style="pp",
        source_url="https://example.test",
    )
    base.update(overrides)
    return Metric(**base)


@pytest.mark.parametrize(
    ("unit", "value", "expected"),
    [
        ("%", 4.276, "4.28%"),
        ("$/bbl", 82.1449, "$82.14"),
        ("$/lb", 4.3512, "$4.35"),
        ("thousands SAAR", 1450.4, "1,450k"),
        ("index", 6142.3, "6,142"),
        ("count", 812345.0, "812,345"),
        ("ratio", 0.917, "0.92"),
        ("bps", 0.18, "18 bps"),
    ],
)
def test_format_value_infers_from_unit(unit: str, value: float, expected: str) -> None:
    assert format_value(value, metric(unit=unit, change_style="pct")) == expected


def test_missing_value_renders_placeholder() -> None:
    assert format_value(None, metric()) == EMPTY


def test_rate_change_is_percentage_points_not_percent() -> None:
    """4.10 -> 4.28 is +0.18 pp. Rendering '+4.4%' would be misleading."""
    assert format_change(4.28, 4.10, metric(change_style="pp")) == "+0.18 pp"


def test_spread_change_is_bps() -> None:
    assert format_change(0.30, 0.12, metric(unit="bps", change_style="bps")) == "+18 bps"


def test_price_change_is_percent() -> None:
    assert format_change(110.0, 100.0, metric(unit="$/bbl", change_style="pct")) == "+10.00%"


def test_negative_price_change_keeps_sign() -> None:
    assert format_change(90.0, 100.0, metric(unit="$/bbl", change_style="pct")) == "-10.00%"


def test_change_needs_a_previous_reading() -> None:
    assert format_change(4.28, None, metric()) == EMPTY


def test_zero_previous_does_not_divide_by_zero() -> None:
    assert format_change(1.0, 0.0, metric(unit="index", change_style="pct")) == EMPTY


@pytest.mark.parametrize(
    ("current", "previous", "expected"),
    [(2.0, 1.0, "up"), (1.0, 2.0, "down"), (1.0, 1.0, "flat"), (1.0, None, "none")],
)
def test_direction_is_purely_directional(current, previous, expected) -> None:
    """Green = up, red = down, for every metric. No good/bad polarity (D7)."""
    assert change_direction(current, previous) == expected
