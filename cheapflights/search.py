"""The three searches the bot offers.

1. `search_specific`: one route, fixed dates.
2. `search_window`: one route, any departure date inside a window.
3. `search_region`: many destinations in a region, fixed dates.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, timedelta
from statistics import median

from .models import Offer, SearchOptions
from .providers import Provider, ProviderError

# Above this many lookups a search gets slow and risks being rate-limited.
MAX_LOOKUPS = 120


@dataclass
class Lookup:
    origin: str
    destination: str
    depart: date
    return_date: date | None


@dataclass
class SearchResult:
    """Cheapest offer per lookup, sorted by price, plus lookups that failed."""

    offers: list[Offer] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    empty: list[Lookup] = field(default_factory=list)

    @property
    def cheapest(self) -> Offer | None:
        return self.offers[0] if self.offers else None

    def typical_price(self) -> float | None:
        return median(o.price for o in self.offers) if self.offers else None

    def deals(self, threshold: float = 0.2) -> list[Offer]:
        """Offers at least `threshold` (20% by default) below the typical price."""
        typical = self.typical_price()
        if typical is None or len(self.offers) < 3:
            return []
        return [o for o in self.offers if o.price <= typical * (1 - threshold)]


def _run(
    provider: Provider,
    lookups: list[Lookup],
    options: SearchOptions,
    workers: int,
    on_progress: Callable[[int, int], None] | None,
    keep_all: bool = False,
) -> SearchResult:
    if len(lookups) > MAX_LOOKUPS:
        raise ValueError(
            f"This search needs {len(lookups)} lookups (limit {MAX_LOOKUPS}). Narrow the window, nights or region."
        )
    result = SearchResult()
    done = 0

    def one(lk: Lookup):
        try:
            return lk, provider.search(lk.origin, lk.destination, lk.depart, lk.return_date, options), None
        except ProviderError as exc:
            return lk, [], str(exc)

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for lk, offers, error in pool.map(one, lookups):
            done += 1
            if on_progress:
                on_progress(done, len(lookups))
            if error:
                result.errors.append(error)
            elif not offers:
                result.empty.append(lk)
            elif keep_all:
                result.offers.extend(offers)
            else:
                result.offers.append(min(offers, key=lambda o: o.price))

    result.offers.sort(key=lambda o: (o.price, o.depart_date, o.destination))
    return result


def search_specific(
    provider: Provider,
    origin: str,
    destination: str,
    depart: date,
    return_date: date | None,
    options: SearchOptions,
) -> SearchResult:
    """Every offer for one route on fixed dates, cheapest first."""
    _check_dates(depart, return_date)
    lookup = Lookup(origin.upper(), destination.upper(), depart, return_date)
    return _run(provider, [lookup], options, workers=1, on_progress=None, keep_all=True)


def search_window(
    provider: Provider,
    origin: str,
    destination: str,
    window_start: date,
    window_end: date,
    nights: Iterable[int] | None,
    options: SearchOptions,
    workers: int = 3,
    on_progress: Callable[[int, int], None] | None = None,
) -> SearchResult:
    """Cheapest offer for each departure date (and trip length) in the window.

    With `nights=None` the search is one-way. With nights, e.g. range(5, 8),
    every trip of 5, 6 or 7 nights that departs inside the window is priced.
    The return date may fall after the window ends.
    """
    if window_end < window_start:
        raise ValueError("The window ends before it starts.")
    _check_dates(window_start, None)
    nights_list = sorted(set(nights)) if nights is not None else [None]
    if any(n is not None and n < 1 for n in nights_list):
        raise ValueError("Nights must be 1 or more.")

    lookups = []
    day = window_start
    while day <= window_end:
        for n in nights_list:
            ret = day + timedelta(days=n) if n is not None else None
            lookups.append(Lookup(origin.upper(), destination.upper(), day, ret))
        day += timedelta(days=1)
    return _run(provider, lookups, options, workers, on_progress)


def search_region(
    provider: Provider,
    origin: str,
    destinations: list[str],
    depart: date,
    return_date: date | None,
    options: SearchOptions,
    workers: int = 3,
    on_progress: Callable[[int, int], None] | None = None,
) -> SearchResult:
    """Cheapest offer to each destination in the list on fixed dates."""
    _check_dates(depart, return_date)
    origin = origin.upper()
    lookups = [Lookup(origin, d.upper(), depart, return_date) for d in destinations if d.upper() != origin]
    return _run(provider, lookups, options, workers, on_progress)


def _check_dates(depart: date, return_date: date | None) -> None:
    if depart < date.today():
        raise ValueError(f"Departure date {depart} is in the past.")
    if return_date and return_date < depart:
        raise ValueError("Return date is before the departure date.")
