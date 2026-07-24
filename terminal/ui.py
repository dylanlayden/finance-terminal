"""Tile rendering. Dark terminal aesthetic, phone-first (D17).

Colour is direction-only — green up, red down, no good/bad polarity (D7).
"""

from __future__ import annotations

import html

import altair as alt
import streamlit as st

from terminal.config import Registry
from terminal.formatting import (
    EMPTY,
    change_direction,
    change_period_label,
    format_change,
    format_value,
)
from terminal.store import Reading, RunState, sparkline_frame

CSS = """
<style>
  .stApp { background: #0b0e11; }
  .tile {
    background: #14181d;
    border: 1px solid #232a32;
    border-radius: 6px;
    padding: 0.75rem 0.9rem;
    margin-bottom: 0.6rem;
  }
  .tile-label {
    font-size: 0.7rem;
    letter-spacing: 0.09em;
    text-transform: uppercase;
    color: #7d8a99;
    margin-bottom: 0.35rem;
  }
  .tile-value {
    font-family: "SF Mono", "Roboto Mono", ui-monospace, monospace;
    font-size: 1.6rem;
    font-weight: 600;
    color: #e8edf2;
    line-height: 1.1;
  }
  .tile-value.compact { font-size: 1.2rem; }
  .tile-change {
    font-family: "SF Mono", "Roboto Mono", ui-monospace, monospace;
    font-size: 0.85rem;
    margin-top: 0.2rem;
  }
  .up { color: #2ecc71; }
  .down { color: #ff5c5c; }
  .flat, .none { color: #7d8a99; }
  .tile-meta {
    font-size: 0.68rem;
    color: #5f6b78;
    margin-top: 0.45rem;
    display: flex;
    justify-content: space-between;
    gap: 0.5rem;
  }
  .tile-meta a { color: #5f6b78; text-decoration: none; border-bottom: 1px dotted #3a444f; }
  .tile-meta a:hover { color: #8fa3b8; }
  .badge {
    font-size: 0.6rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    padding: 0.08rem 0.35rem;
    border-radius: 3px;
    margin-left: 0.35rem;
  }
  .badge-stale { background: #4a3a12; color: #e0b352; }
  .badge-error { background: #4a1c1c; color: #ff8080; }
  .badge-missing { background: #232a32; color: #7d8a99; }
  .banner {
    border-radius: 6px;
    padding: 0.6rem 0.9rem;
    margin-bottom: 1rem;
    font-size: 0.85rem;
  }
  .banner-ok { background: #12241a; color: #7fd6a0; border: 1px solid #1e4230; }
  .banner-warn { background: #2a2412; color: #e0b352; border: 1px solid #4a3a12; }
  .banner-bad { background: #2a1414; color: #ff8080; border: 1px solid #4a1c1c; }
  .section-head {
    font-size: 0.72rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #8fa3b8;
    margin: 1.1rem 0 0.5rem;
    border-bottom: 1px solid #232a32;
    padding-bottom: 0.3rem;
  }
</style>
"""

_BADGES = {
    "stale": '<span class="badge badge-stale">stale</span>',
    "error": '<span class="badge badge-error">error</span>',
    "missing": '<span class="badge badge-missing">no data</span>',
}


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def _tile_html(reading: Reading, *, compact: bool) -> str:
    m = reading.metric
    value = format_value(reading.value, m)
    change = format_change(reading.value, reading.previous, m)
    direction = change_direction(reading.value, reading.previous)
    badge = _BADGES.get(reading.status, "")
    as_of = reading.as_of.isoformat() if reading.as_of else "awaiting first run"
    period = change_period_label(m.frequency) if change != EMPTY else ""
    size = " compact" if compact else ""

    return f"""
    <div class="tile">
      <div class="tile-label">{html.escape(m.label)}{badge}</div>
      <div class="tile-value{size}">{value}</div>
      <div class="tile-change {direction}">{change} <span class="flat">{period}</span></div>
      <div class="tile-meta">
        <span>{as_of}</span>
        <a href="{html.escape(m.source_url)}" target="_blank">{html.escape(m.source)}</a>
      </div>
    </div>
    """


# Selectable chart windows (D8 default per frequency, plus a 5yr + full view).
_RANGES = {"1Y": 1, "5Y": 5, "Max": 100}


def _default_range(frequency: str) -> str:
    # Daily/weekly read best over a year; slow series need the longer view.
    return "1Y" if frequency in ("daily", "weekly") else "5Y"


def _x_axis(window) -> alt.Axis:
    """Month abbreviations every other month up close; year ticks when zoomed out."""
    days = (window["as_of"].max() - window["as_of"].min()).days
    if days <= 800:  # ~2yr or less → "Jan, Mar, May, …"
        return alt.Axis(
            format="%b", tickCount={"interval": "month", "step": 2},
            labelAngle=0, title=None, grid=False,
        )
    step = max(1, round(days / 365.25 / 8))  # ~8 year labels, thinned for long spans
    return alt.Axis(
        format="%Y", tickCount={"interval": "year", "step": step},
        labelAngle=0, title=None, grid=False,
    )


def _render_chart(reading: Reading, years: int) -> None:
    """Full-height history chart, dated x-axis + hover — behind a click (B)."""
    window = sparkline_frame(reading, years)
    if len(window) <= 1:
        st.caption("Not enough history yet — the chart fills in as data collects.")
        return
    chart = (
        alt.Chart(window)
        .mark_line(color="#3d7f9e")
        .encode(
            x=alt.X("as_of:T", axis=_x_axis(window)),
            y=alt.Y("value:Q", axis=alt.Axis(title=None)),
            tooltip=[
                alt.Tooltip("as_of:T", title="date"),
                alt.Tooltip("value:Q", title=reading.metric.label),
            ],
        )
        .properties(height=220)
    )
    st.altair_chart(chart, use_container_width=True)


def render_tile(reading: Reading, *, compact: bool = False) -> None:
    st.markdown(_tile_html(reading, compact=compact), unsafe_allow_html=True)
    if not reading.has_data:
        return
    with st.expander("chart"):
        default = _default_range(reading.metric.frequency)
        choice = st.segmented_control(
            "range",
            options=list(_RANGES),
            default=default,
            key=f"range_{reading.metric.id}",
            label_visibility="collapsed",
        )
        _render_chart(reading, _RANGES[choice or default])


def render_grid(
    readings: list[Reading], registry: Registry, columns: int, *, compact: bool
) -> None:
    for row_start in range(0, len(readings), columns):
        cols = st.columns(columns)
        batch = readings[row_start : row_start + columns]
        for col, reading in zip(cols, batch, strict=False):
            with col:
                render_tile(reading, compact=compact)


def render_banner(run_state: RunState, readings: list[Reading]) -> None:
    """Two signals (D12): job age globally, staleness per tile."""
    stale = [r.metric.label for r in readings if r.status in ("stale", "error")]
    days = run_state.days_since_success

    if days is None:
        tone, msg = "banner-warn", "No successful refresh yet — awaiting the first scheduled run."
    elif days >= 3:
        tone, msg = "banner-bad", f"Data is {days} days old — the refresh job may have stopped."
    elif days >= 1:
        tone, msg = "banner-ok", f"Last refreshed {days} day{'s' if days > 1 else ''} ago."
    else:
        tone, msg = "banner-ok", "Refreshed today."

    if stale:
        shown = ", ".join(stale[:4])
        more = f" +{len(stale) - 4} more" if len(stale) > 4 else ""
        msg += f" · Stale: {shown}{more}"

    st.markdown(f'<div class="banner {tone}">{html.escape(msg)}</div>', unsafe_allow_html=True)
