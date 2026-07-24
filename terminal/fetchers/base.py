"""The fetcher contract.

A fetcher takes a Metric and returns its full observed series. It may raise
anything at all — the runner catches per-metric, so one dead source can never
take down the job or any other tile. That isolation is the whole point.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

import requests

# (as_of, value) pairs, any order; the runner sorts and dedupes.
Series = list[tuple[date, float]]
Fetcher = Callable[..., Series]

USER_AGENT = "finance-terminal/0.1 (+https://github.com/dylanlayden/finance-terminal)"
TIMEOUT = 60


class FetchError(RuntimeError):
    """A source failed in a way we understand. Message lands in the run summary."""


def http_get(url: str, params: dict | None = None, timeout: int = TIMEOUT) -> requests.Response:
    """One place for headers, timeouts, and error shape."""
    response = requests.get(
        url, params=params, timeout=timeout, headers={"User-Agent": USER_AGENT}
    )
    if response.status_code != 200:
        raise FetchError(f"HTTP {response.status_code} from {response.url.split('?')[0]}")
    return response


_REGISTRY: dict[str, Fetcher] = {}


def register(name: str) -> Callable[[Fetcher], Fetcher]:
    def decorator(fn: Fetcher) -> Fetcher:
        _REGISTRY[name] = fn
        return fn

    return decorator


def get_fetcher(source: str) -> Fetcher:
    if source not in _REGISTRY:
        raise FetchError(f"no fetcher registered for source {source!r}")
    return _REGISTRY[source]


def registered_sources() -> list[str]:
    return sorted(_REGISTRY)
