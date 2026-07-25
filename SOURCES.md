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
| Gold | FRED `GOLDAMGBD228NLBM` | **LBMA `gold_pm`** (keyless daily JSON) | FRED dropped its LBMA spot series over licensing (the id now 404s), so gold briefly ran off a Pax-Gold-on-Coinbase proxy (~4yr history). Replaced with LBMA's own open price feed — the actual settled benchmark, daily $/oz back to 1968 (floored to 1990), no key. See "Precious metals" below. |
| Silver | *(not in spec)* | **LBMA `silver`** (keyless daily JSON) | Added 2026-07-25. Same LBMA feed family as gold; FRED has no live silver spot series either. Daily $/oz back to 1968 (floored to 1990). |
| VIX | Stooq `^vix` | FRED `VIXCLS`, Cboe CSV fallback | same key already in use, no scraping |
| FHFA HPI | FHFA dataset `hpi_po_us` | FRED `HPIPONM226S` | FHFA's own CSV endpoints 404 after a site restructure; FRED mirrors the same purchase-only index (monthly, not quarterly) |

## The watchlist needs a decision (flagged for review)

Individual equity tickers (SPY, QQQ, AAPL, NVDA, MSFT) have **no remaining free, keyless, CI-usable source.** Stooq was it. Every alternative — Finnhub, Alpha Vantage, Tiingo, Twelve Data, Polygon — requires a free-tier signup and an API key that only Dylan can create. Rather than block the build, v1 ships the watchlist with **crypto only** (BTC-USD, ETH-USD via Coinbase, which is keyless). To restore equity tickers, pick a provider, add a key as a GitHub secret, and add one fetcher — the registry row shape already supports it.

## Reliability notes

**Cboe put/call ratio** — no API, no FRED mirror. Read out of the daily market-statistics page's server-rendered payload. Knowingly fragile; when Cboe changes their front end it breaks and the resilience contract sends that one tile stale. It's also the only metric with **no history** — its sparkline accumulates from our own daily pulls.

**Precious metals (gold + silver)** — LBMA publishes its official gold/silver benchmark auction prices as open, keyless JSON at `https://prices.lbma.org.uk/json/<feed>.json` (`gold_pm`, `silver`), one row per day back to 1968: `{"d": "YYYY-MM-DD", "v": [USD, GBP, EUR]}`. The `lbma` fetcher takes the USD leg. This is the real settled benchmark, not a proxy, and needs no signup — the search for a keyless, long-history gold source (FRED discontinued its LBMA spot series; Stooq is bot-gated; PAXG-on-Coinbase had only ~4 years) ends here. If a feed ever changes shape, only that tile goes stale.

**FRED index history is short** — `SP500`/`NASDAQ100` on FRED only retain ~10 years, and FRED nulls weekends/holidays. Fine for a 1-year sparkline.

**Local Zillow markets** — Zillow's public CSVs are still keyless when fetched
directly from `files.zillowstatic.com`, even though the interactive
`zillow.com/research/data/` page may challenge automated browsers. The
`zillow` fetcher now supports named region rows, not just the national
`RegionType == country` row. SF rows use `RegionName == "San Francisco"` and
`StateName == "CA"`. The Tahoe tile is an equal-weight basket of Zillow city
rows around the lake; it is a local-market proxy, **not** lakefront-only
property data. True waterfront segmentation would require MLS/ATTOM/CoreLogic
style property-level data.

**SF construction proxy** — city-level "under construction" is not available
from the existing keyless sources as a clean historical time series. The shipped
tile uses FRED `SANF806BPPRIVSA`: monthly, seasonally adjusted private housing
structures authorized by building permits for the San Francisco-Oakland-Berkeley
MSA. It is a timely construction-pipeline proxy, not an in-construction count.

**Crypto market structure** — CoinGecko's public `/global` endpoint returns a
current snapshot for total crypto market cap, total volume, BTC dominance,
active cryptoassets, and active markets. The free anonymous endpoint does not
provide the full history for these aggregate fields, so those tiles accumulate
history from our daily runner snapshots. DeFiLlama's TVL and stablecoin chart
endpoints return full daily history and remain keyless.

## Verification status (live-probed 2026-07-25)

| source | metrics | key required | status |
|---|---|---|---|
| FRED | 24 | yes (`FRED_API`) | endpoint verified live; **key in the secret is malformed — see below** |
| Zillow Research | 12 | no | ✅ national, SF city, and Tahoe basket CSVs verified |
| Cboe | 2 (VIX fallback, put/call) | no | ✅ both working |
| Coinbase | 2 (crypto watchlist) | no | ✅ working |
| LBMA | 2 (gold, silver) | no | ✅ keyless daily JSON, 1968→present |
| CoinGecko | 5 | no | ✅ keyless `/global`; snapshot history accumulates daily |
| DeFiLlama | 2 | no | ✅ keyless full-history TVL/stablecoin chart endpoints |

**The `FRED_API` secret is not a valid key** — the runner reports it as 105 characters with non-alphanumeric content, where a FRED key is exactly 32 lowercase alphanumeric. Until it's replaced with the real key, FRED metrics show `error`/`no data`. This is the one blocker only Dylan can clear.
