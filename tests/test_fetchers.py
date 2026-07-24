"""Fetcher parsing, against fixtures — never the network.

These lock the response-shape assumptions each fetcher makes, so a source
changing format fails here loudly rather than silently emptying a tile.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from terminal.config import Metric
from terminal.fetchers import cboe, coinbase, fred, zillow
from terminal.fetchers.base import FetchError

FIXTURES = Path(__file__).parent / "fixtures"


def metric(source: str, series_id: str, **overrides) -> Metric:
    base = dict(
        id="m",
        dashboard="macro",
        label="M",
        source=source,
        series_id=series_id,
        unit="%",
        frequency="daily",
        change_style="pp",
        source_url="https://example.test",
    )
    base.update(overrides)
    return Metric(**base)


class FakeResponse:
    def __init__(self, text: str):
        self.text = text

    def json(self):
        return json.loads(self.text)


def serve(monkeypatch, module, fixture: str) -> None:
    body = (FIXTURES / fixture).read_text()
    monkeypatch.setattr(module, "http_get", lambda *a, **k: FakeResponse(body))


class TestFred:
    def test_parses_and_skips_missing(self, monkeypatch) -> None:
        serve(monkeypatch, fred, "fred_dgs10.json")
        monkeypatch.setenv("FRED_API", "a" * 32)
        series = fred.fetch(metric("fred", "DGS10"))
        # The "." observation is dropped, leaving two real readings.
        assert series == [(date(2026, 7, 20), 4.10), (date(2026, 7, 22), 4.28)]

    def test_rejects_malformed_key_without_printing_it(self, monkeypatch) -> None:
        monkeypatch.setenv("FRED_API", "this-is-not-a-valid-key")
        with pytest.raises(FetchError) as exc:
            fred.api_key()
        assert "this-is-not-a-valid-key" not in str(exc.value)
        assert "32" in str(exc.value)

    def test_accepts_a_well_formed_key(self, monkeypatch) -> None:
        monkeypatch.delenv("FRED_API_KEY", raising=False)
        monkeypatch.setenv("FRED_API", "abcdef0123456789abcdef0123456789")
        assert fred.api_key() == "abcdef0123456789abcdef0123456789"


class TestZillow:
    def test_extracts_country_row_only(self, monkeypatch) -> None:
        serve(monkeypatch, zillow, "zillow_zhvi.csv")
        series = zillow.fetch(metric("zillow", "zhvi_us_all_homes_sa"))
        assert series == [(date(2026, 5, 31), 373242.05), (date(2026, 6, 30), 372995.19)]

    def test_unknown_series_is_an_error(self) -> None:
        with pytest.raises(FetchError, match="unknown Zillow series"):
            zillow.fetch(metric("zillow", "not_a_real_file"))


class TestCboe:
    def test_vix_history_parses_us_dates(self, monkeypatch) -> None:
        serve(monkeypatch, cboe, "vix_history.csv")
        series = cboe.fetch(metric("cboe", "vix_history"))
        assert (date(2026, 7, 22), 18.70) in series

    def test_put_call_extracted_from_page_payload(self, monkeypatch) -> None:
        payload = (
            'x __next_f.push([1,"24:[\\"$\\",\\"$L32\\",null,{\\"data\\":{\\"optionsData\\":'
            '{\\"ratios\\":[{\\"name\\":\\"TOTAL PUT/CALL RATIO\\",\\"value\\":\\"0.91\\"},'
            '{\\"name\\":\\"INDEX PUT/CALL RATIO\\",\\"value\\":\\"0.86\\"}]}}}]) '
            "as of 2026-07-22"
        )
        monkeypatch.setattr(cboe, "http_get", lambda *a, **k: FakeResponse(payload))
        series = cboe.fetch(metric("cboe", "total_put_call"))
        assert series == [(date(2026, 7, 22), 0.91)]

    def test_missing_put_call_raises(self, monkeypatch) -> None:
        monkeypatch.setattr(cboe, "http_get", lambda *a, **k: FakeResponse("no ratios here"))
        with pytest.raises(FetchError, match="front end likely changed"):
            cboe.fetch(metric("cboe", "total_put_call"))


class TestCoinbase:
    def test_parses_candles_and_dedupes(self, monkeypatch) -> None:
        body = json.loads((FIXTURES / "coinbase_btc.json").read_text())
        calls = {"n": 0}

        def fake_get(url, params=None, **k):
            # First page returns candles, second returns empty to end the loop.
            calls["n"] += 1
            return FakeResponse(json.dumps(body if calls["n"] == 1 else []))

        monkeypatch.setattr(coinbase, "http_get", fake_get)
        series = coinbase.fetch(metric("coinbase", "BTC-USD"), since=date(2026, 7, 20))
        assert dict(series)[date(2026, 7, 24)] == 65307.0
