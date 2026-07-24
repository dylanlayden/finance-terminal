"""The registry is the contract: adding a metric must stay a one-row change."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from terminal.config import ConfigError, load_registry, registry

VALID = """
dashboards:
  - id: macro
    label: Macro
metrics:
  - id: treasury_10yr
    dashboard: macro
    label: 10-Yr Treasury
    source: fred
    series_id: DGS10
    unit: "%"
    frequency: daily
    change_style: pp
    source_url: https://example.test/DGS10
settings:
  history_floor: "1990-01-01"
  sparkline_years: {daily: 1, weekly: 1, monthly: 3, quarterly: 5}
  stale_multiplier: 2.0
"""


def write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "metrics.yaml"
    path.write_text(textwrap.dedent(body))
    return path


def test_loads_valid_config(tmp_path: Path) -> None:
    reg = load_registry(write(tmp_path, VALID))
    assert [d.id for d in reg.dashboards] == ["macro"]
    assert reg.metric("treasury_10yr").change_style == "pp"
    assert reg.settings.history_floor.year == 1990


def test_rejects_unknown_dashboard(tmp_path: Path) -> None:
    body = VALID.replace("dashboard: macro", "dashboard: nope")
    with pytest.raises(ConfigError, match="unknown dashboard"):
        load_registry(write(tmp_path, body))


def test_rejects_bad_frequency(tmp_path: Path) -> None:
    body = VALID.replace("frequency: daily", "frequency: hourly")
    with pytest.raises(ConfigError, match="invalid frequency"):
        load_registry(write(tmp_path, body))


def test_rejects_missing_field(tmp_path: Path) -> None:
    body = VALID.replace("    source_url: https://example.test/DGS10\n", "")
    with pytest.raises(ConfigError, match="source_url"):
        load_registry(write(tmp_path, body))


def test_rejects_duplicate_ids(tmp_path: Path) -> None:
    metric_block = VALID.split("metrics:")[1].split("settings:")[0]
    body = VALID.replace("settings:", f"{metric_block}settings:")
    with pytest.raises(ConfigError, match="duplicate metric id"):
        load_registry(write(tmp_path, body))


class TestRealRegistry:
    """The shipped config must always be valid — this is the smoke test's floor."""

    def test_loads(self) -> None:
        assert len(registry().metrics) > 0

    def test_dashboards_match_spec(self) -> None:
        assert [d.id for d in registry().dashboards] == [
            "commodities",
            "real_estate",
            "macro",
            "equities",
        ]

    def test_every_metric_has_a_source_url(self) -> None:
        assert all(m.source_url.startswith("http") for m in registry().metrics)

    def test_rate_metrics_do_not_use_percent_change(self) -> None:
        """A yield moving 4.10 -> 4.28 must never render as '+4.4%' (D6)."""
        for m in registry().metrics:
            if m.unit == "%":
                assert m.change_style == "pp", f"{m.id} would render a misleading % change"

    def test_watchlist_expands_to_individual_metrics(self) -> None:
        watch = [m for m in registry().metrics if m.id.startswith("watch_")]
        assert len(watch) >= 1
        assert all(m.dashboard == "equities" for m in watch)

    def test_every_source_has_a_fetcher(self) -> None:
        """A metrics.yaml row naming a source nobody implements is a silent
        no-op tile. Catch it here, not in production."""
        from terminal.fetchers import load_all, registered_sources

        load_all()
        available = set(registered_sources())
        for m in registry().metrics:
            assert m.source in available, f"{m.id} names unimplemented source {m.source!r}"
            if m.fallback:
                assert m.fallback.source in available, f"{m.id} fallback {m.fallback.source!r}"

    def test_data_paths_are_one_file_per_metric(self) -> None:
        paths = {m.data_path.name for m in registry().metrics}
        assert len(paths) == len(registry().metrics)
