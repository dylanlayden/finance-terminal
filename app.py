"""Terminal — read-only view over /data. Never fetches.

Overview is the landing page (D18): all metrics as a compact grid, grouped by
dashboard. The four dashboard pages are the drill-down, with sparklines.
"""

from __future__ import annotations

import streamlit as st

from terminal.config import Registry, registry
from terminal.store import Reading, read_metric, read_run_state
from terminal.ui import inject_css, render_banner, render_grid

st.set_page_config(
    page_title="Terminal",
    page_icon="▚",
    layout="wide",
    # Phone-first: the board is the point, not the nav.
    initial_sidebar_state="collapsed",
)


@st.cache_data(ttl=600)
def _readings_for(dashboard_id: str | None = None) -> list[Reading]:
    reg = registry()
    metrics = (
        reg.metrics
        if dashboard_id is None
        else next(d for d in reg.dashboards if d.id == dashboard_id).metrics
    )
    return [
        read_metric(m, reg.settings.stale_after_days(m.frequency)) for m in metrics
    ]


def _columns(compact: bool) -> int:
    # Phone gets one column; Streamlit collapses columns below ~640px anyway,
    # so this is the desktop density knob.
    return 4 if compact else 3


def overview(reg: Registry) -> None:
    st.markdown("### Overview")
    render_banner(read_run_state(), _readings_for())
    for dashboard in reg.dashboards:
        st.markdown(
            f'<div class="section-head">{dashboard.label}</div>', unsafe_allow_html=True
        )
        render_grid(_readings_for(dashboard.id), reg, _columns(True), compact=True)


def dashboard_page(reg: Registry, dashboard_id: str) -> None:
    dashboard = next(d for d in reg.dashboards if d.id == dashboard_id)
    st.markdown(f"### {dashboard.label}")
    readings = _readings_for(dashboard_id)
    render_banner(read_run_state(), readings)
    render_grid(readings, reg, _columns(False), compact=False)


def main() -> None:
    inject_css()
    reg = registry()

    labels = ["Overview"] + [d.label for d in reg.dashboards]
    choice = st.sidebar.radio("Terminal", labels, label_visibility="collapsed")
    st.sidebar.caption(f"{len(reg.metrics)} metrics · data read-only")

    if choice == "Overview":
        overview(reg)
    else:
        dashboard = next(d for d in reg.dashboards if d.label == choice)
        dashboard_page(reg, dashboard.id)


if __name__ == "__main__":
    main()
