# Sources

Every metric maps to exactly one primary source. Where the spec's frozen table was wrong, dead, or beaten by a free alternative, the substitution is recorded here.

## The Stooq collapse (2026-07-23) — the big one

The spec leaned on Stooq as the primary keyless source for all market data (S&P 500, Nasdaq 100, VIX fallback, copper daily proxy, and the entire equity watchlist). **Stooq now gates its CSV download behind a JavaScript proof-of-work challenge** — a request returns a page that computes a SHA-256 hash puzzle in-browser before the CSV is served. That is deliberate bot-blocking; solving it is both out of bounds (defeating an anti-bot measure) and futile (it retunes and breaks). Stooq was dropped entirely. Every metric that depended on it was rehomed:

| metric | was (Stooq) | now | note |
|---|---|---|---|
| S&P 500 | `^spx` | FRED `SP500` | FRED only keeps ~10 years, but that's plenty for the sparkline |
| Nasdaq 100 | `^ndx` | FRED `NASDAQ100` | same |
| VIX fallback | `^vix` | Cboe `VIX_History.csv` | keyless CDN CSV back to 1990 |
| Copper | `hg.f` daily $/lb | FRED `PCOPPUSDM` monthly $/mt | reverts to the spec's original series; back to ~$9,600/mt, monthly cadence |
| Watchlist (equities) | `spy.us` etc | **deferred** | see below |
| Watchlist (crypto) | `btcusd` | Coinbase public API | keyless; BTC-USD + ETH-USD |

## Other substitutions from the frozen spec table

| metric | spec'd | now | why |
|---|---|---|---|
| Gold | FRED `GOLDAMGBD228NLBM` | FRED, liveness checked each run | The LBMA series was discontinued over licensing and still *returns* stale data that looks healthy. The runner now flags it (see Gold liveness below). The Stooq `xauusd` fallback died with Stooq. **If gold reads stale, it needs a new source — likely a signup.** |
| VIX | Stooq `^vix` | FRED `VIXCLS`, Cboe CSV fallback | same key already in use, no scraping |
| FHFA HPI | FHFA dataset `hpi_po_us` | FRED `HPIPONM226S` | FHFA's own CSV endpoints 404 after a site restructure; FRED mirrors the same purchase-only index (monthly, not quarterly) |

## The watchlist needs a decision (flagged for review)

Individual equity tickers (SPY, QQQ, AAPL, NVDA, MSFT) have **no remaining free, keyless, CI-usable source.** Stooq was it. Every alternative — Finnhub, Alpha Vantage, Tiingo, Twelve Data, Polygon — requires a free-tier signup and an API key that only Dylan can create. Rather than block the build, v1 ships the watchlist with **crypto only** (BTC-USD, ETH-USD via Coinbase, which is keyless). To restore equity tickers, pick a provider, add a key as a GitHub secret, and add one fetcher — the registry row shape already supports it.

## Reliability notes

**Cboe put/call ratio** — no API, no FRED mirror. Read out of the daily market-statistics page's server-rendered payload. Knowingly fragile; when Cboe changes their front end it breaks and the resilience contract sends that one tile stale. It's also the only metric with **no history** — its sparkline accumulates from our own daily pulls.

**Gold liveness** — the FRED LBMA series may be frozen. Rather than hard-code a verdict, the per-tile staleness flag (`as_of` past 2× the daily cadence) will surface it automatically: if gold is dead, its tile shows `stale` within days. Watch for it at first light.

**FRED index history is short** — `SP500`/`NASDAQ100` on FRED only retain ~10 years, and FRED nulls weekends/holidays. Fine for a 1-year sparkline.

## Verification status (live-probed 2026-07-23)

| source | metrics | key required | status |
|---|---|---|---|
| FRED | 19 | yes (`FRED_API`) | endpoint verified live; **key in the secret is malformed — see below** |
| Zillow Research | 3 | no | ✅ all three pull real US-level data |
| Cboe | 2 (VIX fallback, put/call) | no | ✅ both working |
| Coinbase | 2 (crypto watchlist) | no | ✅ working |

**The `FRED_API` secret is not a valid key** — the runner reports it as 105 characters with non-alphanumeric content, where a FRED key is exactly 32 lowercase alphanumeric. Until it's replaced with the real key, all 19 FRED metrics show `error`/`no data`. This is the one blocker only Dylan can clear.
