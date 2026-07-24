# Sources

Every metric maps to exactly one primary source. Where the spec's frozen table was wrong, dead, or beaten by a free alternative, the substitution is recorded here.

## Substitutions from the frozen spec table

| metric | spec'd | now | why |
|---|---|---|---|
| Gold | FRED `GOLDAMGBD228NLBM` | pending verification; Stooq `xauusd` wired as fallback | FRED's LBMA gold series was discontinued over licensing. The dangerous part is that it still *returns* data — it just stops years ago, so the tile would show a permanently stale value that looks perfectly healthy. Phase 5 must check the last `as_of` and promote the fallback if it's dead. |
| VIX | Stooq `^vix` | FRED `VIXCLS` (Stooq kept as fallback) | Same API key already in use, no scraping, clean full history. |
| Copper | FRED `PCOPPUSDM`, $/mt, monthly | Stooq `hg.f` (COMEX futures), **$/lb**, daily | A daily proxy was preferred over the IMF monthly series, which also publishes with a two-month lag. Note the quote convention changes: ~$4.35/lb, not ~$9,600/mt. |

## Reliability notes

**Cboe put/call ratio** is the most fragile row on the board — no API, no FRED mirror, scraped from daily market-statistics files that change format and block cloud IPs. Knowingly retained. When it breaks, the resilience contract sends that one tile stale and touches nothing else.

**Stooq is primary for market data; yfinance is fallback only** — yfinance scrapes Yahoo and gets blocked from CI IP ranges, so it cannot be relied on from a GitHub runner.

**Zillow** publishes several flavours of each index. This build uses the smoothed, seasonally-adjusted US-level series for ZHVI, ZORI, and for-sale inventory — Zillow's own headline numbers.

**FRED covers 15 of the metrics** on a single free API key.

## Verification status

Series IDs are verified against live source documentation as each is wired, per the spec's instruction not to trust an ID blindly. Table below is updated at each phase gate.

| source | metrics | key required | verified |
|---|---|---|---|
| FRED | 15 | yes (`FRED_API_KEY`) | pending — Phase 2 onward |
| Stooq | 8 (incl. watchlist) | no | pending |
| Zillow Research | 3 | no | pending |
| FHFA | 1 | no | pending |
| Cboe | 1 | no | pending |
