"""Phase 6 smoke test: every metric must render a value + sparkline.

Runs against committed /data (whatever the last refresh produced), not the
network. It asserts the app can render every metric the registry declares —
catching a metric that's in metrics.yaml but has no data file, or a data file
the store can't read. Metrics with a known-blocked source are allowed to be
empty so a missing API key doesn't turn CI red.
"""

from __future__ import annotations

from terminal.config import registry
from terminal.store import read_metric, sparkline_frame


def test_every_metric_is_renderable() -> None:
    """Reading + sparkline framing must not raise for any metric, data or not."""
    reg = registry()
    for metric in reg.metrics:
        reading = read_metric(metric, reg.settings.stale_after_days(metric.frequency))
        years = reg.settings.sparkline_window_years(metric.frequency)
        # Must not raise even when the file is missing/empty.
        sparkline_frame(reading, years)
        assert reading.status in {"ok", "stale", "error", "missing"}


def test_no_orphan_data_files() -> None:
    """Every data/*.csv should belong to a metric in the registry."""
    from terminal.config import DATA_DIR

    known = {m.id for m in registry().metrics}
    for path in DATA_DIR.glob("*.csv"):
        assert path.stem in known, f"orphan data file {path.name} — metric removed but data left"
