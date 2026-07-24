"""The refresh job. Fetches every metric, writes /data, never dies.

The contract, in one sentence: a single source failing must not fail the job,
must not touch any other metric's data, and must leave the failed metric's
last-good value on screen with a stale badge.

Exit code is 0 even when sources fail. Failures are reported in the run
summary and in data/_run.json, which the app's banner reads.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from dataclasses import dataclass
from datetime import UTC, date, datetime

import pandas as pd

from terminal import transforms
from terminal.config import DATA_DIR, Metric, Registry, registry
from terminal.fetchers import load_all
from terminal.fetchers.base import get_fetcher
from terminal.store import COLUMNS, RUN_STATE_PATH, load_series

load_all()


@dataclass
class MetricOutcome:
    metric_id: str
    status: str  # ok | error
    rows: int = 0
    latest: float | None = None
    as_of: date | None = None
    detail: str = ""
    used_fallback: bool = False

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def fetch_one(metric: Metric, since: date) -> MetricOutcome:
    """Try primary, then fallback. Any exception becomes an error outcome."""
    attempts: list[tuple[str, str]] = [(metric.source, metric.series_id)]
    if metric.fallback:
        attempts.append((metric.fallback.source, metric.fallback.series_id))

    problems: list[str] = []
    for index, (source, series_id) in enumerate(attempts):
        try:
            series = get_fetcher(source)(metric, series_id=series_id, since=since)
            series = transforms.apply(metric.transform, series)
            if not series:
                raise ValueError("transform produced an empty series")
            rows = write_series(metric, series)
            latest_date, latest_value = max(series)
            return MetricOutcome(
                metric_id=metric.id,
                status="ok",
                rows=rows,
                latest=latest_value,
                as_of=latest_date,
                used_fallback=index > 0,
                detail=f"via {source}" if index > 0 else "",
            )
        except Exception as exc:  # noqa: BLE001 — isolation is the whole point
            problems.append(f"{source}: {type(exc).__name__}: {exc}")
            if os.environ.get("TERMINAL_DEBUG"):
                traceback.print_exc()

    return MetricOutcome(metric_id=metric.id, status="error", detail=" | ".join(problems))


def write_series(metric: Metric, series: list[tuple[date, float]]) -> int:
    """Upsert by as_of and rewrite the file. Idempotent: same input, same file.

    Revisions win — a re-fetched value replaces the stored one for that date,
    which is the point of re-pulling full history rather than appending.
    """
    incoming = pd.DataFrame(
        {
            "as_of": pd.to_datetime([d for d, _ in series]),
            "value": [v for _, v in series],
            "status": "ok",
        }
    )

    existing = load_series(metric)
    combined = (
        pd.concat([existing, incoming], ignore_index=True)
        .drop_duplicates(subset="as_of", keep="last")
        .sort_values("as_of")
        .reset_index(drop=True)
    )

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = combined[COLUMNS].copy()
    out["as_of"] = out["as_of"].dt.strftime("%Y-%m-%d")
    out["value"] = out["value"].map(lambda v: f"{v:.6g}")
    out.to_csv(metric.data_path, index=False)
    return len(out)


def write_run_state(outcomes: list[MetricOutcome], all_failed: bool) -> None:
    """The banner's dead-man's-switch input.

    last_success only advances when the run actually produced data. A run in
    which every source failed must NOT look like a healthy refresh.
    """
    previous = {}
    if RUN_STATE_PATH.exists():
        previous = json.loads(RUN_STATE_PATH.read_text())

    now = datetime.now(UTC).replace(microsecond=0).isoformat()
    state = {
        "last_attempt": now,
        "last_success": previous.get("last_success") if all_failed else now,
        "failures": [o.metric_id for o in outcomes if not o.ok],
        "metrics_ok": sum(1 for o in outcomes if o.ok),
        "metrics_total": len(outcomes),
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RUN_STATE_PATH.write_text(json.dumps(state, indent=2) + "\n")


def summarize(outcomes: list[MetricOutcome]) -> str:
    ok = [o for o in outcomes if o.ok]
    failed = [o for o in outcomes if not o.ok]
    fallbacks = [o for o in ok if o.used_fallback]

    lines = [
        "## Refresh summary",
        "",
        f"- **{len(ok)}/{len(outcomes)}** metrics updated",
    ]
    if fallbacks:
        lines.append(f"- **{len(fallbacks)}** used a fallback source: "
                     + ", ".join(f"`{o.metric_id}` ({o.detail})" for o in fallbacks))
    if failed:
        lines += ["", "### Failed", ""]
        lines += [f"- `{o.metric_id}` — {o.detail}" for o in failed]
    else:
        lines.append("- no failures")
    return "\n".join(lines)


def run(reg: Registry | None = None, only: list[str] | None = None) -> list[MetricOutcome]:
    reg = reg or registry()
    metrics = [m for m in reg.metrics if not only or m.id in only]
    since = reg.settings.history_floor

    outcomes: list[MetricOutcome] = []
    for metric in metrics:
        outcome = fetch_one(metric, since)
        outcomes.append(outcome)
        mark = "ok  " if outcome.ok else "FAIL"
        detail = f"{outcome.rows} rows, latest {outcome.as_of}" if outcome.ok else outcome.detail
        print(f"[{mark}] {metric.id:<22} {detail}", flush=True)

    write_run_state(outcomes, all_failed=not any(o.ok for o in outcomes))
    return outcomes


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh terminal data.")
    parser.add_argument("--only", nargs="*", help="metric ids to refresh (default: all)")
    args = parser.parse_args()

    outcomes = run(only=args.only)
    summary = summarize(outcomes)
    print("\n" + summary)

    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a") as handle:
            handle.write(summary + "\n")

    # Always 0: a dead source is an expected state, not a broken job.
    return 0


if __name__ == "__main__":
    sys.exit(main())
