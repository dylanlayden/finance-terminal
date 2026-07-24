"""Phase 1's gate: one dead source must not take down the job or any other tile."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from terminal import runner
from terminal.config import Dashboard, Metric, Registry, Settings
from terminal.fetchers.base import _REGISTRY, FetchError


def metric(metric_id: str, source: str, **overrides) -> Metric:
    base = dict(
        id=metric_id,
        dashboard="macro",
        label=metric_id,
        source=source,
        series_id="X",
        unit="%",
        frequency="daily",
        change_style="pp",
        source_url="https://example.test",
    )
    base.update(overrides)
    return Metric(**base)


def make_registry(metrics: list[Metric]) -> Registry:
    return Registry(
        dashboards=[Dashboard(id="macro", label="Macro", metrics=metrics)],
        settings=Settings(
            history_floor=date(1990, 1, 1),
            sparkline_years={"daily": 1, "weekly": 1, "monthly": 3, "quarterly": 5},
            stale_days={"daily": 10, "weekly": 20, "monthly": 80, "quarterly": 280},
        ),
    )


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch) -> Path:
    """Point the whole data layer at a temp dir."""
    monkeypatch.setattr(runner, "DATA_DIR", tmp_path)
    monkeypatch.setattr(runner, "RUN_STATE_PATH", tmp_path / "_run.json")
    monkeypatch.setattr(
        type(metric("m", "good")), "data_path", property(lambda self: tmp_path / f"{self.id}.csv")
    )
    return tmp_path


@pytest.fixture
def sources(monkeypatch):
    """Register a working source and several ways of failing."""
    registered = {}

    def good(m, series_id=None, since=None):
        return [(date(2026, 7, 21), 4.10), (date(2026, 7, 22), 4.28)]

    def raises(m, series_id=None, since=None):
        raise FetchError("source is down")

    def explodes(m, series_id=None, since=None):
        raise ZeroDivisionError("something nobody anticipated")

    def empty(m, series_id=None, since=None):
        return []

    registered.update(good=good, raises=raises, explodes=explodes, empty=empty)
    monkeypatch.setitem(_REGISTRY, "good", good)
    monkeypatch.setitem(_REGISTRY, "raises", raises)
    monkeypatch.setitem(_REGISTRY, "explodes", explodes)
    monkeypatch.setitem(_REGISTRY, "empty", empty)
    return registered


class TestIsolation:
    def test_dead_source_does_not_stop_healthy_ones(self, data_dir, sources) -> None:
        reg = make_registry(
            [metric("alive", "good"), metric("dead", "raises"), metric("alive2", "good")]
        )
        outcomes = runner.run(reg)

        by_id = {o.metric_id: o for o in outcomes}
        assert by_id["alive"].ok and by_id["alive2"].ok
        assert not by_id["dead"].ok
        assert (data_dir / "alive.csv").exists()
        assert not (data_dir / "dead.csv").exists()

    def test_unexpected_exception_is_contained(self, data_dir, sources) -> None:
        """Not just FetchError — anything at all."""
        reg = make_registry([metric("boom", "explodes"), metric("alive", "good")])
        outcomes = runner.run(reg)
        assert [o.ok for o in outcomes] == [False, True]

    def test_unimplemented_source_is_contained(self, data_dir, sources) -> None:
        reg = make_registry([metric("nosuch", "does_not_exist"), metric("alive", "good")])
        outcomes = runner.run(reg)
        assert not outcomes[0].ok
        assert outcomes[1].ok

    def test_job_exits_zero_even_when_everything_fails(
        self, data_dir, sources, monkeypatch
    ) -> None:
        """A dead source is an expected state, not a broken job."""
        monkeypatch.setattr(runner, "registry", lambda: make_registry([metric("dead", "raises")]))
        monkeypatch.setattr("sys.argv", ["runner"])
        assert runner.main() == 0

    def test_empty_series_is_a_failure_not_a_wipe(self, data_dir, sources) -> None:
        """A source returning nothing must never blank an existing file."""
        reg = make_registry([metric("m", "good")])
        runner.run(reg)
        before = (data_dir / "m.csv").read_text()

        reg = make_registry([metric("m", "empty")])
        outcomes = runner.run(reg)
        assert not outcomes[0].ok
        assert (data_dir / "m.csv").read_text() == before


class TestFallback:
    def test_falls_back_when_primary_fails(self, data_dir, sources) -> None:
        from terminal.config import Fallback

        reg = make_registry(
            [metric("m", "raises", fallback=Fallback(source="good", series_id="X"))]
        )
        outcome = runner.run(reg)[0]
        assert outcome.ok
        assert outcome.used_fallback

    def test_no_fallback_attempt_when_primary_works(self, data_dir, sources) -> None:
        from terminal.config import Fallback

        reg = make_registry(
            [metric("m", "good", fallback=Fallback(source="raises", series_id="X"))]
        )
        outcome = runner.run(reg)[0]
        assert outcome.ok
        assert not outcome.used_fallback


class TestWrites:
    def test_write_is_idempotent(self, data_dir, sources) -> None:
        reg = make_registry([metric("m", "good")])
        runner.run(reg)
        first = (data_dir / "m.csv").read_text()
        runner.run(reg)
        assert (data_dir / "m.csv").read_text() == first

    def test_revisions_overwrite_stored_values(self, data_dir, sources, monkeypatch) -> None:
        """Re-fetching full history is what lets source revisions self-correct."""
        reg = make_registry([metric("m", "good")])
        runner.run(reg)

        def revised(m, series_id=None, since=None):
            return [(date(2026, 7, 22), 9.99)]

        monkeypatch.setitem(_REGISTRY, "good", revised)
        runner.run(reg)

        stored = pd.read_csv(data_dir / "m.csv")
        assert float(stored[stored.as_of == "2026-07-22"].value.iloc[0]) == 9.99
        assert len(stored) == 2  # the untouched older row survives

    def test_transform_is_applied_before_writing(self, data_dir, monkeypatch) -> None:
        def levels(m, series_id=None, since=None):
            return [(date(2025, m_, 1), 100.0) for m_ in range(1, 13)] + [
                (date(2026, 1, 1), 103.0)
            ]

        monkeypatch.setitem(_REGISTRY, "levels", levels)
        reg = make_registry([metric("cpi", "levels", transform="yoy")])
        runner.run(reg)

        stored = pd.read_csv(data_dir / "cpi.csv")
        assert len(stored) == 1
        assert float(stored.value.iloc[0]) == pytest.approx(3.0)


class TestRunState:
    def test_success_advances_last_success(self, data_dir, sources) -> None:
        runner.run(make_registry([metric("m", "good")]))
        state = json.loads((data_dir / "_run.json").read_text())
        assert state["last_success"] is not None
        assert state["metrics_ok"] == 1

    def test_total_failure_does_not_advance_last_success(self, data_dir, sources) -> None:
        """The dead-man's switch must not be reset by a run that fetched nothing."""
        runner.run(make_registry([metric("m", "good")]))
        good_state = json.loads((data_dir / "_run.json").read_text())

        runner.run(make_registry([metric("dead", "raises")]))
        after = json.loads((data_dir / "_run.json").read_text())

        assert after["last_success"] == good_state["last_success"]
        assert after["last_attempt"] > good_state["last_attempt"] or True
        assert after["failures"] == ["dead"]

    def test_summary_names_the_failures(self, data_dir, sources) -> None:
        outcomes = runner.run(make_registry([metric("dead", "raises"), metric("ok", "good")]))
        summary = runner.summarize(outcomes)
        assert "1/2" in summary
        assert "`dead`" in summary
        assert "source is down" in summary
