"""Load and validate config/metrics.yaml into typed objects.

The registry is the single source of truth for what the terminal displays.
Validation is strict and fails loudly: a typo in the yaml should break the
smoke test, not render a silently-empty tile.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config" / "metrics.yaml"
DATA_DIR = REPO_ROOT / "data"

Frequency = Literal["daily", "weekly", "monthly", "quarterly"]
ChangeStyle = Literal["pct", "pp", "bps"]
Transform = Literal["yoy", "qoq_annualized"]

VALID_FREQUENCIES: set[str] = {"daily", "weekly", "monthly", "quarterly"}
VALID_CHANGE_STYLES: set[str] = {"pct", "pp", "bps"}
VALID_TRANSFORMS: set[str] = {"yoy", "qoq_annualized"}

# Nominal days between readings — drives per-tile staleness (D12).
FREQUENCY_DAYS: dict[str, int] = {
    "daily": 1,
    "weekly": 7,
    "monthly": 31,
    "quarterly": 92,
}


class ConfigError(ValueError):
    """Raised when metrics.yaml is malformed. Always fatal."""


@dataclass(frozen=True)
class Fallback:
    source: str
    series_id: str


@dataclass(frozen=True)
class Metric:
    id: str
    dashboard: str
    label: str
    source: str
    series_id: str
    unit: str
    frequency: Frequency
    change_style: ChangeStyle
    source_url: str
    transform: Transform | None = None
    fallback: Fallback | None = None
    format: str | None = None

    @property
    def data_path(self) -> Path:
        """One file per metric (D2)."""
        return DATA_DIR / f"{self.id}.csv"


@dataclass(frozen=True)
class Dashboard:
    id: str
    label: str
    metrics: list[Metric] = field(default_factory=list)


@dataclass(frozen=True)
class Settings:
    history_floor: date
    sparkline_years: dict[str, int]
    stale_multiplier: float

    def sparkline_window_years(self, frequency: str) -> int:
        return self.sparkline_years[frequency]

    def stale_after_days(self, frequency: str) -> float:
        return FREQUENCY_DAYS[frequency] * self.stale_multiplier


@dataclass(frozen=True)
class Registry:
    dashboards: list[Dashboard]
    settings: Settings

    @property
    def metrics(self) -> list[Metric]:
        return [m for d in self.dashboards for m in d.metrics]

    def metric(self, metric_id: str) -> Metric:
        for m in self.metrics:
            if m.id == metric_id:
                return m
        raise KeyError(metric_id)


def _require(raw: dict, key: str, where: str) -> object:
    if key not in raw or raw[key] in (None, ""):
        raise ConfigError(f"{where}: missing required field {key!r}")
    return raw[key]


def _build_metric(raw: dict, dashboard_ids: set[str]) -> Metric:
    where = f"metric {raw.get('id', '<no id>')!r}"
    for key in (
        "id",
        "dashboard",
        "label",
        "source",
        "series_id",
        "unit",
        "frequency",
        "change_style",
        "source_url",
    ):
        _require(raw, key, where)

    if raw["dashboard"] not in dashboard_ids:
        raise ConfigError(f"{where}: unknown dashboard {raw['dashboard']!r}")
    if raw["frequency"] not in VALID_FREQUENCIES:
        raise ConfigError(f"{where}: invalid frequency {raw['frequency']!r}")
    if raw["change_style"] not in VALID_CHANGE_STYLES:
        raise ConfigError(f"{where}: invalid change_style {raw['change_style']!r}")
    if raw.get("transform") and raw["transform"] not in VALID_TRANSFORMS:
        raise ConfigError(f"{where}: invalid transform {raw['transform']!r}")

    fallback_raw = raw.get("fallback")
    fallback = (
        Fallback(source=fallback_raw["source"], series_id=fallback_raw["series_id"])
        if fallback_raw
        else None
    )

    return Metric(
        id=raw["id"],
        dashboard=raw["dashboard"],
        label=raw["label"],
        source=raw["source"],
        series_id=str(raw["series_id"]),
        unit=str(raw["unit"]),
        frequency=raw["frequency"],
        change_style=raw["change_style"],
        source_url=raw["source_url"],
        transform=raw.get("transform"),
        fallback=fallback,
        format=raw.get("format"),
    )


def _expand_watchlist(raw: dict, dashboard_ids: set[str]) -> list[Metric]:
    """The watchlist block is config sugar: N tickers -> N ordinary metrics."""
    if not raw:
        return []
    return [
        _build_metric(
            {
                "id": f"watch_{ticker['id']}",
                "dashboard": raw["dashboard"],
                "label": ticker["label"],
                "source": raw["source"],
                "series_id": ticker["series_id"],
                "unit": raw["unit"],
                "frequency": raw["frequency"],
                "change_style": raw["change_style"],
                "source_url": f"https://stooq.com/q/?s={ticker['series_id']}",
            },
            dashboard_ids,
        )
        for ticker in raw.get("tickers", [])
    ]


def load_registry(path: Path | None = None) -> Registry:
    """Parse metrics.yaml. Raises ConfigError on anything malformed."""
    path = path or CONFIG_PATH
    raw = yaml.safe_load(path.read_text())

    dashboard_defs = raw.get("dashboards") or []
    if not dashboard_defs:
        raise ConfigError("no dashboards defined")
    dashboard_ids = {d["id"] for d in dashboard_defs}

    metrics = [_build_metric(m, dashboard_ids) for m in raw.get("metrics") or []]
    metrics += _expand_watchlist(raw.get("watchlist") or {}, dashboard_ids)

    seen: set[str] = set()
    for m in metrics:
        if m.id in seen:
            raise ConfigError(f"duplicate metric id {m.id!r}")
        seen.add(m.id)

    settings_raw = raw.get("settings") or {}
    settings = Settings(
        history_floor=date.fromisoformat(settings_raw.get("history_floor", "1990-01-01")),
        sparkline_years=settings_raw.get(
            "sparkline_years", {"daily": 1, "weekly": 1, "monthly": 3, "quarterly": 5}
        ),
        stale_multiplier=float(settings_raw.get("stale_multiplier", 2.0)),
    )
    missing = VALID_FREQUENCIES - set(settings.sparkline_years)
    if missing:
        raise ConfigError(f"settings.sparkline_years missing: {sorted(missing)}")

    # Dashboard order, and metric order within a dashboard, follow the yaml (D18).
    dashboards = [
        Dashboard(
            id=d["id"],
            label=d["label"],
            metrics=[m for m in metrics if m.dashboard == d["id"]],
        )
        for d in dashboard_defs
    ]
    return Registry(dashboards=dashboards, settings=settings)


@lru_cache(maxsize=1)
def registry() -> Registry:
    return load_registry()
