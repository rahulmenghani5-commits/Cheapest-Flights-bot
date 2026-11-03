"""Flight price sources.

A provider answers one question: "what does it cost to fly from A to B on this
date (and back on that date)?" Everything else in the bot is built on top of
that, so switching to a paid API later only means adding another provider.
"""

from __future__ import annotations

import hashlib
import random
import time
from datetime import date
from typing import Protocol

from .models import Offer, SearchOptions


class ProviderError(RuntimeError):
    """The provider could not answer (blocked, network error, bad airport...)."""


class Provider(Protocol):
    def search(
        self,
        origin: str,
        destination: str,
        depart: date,
        return_date: date | None,
        options: SearchOptions,
    ) -> list[Offer]: ...


class GoogleFlightsProvider:
    """Reads Google Flights through the `fast-flights` library. No API key needed.

    It is an unofficial scraper, so Google can rate-limit or change the page.
    A small delay between requests keeps the bot polite.
    """

    def __init__(self, delay_seconds: float = 1.0, proxy: str | None = None):
        self.delay_seconds = delay_seconds
        self.proxy = proxy

    def search(self, origin, destination, depart, return_date, options):
        try:
            from fast_flights import FlightQuery, FlightsNotFound, Passengers, create_query, get_flights
        except ImportError as exc:  # pragma: no cover - depends on install
            raise ProviderError(f"could not load fast-flights ({exc}). Run: pip install -r requirements.txt") from exc

        legs = [FlightQuery(date=depart.isoformat(), from_airport=origin, to_airport=destination)]
        if return_date:
            legs.append(FlightQuery(date=return_date.isoformat(), from_airport=destination, to_airport=origin))

        query = create_query(
            flights=legs,
            trip="round-trip" if return_date else "one-way",
            seat=options.seat,
            passengers=Passengers(adults=options.adults),
            max_stops=options.max_stops,
            currency=options.currency,
            language=options.language,
        )

        if self.delay_seconds:
            time.sleep(self.delay_seconds * random.uniform(0.7, 1.3))

        try:
            results = get_flights(query, proxy=self.proxy)
        except FlightsNotFound:
            return []
        except Exception as exc:  # network errors, parse errors after page changes
            raise ProviderError(f"{origin}->{destination} on {depart}: {exc}") from exc

        offers = []
        for r in results:
            if not r.price:
                continue
            first, last = r.flights[0], r.flights[-1]
            offers.append(
                Offer(
                    origin=origin,
                    destination=destination,
                    depart_date=depart,
                    return_date=return_date,
                    price=float(r.price),
                    airlines=list(r.airlines),
                    stops=max(len(r.flights) - 1, 0),
                    duration_minutes=sum(f.duration for f in r.flights) or None,
                    departure_time="%02d:%02d" % first.departure.time,
                    arrival_time="%02d:%02d" % last.arrival.time,
                    booking_url=query.url(),
                )
            )
        return offers


class DemoProvider:
    """Made-up but repeatable prices, for trying the bot without network access.

    Prices depend only on route and dates, so the same search always gives the
    same answer. Weekends and dates close to today cost more.
    """

    def search(self, origin, destination, depart, return_date, options):
        seed = f"{origin}{destination}{depart}{return_date}{options.seat}"
        rng = random.Random(int(hashlib.sha256(seed.encode()).hexdigest(), 16))
        route = int(hashlib.sha256(f"{origin}{destination}".encode()).hexdigest(), 16)
        base = 80 + route % 600
        if depart.weekday() >= 4:
            base *= 1.25
        days_out = (depart - date.today()).days
        if days_out < 14:
            base *= 1.4
        if return_date:
            base *= 1.8
        offers = []
        for i in range(rng.randint(2, 5)):
            stops = rng.choice([0, 1, 1, 2])
            if options.max_stops is not None and stops > options.max_stops:
                continue
            price = round(base * rng.uniform(0.75, 1.35) * (1.15 if stops == 0 else 1.0)) * options.adults
            offers.append(
                Offer(
                    origin=origin,
                    destination=destination,
                    depart_date=depart,
                    return_date=return_date,
                    price=float(price),
                    airlines=[rng.choice(["Demo Air", "Sample Jet", "Mock Airways"])],
                    stops=stops,
                    duration_minutes=120 + 90 * stops + route % 400,
                    departure_time="%02d:%02d" % (rng.randint(5, 22), rng.choice([0, 15, 30, 45])),
                )
            )
        return offers
