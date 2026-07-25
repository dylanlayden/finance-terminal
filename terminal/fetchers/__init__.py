"""Fetcher registry. Import a module and its @register decorator wires it in."""

from __future__ import annotations

from terminal.fetchers.base import FetchError, Series, get_fetcher, registered_sources


def load_all() -> None:
    """Import every fetcher module for its registration side effect."""
    from terminal.fetchers import (  # noqa: F401
        cboe,
        coinbase,
        coingecko,
        defillama,
        fred,
        lbma,
        zillow,
    )


__all__ = ["FetchError", "Series", "get_fetcher", "load_all", "registered_sources"]
