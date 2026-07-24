"""Zillow Research public CSVs — keyless, but wide-format and large (1-4 MB).

Each file is one row per region with a column per month. We want the single
row where RegionType == "country", then transpose its date columns.

File choices (smoothed, seasonally adjusted where Zillow publishes an SA
variant — their headline numbers). Inventory has no SA variant; the SA URL
404s, so that one uses the smoothed non-SA file.
"""

from __future__ import annotations

from datetime import date, datetime
from io import StringIO

import pandas as pd

from terminal.config import Metric
from terminal.fetchers.base import FetchError, Series, http_get, register

BASE = "https://files.zillowstatic.com/research/public_csvs"

FILES = {
    "zhvi_us_all_homes_sa": f"{BASE}/zhvi/Metro_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv",
    "zori_us_sa": f"{BASE}/zori/Metro_zori_uc_sfrcondomfr_sm_sa_month.csv",
    "inventory_us_sa": f"{BASE}/invt_fs/Metro_invt_fs_uc_sfrcondo_sm_month.csv",
}

META_COLUMNS = 5  # RegionID, SizeRank, RegionName, RegionType, StateName


@register("zillow")
def fetch(metric: Metric, series_id: str | None = None, since: date | None = None) -> Series:
    key = series_id or metric.series_id
    if key not in FILES:
        raise FetchError(f"unknown Zillow series {key!r}")

    frame = pd.read_csv(StringIO(http_get(FILES[key]).text))
    return parse_country_row(frame, since or date(1990, 1, 1))


def parse_country_row(frame: pd.DataFrame, since: date) -> Series:
    national = frame[frame["RegionType"].astype(str).str.strip() == "country"]
    if national.empty:
        raise FetchError("no RegionType=='country' row in Zillow file")

    row = national.iloc[0].iloc[META_COLUMNS:].dropna()
    series: Series = []
    for column, value in row.items():
        try:
            as_of = datetime.strptime(str(column), "%Y-%m-%d").date()
        except ValueError:
            continue  # not a date column
        if as_of >= since:
            series.append((as_of, float(value)))

    if not series:
        raise FetchError("Zillow country row had no dated observations")
    return series
