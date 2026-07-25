"""The app must render against an empty /data, a partial one, and a stale one."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from terminal.config import Metric
from terminal.store import content_stamp, load_series, read_metric, sparkline_frame


def metric(tmp_path: Path, frequency: str = "daily", **overrides) -> Metric:
    base = dict(
        id="wti_crude",
        dashboard="commodities",
        label="WTI",
        source="fred",
        series_id="DCOILWTICO",
        unit="$/bbl",
        frequency=frequency,
        change_style="pct",
        source_url="https://example.test",
    )
    base.update(overrides)
    m = Metric(**base)
    object.__setattr__(m, "id", base["id"])
    return m


def write_csv(tmp_path: Path, rows: list[tuple[str, float | None, str]]) -> Path:
    path = tmp_path / "wti_crude.csv"
    pd.DataFrame(rows, columns=["as_of", "value", "status"]).to_csv(path, index=False)
    return path


def patched(monkeypatch, tmp_path: Path, m: Metric) -> Metric:
    monkeypatch.setattr(type(m), "data_path", property(lambda self: tmp_path / f"{self.id}.csv"))
    return m


def test_missing_file_is_not_an_error(monkeypatch, tmp_path: Path) -> None:
    m = patched(monkeypatch, tmp_path, metric(tmp_path))
    assert load_series(m).empty
    reading = read_metric(m, stale_after_days=2)
    assert reading.status == "missing"
    assert reading.value is None


def test_reads_latest_and_previous(monkeypatch, tmp_path: Path) -> None:
    m = patched(monkeypatch, tmp_path, metric(tmp_path))
    write_csv(tmp_path, [("2026-07-21", 80.0, "ok"), ("2026-07-22", 82.0, "ok")])
    reading = read_metric(m, stale_after_days=2, today=date(2026, 7, 23))
    assert (reading.value, reading.previous) == (82.0, 80.0)
    assert reading.as_of == date(2026, 7, 22)


def test_previous_is_previous_available_reading(monkeypatch, tmp_path: Path) -> None:
    """Gaps (holidays, failed pulls) must not become a null 'previous'."""
    m = patched(monkeypatch, tmp_path, metric(tmp_path))
    write_csv(
        tmp_path,
        [("2026-07-20", 79.0, "ok"), ("2026-07-21", None, "error"), ("2026-07-22", 82.0, "ok")],
    )
    reading = read_metric(m, stale_after_days=2, today=date(2026, 7, 23))
    assert (reading.value, reading.previous) == (82.0, 79.0)


def test_daily_metric_goes_stale(monkeypatch, tmp_path: Path) -> None:
    m = patched(monkeypatch, tmp_path, metric(tmp_path))
    write_csv(tmp_path, [("2026-07-10", 80.0, "ok")])
    assert read_metric(m, stale_after_days=2, today=date(2026, 7, 23)).status == "stale"


def test_monthly_metric_is_healthy_at_25_days(monkeypatch, tmp_path: Path) -> None:
    """A 25-day-old CPI reading is normal, not broken (D12)."""
    m = patched(monkeypatch, tmp_path, metric(tmp_path, frequency="monthly"))
    write_csv(tmp_path, [("2026-06-28", 3.1, "ok")])
    assert read_metric(m, stale_after_days=62, today=date(2026, 7, 23)).status == "ok"


def test_sparkline_window_trims_to_lookback(monkeypatch, tmp_path: Path) -> None:
    m = patched(monkeypatch, tmp_path, metric(tmp_path))
    write_csv(
        tmp_path,
        [("2019-01-02", 50.0, "ok"), ("2026-01-02", 75.0, "ok"), ("2026-07-22", 82.0, "ok")],
    )
    reading = read_metric(m, stale_after_days=2, today=date(2026, 7, 23))
    window = sparkline_frame(reading, years=1, today=date(2026, 7, 23))
    assert len(window) == 2


class TestContentStamp:
    """The stamp is the cache-buster that lets a redeploy/refresh show without a
    reboot — it must actually change when the tracked files change."""

    def test_changes_when_a_file_is_added(self, tmp_path: Path) -> None:
        a = tmp_path / "gold.csv"
        a.write_text("x")
        before = content_stamp([a])
        b = tmp_path / "silver.csv"
        b.write_text("y")
        after = content_stamp([a, b])
        assert before != after

    def test_changes_when_a_file_is_rewritten(self, tmp_path: Path) -> None:
        import os

        a = tmp_path / "gold.csv"
        a.write_text("v1")
        before = content_stamp([a])
        a.write_text("v2")
        os.utime(a, ns=(2_000_000_000_000_000_000, 2_000_000_000_000_000_000))
        assert content_stamp([a]) != before

    def test_missing_files_are_skipped_not_fatal(self, tmp_path: Path) -> None:
        present = tmp_path / "gold.csv"
        present.write_text("x")
        stamp = content_stamp([present, tmp_path / "not_there.csv"])
        assert "gold.csv" in stamp and "not_there.csv" not in stamp
