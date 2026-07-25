"""Zillow Research public CSVs — keyless, but wide-format and sometimes large.

Each file is one row per region with a column per month. We select one or more
named rows, then transpose the date columns. A multi-row spec is averaged into
one basket, which is useful for local markets that are best represented by a
small set of city rows.

File choices (smoothed, seasonally adjusted where Zillow publishes an SA
variant — their headline numbers). Inventory has no SA variant; the SA URL
404s, so that one uses the smoothed non-SA file.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime
from io import StringIO

from terminal.config import Metric
from terminal.fetchers.base import FetchError, Series, http_get, register

BASE = "https://files.zillowstatic.com/research/public_csvs"


@dataclass(frozen=True)
class ZillowSeries:
    url: str
    filters: tuple[dict[str, str], ...]
    value_scale: float = 1.0


def city(name: str, state: str) -> dict[str, str]:
    return {"RegionName": name, "RegionType": "city", "StateName": state}


FILES = {
    "zhvi_us_all_homes_sa": ZillowSeries(
        f"{BASE}/zhvi/Metro_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv",
        ({"RegionType": "country"},),
    ),
    "zori_us_sa": ZillowSeries(
        f"{BASE}/zori/Metro_zori_uc_sfrcondomfr_sm_sa_month.csv",
        ({"RegionType": "country"},),
    ),
    "inventory_us_sa": ZillowSeries(
        f"{BASE}/invt_fs/Metro_invt_fs_uc_sfrcondo_sm_month.csv",
        ({"RegionType": "country"},),
    ),
    "zhvi_sf_city": ZillowSeries(
        f"{BASE}/zhvi/City_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv",
        (city("San Francisco", "CA"),),
    ),
    "zori_sf_city": ZillowSeries(
        f"{BASE}/zori/City_zori_uc_sfrcondomfr_sm_month.csv",
        (city("San Francisco", "CA"),),
    ),
    "inventory_sf_city": ZillowSeries(
        f"{BASE}/invt_fs/City_invt_fs_uc_sfrcondo_sm_month.csv",
        (city("San Francisco", "CA"),),
    ),
    "new_listings_sf_city": ZillowSeries(
        f"{BASE}/new_listings/City_new_listings_uc_sfrcondo_sm_month.csv",
        (city("San Francisco", "CA"),),
    ),
    "median_list_price_sf_city": ZillowSeries(
        f"{BASE}/mlp/City_mlp_uc_sfrcondo_sm_month.csv",
        (city("San Francisco", "CA"),),
    ),
    "price_cut_pct_sf_city": ZillowSeries(
        f"{BASE}/mean_listings_price_cut_perc/"
        "City_mean_listings_price_cut_perc_uc_sfrcondo_sm_month.csv",
        (city("San Francisco", "CA"),),
        value_scale=100.0,
    ),
    "days_to_pending_sf_city": ZillowSeries(
        f"{BASE}/mean_doz_pending/City_mean_doz_pending_uc_sfrcondo_sm_month.csv",
        (city("San Francisco", "CA"),),
    ),
    "zhvi_tahoe_basket": ZillowSeries(
        f"{BASE}/zhvi/City_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv",
        (
            city("South Lake Tahoe", "CA"),
            city("Truckee", "CA"),
            city("Tahoe City", "CA"),
            city("Incline Village", "NV"),
            city("Kings Beach", "CA"),
            city("Stateline", "NV"),
            city("Carnelian Bay", "CA"),
            city("Tahoma", "CA"),
            city("Homewood", "CA"),
            city("Tahoe Vista", "CA"),
        ),
    ),
}

META_COLUMNS = {"RegionID", "SizeRank", "RegionName", "RegionType", "StateName"}


@register("zillow")
def fetch(metric: Metric, series_id: str | None = None, since: date | None = None) -> Series:
    key = series_id or metric.series_id
    if key not in FILES:
        raise FetchError(f"unknown Zillow series {key!r}")

    spec = FILES[key]
    rows = list(selected_rows(http_get(spec.url).text, spec.filters))
    if not rows:
        raise FetchError(f"Zillow series {key!r} found no matching region rows")

    return parse_region_rows(rows, since or date(1990, 1, 1), scale=spec.value_scale)


def selected_rows(text: str, filters: tuple[dict[str, str], ...]) -> list[dict[str, str]]:
    rows = []
    for row in csv.DictReader(StringIO(text)):
        if any(matches(row, expected) for expected in filters):
            rows.append(row)
    return rows


def matches(row: dict[str, str], expected: dict[str, str]) -> bool:
    return all((row.get(key) or "").strip() == value for key, value in expected.items())


def parse_region_rows(rows: list[dict[str, str]], since: date, scale: float = 1.0) -> Series:
    by_date: dict[date, list[float]] = {}
    for row in rows:
        for column, raw in row.items():
            if column in META_COLUMNS or raw in ("", None):
                continue
            try:
                as_of = datetime.strptime(str(column), "%Y-%m-%d").date()
            except ValueError:
                continue
            if as_of >= since:
                by_date.setdefault(as_of, []).append(float(raw) * scale)

    if not by_date:
        raise FetchError("Zillow region rows had no dated observations")

    series: Series = []
    for as_of, values in by_date.items():
        series.append((as_of, sum(values) / len(values)))
    return series
