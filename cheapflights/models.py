"""Plain data types shared by every part of the bot."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class SearchOptions:
    """Filters applied to every flight lookup."""

    adults: int = 1
    seat: str = "economy"  # economy | premium-economy | business | first
    max_stops: int | None = None
    currency: str = ""  # blank lets Google pick based on location
    language: str = "en"


@dataclass
class Offer:
    """One priced itinerary returned by a provider."""

    origin: str
    destination: str
    depart_date: date
    return_date: date | None
    price: float
    airlines: list[str] = field(default_factory=list)
    stops: int = 0
    duration_minutes: int | None = None
    departure_time: str | None = None
    arrival_time: str | None = None
    booking_url: str | None = None

    @property
    def trip(self) -> str:
        return "round-trip" if self.return_date else "one-way"
