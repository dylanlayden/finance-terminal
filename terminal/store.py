"""Read side of the data layer. The app only ever reads; the Action writes.

Each metric owns one CSV (D2) holding a snapshot of its full series from the
history floor forward (D1), so a missing file just means "not wired yet" —
never an error.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

from terminal.config import CONFIG_PATH, DATA_DIR, REPO_ROOT, Metric

COLUMNS = ["as_of", "value", "status"]
RUN_STATE_PATH = DATA_DIR / "_run.json"


@dataclass(frozen=True)
class Reading:
    """The latest state of one metric, ready to render."""

    metric: Metric
    value: float | None
    previous: float | None
    as_of: date | None
    status: str  # ok | stale | error | missing
    history: pd.DataFrame

    @property
    def has_data(self) -> bool:
        return self.value is not None

    def age_days(self, today: date | None = None) -> int | None:
        if self.as_of is None:
            return None
        return ((today or date.today()) - self.as_of).days


def empty_series() -> pd.DataFrame:
    return pd.DataFrame({"as_of": pd.Series(dtype="datetime64[ns]"),
                         "value": pd.Series(dtype="float64"),
                         "status": pd.Series(dtype="object")})


def load_series(metric: Metric) -> pd.DataFrame:
    """Full stored history for one metric, oldest first. Empty if unwired."""
    path = metric.data_path
    if not path.exists():
        return empty_series()
    df = pd.read_csv(path, parse_dates=["as_of"])
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"{path.name}: missing columns {missing}")
    return df.sort_values("as_of").reset_index(drop=True)


def read_metric(metric: Metric, stale_after_days: float, today: date | None = None) -> Reading:
    """Latest value + previous *available* reading + per-tile staleness (D12)."""
    history = load_series(metric)
    if history.empty:
        return Reading(metric, None, None, None, "missing", history)

    usable = history[history["value"].notna()]
    if usable.empty:
        return Reading(metric, None, None, None, "error", history)

    latest = usable.iloc[-1]
    previous = usable.iloc[-2]["value"] if len(usable) > 1 else None
    as_of = latest["as_of"].date()

    status = str(latest.get("status", "ok"))
    if status == "ok" and ((today or date.today()) - as_of).days > stale_after_days:
        status = "stale"

    return Reading(
        metric=metric,
        value=float(latest["value"]),
        previous=float(previous) if previous is not None else None,
        as_of=as_of,
        status=status,
        history=history,
    )


def sparkline_frame(reading: Reading, years: int, today: date | None = None) -> pd.DataFrame:
    """Trailing window sized by frequency (D8)."""
    if reading.history.empty:
        return reading.history
    anchor = pd.Timestamp(today or date.today())
    cutoff = anchor - pd.DateOffset(years=years)
    return reading.history[reading.history["as_of"] >= cutoff]


@dataclass(frozen=True)
class RunState:
    """Dead-man's-switch input: when did the job last succeed (D12)."""

    last_success: datetime | None
    failures: list[str]

    @property
    def days_since_success(self) -> int | None:
        if self.last_success is None:
            return None
        return (datetime.now(UTC) - self.last_success).days


def read_run_state(path: Path | None = None) -> RunState:
    path = path or RUN_STATE_PATH
    if not path.exists():
        return RunState(last_success=None, failures=[])
    raw = json.loads(path.read_text())
    ts = raw.get("last_success")
    return RunState(
        last_success=datetime.fromisoformat(ts) if ts else None,
        failures=list(raw.get("failures", [])),
    )


def data_dir_is_empty() -> bool:
    return not any(DATA_DIR.glob("*.csv"))


def content_stamp(paths: list[Path] | None = None) -> str:
    """A cheap fingerprint of everything the board renders from: the config plus
    the per-metric CSVs and run-state the refresh job writes.

    The app process on Streamlit Community Cloud stays warm across a redeploy, so
    a time-based cache (`st.cache_data(ttl=...)`) keeps serving the *old*
    readings until its window lapses — the daily data refresh wouldn't show, and
    a config change never would. Folding this stamp into those cache keys busts
    them the instant any tracked file changes on disk (which a git pull does),
    so new data and config appear without a manual reboot. Missing files are
    skipped, so a not-yet-wired metric never breaks the stamp.
    """
    if paths is None:
        paths = [CONFIG_PATH, RUN_STATE_PATH, *sorted(DATA_DIR.glob("*.csv"))]
    parts: list[str] = []
    for path in paths:
        try:
            parts.append(f"{path.name}:{path.stat().st_mtime_ns}")
        except OSError:
            continue
    return "|".join(parts)


__all__ = [
    "COLUMNS",
    "DATA_DIR",
    "REPO_ROOT",
    "Reading",
    "RunState",
    "content_stamp",
    "data_dir_is_empty",
    "load_series",
    "read_metric",
    "read_run_state",
    "sparkline_frame",
]
