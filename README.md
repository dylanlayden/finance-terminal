# Terminal

A phone-friendly board of ~29 personal finance metrics across four dashboards, refreshed once a day from free public sources.

**Live:** https://finance-terminal-cjpwyl4cvpwojgndo766gc.streamlit.app/

The repo is public and the app is reachable by anyone with the URL. That was deliberate: Streamlit Community Cloud's private-app path requires granting their OAuth app the `repo` scope, which is read/write across *every* private repo on the account — far broader than this project needs. Since the app contains only public market data and no personal information, an unlisted public URL leaks nothing. The unguessable subdomain is the obscurity. **Nothing personal or secret belongs in this repo.**

Two decoupled halves. A scheduled GitHub Action fetches data and commits it to `/data`; the Streamlit app only ever *reads* those files. The app never makes a network call to a data source, so a cold start is just a file read.

Spec and decision record live in the Obsidian vault: `Planning/Runs/2026-06-25-finance-dashboard-v1/`.

## Layout

```
app.py                  entry point — Overview + 4 dashboard pages
config/metrics.yaml     the metric registry (the only file you edit day to day)
data/<metric_id>.csv    one file per metric: as_of, value, status
terminal/config.py      loads + strictly validates the registry
terminal/store.py       read side: latest value, previous reading, staleness
terminal/formatting.py  value + change rendering
terminal/ui.py          tile rendering, dark terminal theme
tests/                  fixtures only — never hits a live source
```

## Local development

```bash
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements-dev.txt
```

```bash
streamlit run app.py
```

```bash
pytest -q && ruff check .
```

## Adding a metric

1. Add one row to `config/metrics.yaml`.
2. If it needs a source that doesn't exist yet, add one fetcher under `terminal/fetchers/`.

That's the whole contract, and `tests/test_config.py` enforces it. Required fields: `id`, `dashboard`, `label`, `source`, `series_id`, `unit`, `frequency`, `change_style`, `source_url`. A malformed row fails the tests loudly rather than rendering an empty tile.

`unit` drives number formatting. `frequency` drives both the staleness threshold and the sparkline window. `change_style` decides whether change reads as `%`, `pp`, or `bps` — **any metric whose unit is `%` must use `pp`**, or a yield moving 4.10 → 4.28 renders as a misleading "+4.4%". There's a test for exactly that.

## Design decisions worth knowing

- **Each run fetches the full series**, not just today's print, and upserts by `as_of`. Sparklines are correct on day one and source revisions self-correct. History is floored at 1990.
- **One CSV per metric**, so a daily tick doesn't rewrite a file containing every other metric's decades of history.
- **The job never fails because a source failed.** A dead source leaves its tile on last-good with a `stale` badge; everything else updates normally.
- **Two staleness signals**: a global banner counting days since the last *successful run* (this is the dead-man's switch — GitHub disables crons after 60 days of repo inactivity), and a per-tile flag that fires only past ~2× a metric's own cadence, so a 25-day-old CPI reading is correctly treated as healthy.
- **Colour is direction-only.** Green is up, red is down, for everything. No good/bad polarity.

## Secrets

`FRED_API` — free from [fred.stlouisfed.org](https://fredaccount.stlouisfed.org/apikeys). Lives in GitHub Actions secrets, and in a gitignored `.env` for local runs.

Note the name is `FRED_API`, **not** `FRED_API_KEY` — that's just how it got saved, and renaming would mean re-pasting the key for no benefit. The fetcher reads `FRED_API`.

The key is never needed by the app itself, only by the refresh job, so the deployed Streamlit app holds no secrets at all — its secrets box is empty and should stay that way.
