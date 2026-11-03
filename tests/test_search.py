from datetime import date, timedelta

import pytest

from cheapflights import cli
from cheapflights.models import Offer, SearchOptions
from cheapflights.providers import DemoProvider, GoogleFlightsProvider, ProviderError
from cheapflights.regions import REGIONS, resolve_destinations
from cheapflights.search import MAX_LOOKUPS, search_region, search_specific, search_window

SOON = date.today() + timedelta(days=30)
OPTS = SearchOptions()


class TableProvider:
    """Returns prices from a dict keyed by (destination, depart, return)."""

    def __init__(self, prices, fail=()):
        self.prices = prices
        self.fail = set(fail)
        self.calls = []

    def search(self, origin, destination, depart, return_date, options):
        self.calls.append((destination, depart, return_date))
        if destination in self.fail:
            raise ProviderError(f"blocked {destination}")
        price = self.prices.get((destination, depart, return_date))
        if price is None:
            return []
        return [
            Offer(origin, destination, depart, return_date, price + 50),
            Offer(origin, destination, depart, return_date, price),
        ]


def test_specific_dates_returns_all_offers_cheapest_first():
    p = TableProvider({("LHR", SOON, None): 400})
    result = search_specific(p, "bom", "lhr", SOON, None, OPTS)
    assert [o.price for o in result.offers] == [400, 450]
    assert result.cheapest.destination == "LHR"


def test_specific_dates_rejects_past_and_backwards_dates():
    with pytest.raises(ValueError):
        search_specific(DemoProvider(), "BOM", "LHR", date.today() - timedelta(days=1), None, OPTS)
    with pytest.raises(ValueError):
        search_specific(DemoProvider(), "BOM", "LHR", SOON, SOON - timedelta(days=1), OPTS)


def test_window_one_way_picks_cheapest_day():
    days = [SOON + timedelta(days=i) for i in range(5)]
    prices = {("LHR", d, None): 500 for d in days}
    prices[("LHR", days[3], None)] = 300
    p = TableProvider(prices)
    result = search_window(p, "BOM", "LHR", days[0], days[-1], None, OPTS)
    assert len(p.calls) == 5
    assert result.cheapest.depart_date == days[3]
    assert result.cheapest.price == 300
    assert len(result.offers) == 5  # one per day


def test_window_round_trip_tries_every_trip_length():
    p = TableProvider({})
    search_window(p, "BOM", "LHR", SOON, SOON + timedelta(days=2), range(5, 8), OPTS)
    assert len(p.calls) == 9
    assert (("LHR", SOON, SOON + timedelta(days=7))) in p.calls


def test_window_too_big_is_refused():
    with pytest.raises(ValueError, match="lookups"):
        search_window(DemoProvider(), "BOM", "LHR", SOON, SOON + timedelta(days=60), range(3, 10), OPTS)
    assert MAX_LOOKUPS < 61 * 7


def test_region_ranks_destinations_and_keeps_going_after_errors():
    p = TableProvider({("BKK", SOON, None): 200, ("SIN", SOON, None): 150}, fail={"KUL"})
    result = search_region(p, "BOM", ["BKK", "SIN", "KUL", "HAN", "BOM"], SOON, None, OPTS)
    assert [o.destination for o in result.offers] == ["SIN", "BKK"]
    assert result.errors == ["blocked KUL"]
    assert [lk.destination for lk in result.empty] == ["HAN"]
    assert ("BOM", SOON, None) not in p.calls  # never searches origin -> origin


def test_deals_are_well_below_typical():
    days = [SOON + timedelta(days=i) for i in range(5)]
    prices = {("LHR", d, None): 500 for d in days}
    prices[("LHR", days[0], None)] = 350
    result = search_window(TableProvider(prices), "BOM", "LHR", days[0], days[-1], None, OPTS)
    assert [o.price for o in result.deals()] == [350]


def test_resolve_destinations():
    assert resolve_destinations("Southeast-Asia") == REGIONS["southeast-asia"]
    assert resolve_destinations("lhr, cdg") == ["LHR", "CDG"]
    with pytest.raises(ValueError):
        resolve_destinations("mars")


def test_google_provider_maps_fast_flights_results(monkeypatch):
    fast_flights = pytest.importorskip("fast_flights")
    from fast_flights.model import Airport, CarbonEmission, Flights, SimpleDatetime, SingleFlight

    def leg(a, b, dep, arr, mins):
        return SingleFlight(Airport(a, a), Airport(b, b), SimpleDatetime((2026, 1, 1), dep),
                            SimpleDatetime((2026, 1, 1), arr), mins, "A320")

    fake = [Flights("multi", 612, ["IndiGo"], [leg("BOM", "DXB", (6, 5), (7, 40), 215),
                                               leg("DXB", "LHR", (9, 0), (13, 5), 485)], CarbonEmission(1, 1))]
    seen = {}

    def fake_get_flights(query, proxy=None):
        seen["url"] = query.url()
        return fake

    monkeypatch.setattr(fast_flights, "get_flights", fake_get_flights)
    offers = GoogleFlightsProvider(delay_seconds=0).search("BOM", "LHR", SOON, None, OPTS)
    assert len(offers) == 1
    o = offers[0]
    assert (o.price, o.stops, o.duration_minutes, o.departure_time, o.arrival_time) == (612, 1, 700, "06:05", "13:05")
    assert o.booking_url == seen["url"]


def test_cli_demo_runs_all_three_searches(capsys, tmp_path):
    d = SOON.isoformat()
    end = (SOON + timedelta(days=6)).isoformat()
    assert cli.main(["dates", "--from", "BOM", "--to", "LHR", "--depart", d, "--demo"]) == 0
    assert cli.main(["window", "--from", "BOM", "--to", "LHR", "--start", d, "--end", end, "--nights", "5-6",
                     "--demo", "--csv", str(tmp_path / "w.csv")]) == 0
    assert cli.main(["region", "--from", "BOM", "--to", "east-asia", "--depart", d, "--demo"]) == 0
    out = capsys.readouterr().out
    assert out.count("Cheapest:") == 3
    assert (tmp_path / "w.csv").read_text().count("\n") == 15  # header + 7 days x 2 lengths
