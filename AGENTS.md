# AGENTS.md — finance-terminal

Orientation for any agent working in this repo. The canonical version lives here; `CLAUDE.md` symlinks to it.

## What this is

A private, phone-friendly finance dashboard ("Custom Bloomberg terminal") — 25 metrics across 4 dashboards (Commodities, Real Estate, Macro, Equities & Options), refreshed daily from free public sources. **Python / Streamlit**, deployed on Streamlit Community Cloud. Live: https://finance-terminal-cjpwyl4cvpwojgndo766gc.streamlit.app/

## The mental model (read this first)

Two **decoupled halves**:
1. **Refresh job** (`terminal/runner.py`, run daily by `.github/workflows/refresh.yml`) fetches each metric's *full history* and writes one CSV per metric to `/data/<id>.csv`. It **never dies** — each metric is fetched in isolation; a dead source leaves its tile on last-good and the job still exits 0.
2. **Streamlit app** (`app.py` + `terminal/`) only ever *reads* `/data`. It never fetches. Data lives on `main`, so **every push auto-redeploys the app** with fresh data.

## Load-bearing files

- **`config/metrics.yaml`** — the metric registry. The single source of truth for what the terminal shows. Adding a metric starts (and usually ends) here.
- **`terminal/config.py`** — loads + strictly validates the registry into typed objects.
- **`terminal/runner.py`** — the refresh job; per-metric isolation, upsert-by-date, run-state.
- **`terminal/fetchers/`** — one module per source (`fred`, `zillow`, `cboe`, `coinbase`), each a `@register`-ed function returning `list[(date, value)]`.
- **`terminal/store.py`** — read side: latest value, previous reading, staleness.
- **`terminal/formatting.py`** — value + change rendering. **`terminal/ui.py`** — tiles, dark theme.
- **`README.md`** / **`SOURCES.md`** — user-facing docs and the source-decision record.

## The core promise

**Adding a metric = one row in `config/metrics.yaml` + (only if the source is new) one fetcher.** If you find yourself editing `app.py` or `ui.py` to add an ordinary metric, stop — you're doing it wrong.

## → Adding an indicator: use the skill

The full, self-contained procedure (every field rule, the fetcher contract, which sources work, how to verify and ship) lives in Dylan's vault:

**`~/Desktop/Vault/skills/finance-terminal-add-indicator/SKILL.md`**

Read it before adding or swapping a metric. Highlights that bite if skipped:
- **Any metric whose `unit` is `"%"` MUST use `change_style: pp`** (a test enforces it — a yield shown as "+4.4%" is wrong).
- **Stooq and yfinance are dead** for this repo (bot-gated / IP-blocked); individual equity tickers have no free keyless source.
- `frequency` drives staleness + sparkline window; use the *effective* publication cadence.

## Commands

```bash
./.venv/bin/python -m pytest -q      # tests (fixtures only, never the network)
./.venv/bin/python -m ruff check .   # lint — must be clean
gh workflow run "Refresh data" --repo dylanlayden/finance-terminal   # force a refresh
```

## Guardrails (standing rules)

- **The repo is PUBLIC.** Never commit anything personal or secret. The FRED key is a GitHub Actions secret named `FRED_API`; change it only via `scripts/set_fred_key.sh` (it refuses malformed keys). It must never enter the tree, a commit, or chat.
- **Don't defeat anti-bot measures.** If a free source is gated, tell Dylan it needs a paid/signup feed rather than working around it.
- **A metric that can't be fetched freely + keylessly is a decision for Dylan**, not a silent drop — surface the options.
