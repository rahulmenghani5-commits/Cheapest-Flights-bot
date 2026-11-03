"""Command line entry point: `python -m cheapflights <search> ...`."""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date

from .models import Offer, SearchOptions
from .providers import DemoProvider, GoogleFlightsProvider
from .regions import REGIONS, resolve_destinations
from .search import SearchResult, search_region, search_specific, search_window


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{value}' is not a date like 2026-12-20")


def _airport(value: str) -> str:
    if len(value) != 3 or not value.isalpha():
        raise argparse.ArgumentTypeError(f"'{value}' is not a 3-letter airport code like BOM")
    return value.upper()


def _nights(value: str) -> range:
    try:
        if "-" in value:
            lo, hi = (int(x) for x in value.split("-", 1))
        else:
            lo = hi = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{value}' should be a number of nights like 7 or a range like 5-9")
    if lo < 1 or hi < lo:
        raise argparse.ArgumentTypeError(f"'{value}' is not a valid nights range")
    return range(lo, hi + 1)


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--from", dest="origin", required=True, type=_airport, help="origin airport, e.g. BOM")
    common.add_argument("--adults", type=int, default=1)
    common.add_argument("--seat", default="economy", choices=["economy", "premium-economy", "business", "first"])
    common.add_argument("--max-stops", type=int, default=None, help="0 for non-stop only")
    common.add_argument("--currency", default="", help="e.g. USD, INR (default: Google decides)")
    common.add_argument("--top", type=int, default=10, help="how many results to print")
    common.add_argument("--csv", help="also save all results to this CSV file")
    common.add_argument("--workers", type=int, default=3, help="parallel lookups (keep small)")
    common.add_argument("--demo", action="store_true", help="use made-up prices, no network needed")

    p = argparse.ArgumentParser(
        prog="cheapflights",
        description="Find the cheapest flights on Google Flights.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    d = sub.add_parser("dates", parents=[common], help="one destination, specific dates")
    d.add_argument("--to", required=True, type=_airport)
    d.add_argument("--depart", required=True, type=_date)
    d.add_argument("--return", dest="return_date", type=_date, help="omit for one-way")

    w = sub.add_parser("window", parents=[common], help="one destination, any date inside a window")
    w.add_argument("--to", required=True, type=_airport)
    w.add_argument("--start", required=True, type=_date, help="earliest departure date")
    w.add_argument("--end", required=True, type=_date, help="latest departure date")
    w.add_argument("--nights", type=_nights, help="trip length, e.g. 7 or 5-9 (omit for one-way)")

    r = sub.add_parser("region", parents=[common], help="every destination in a region, specific dates")
    r.add_argument(
        "--to",
        required=True,
        help=f"region name ({', '.join(sorted(REGIONS))}) or airports like LHR,CDG,AMS",
    )
    r.add_argument("--depart", required=True, type=_date)
    r.add_argument("--return", dest="return_date", type=_date, help="omit for one-way")
    return p


def _fmt_duration(minutes: int | None) -> str:
    if not minutes:
        return "-"
    return f"{minutes // 60}h{minutes % 60:02d}"


def _fmt_price(price: float, currency: str) -> str:
    return f"{price:,.0f} {currency}".strip()


def print_table(offers: list[Offer], currency: str, typical: float | None, out=None) -> None:
    out = out or sys.stdout
    headers = ["#", "Route", "Depart", "Return", "Price", "vs typical", "Stops", "Duration", "Airlines"]
    rows = []
    for i, o in enumerate(offers, 1):
        vs = f"{(o.price / typical - 1) * 100:+.0f}%" if typical else "-"
        depart = o.depart_date.strftime("%a %d %b")
        if o.departure_time:
            depart += f" {o.departure_time}"
        rows.append(
            [
                str(i),
                f"{o.origin}-{o.destination}",
                depart,
                o.return_date.strftime("%a %d %b") if o.return_date else "-",
                _fmt_price(o.price, currency),
                vs,
                "non-stop" if o.stops == 0 else str(o.stops),
                _fmt_duration(o.duration_minutes),
                ", ".join(o.airlines)[:30],
            ]
        )
    widths = [max(len(h), *(len(r[i]) for r in rows)) for i, h in enumerate(headers)]
    line = "  ".join(h.ljust(w) for h, w in zip(headers, widths))
    print(line, file=out)
    print("-" * len(line), file=out)
    for r in rows:
        print("  ".join(c.ljust(w) for c, w in zip(r, widths)), file=out)


def write_csv(path: str, offers: list[Offer]) -> None:
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["origin", "destination", "depart_date", "return_date", "price", "stops",
                    "duration_minutes", "departure_time", "airlines", "booking_url"])
        for o in offers:
            w.writerow([o.origin, o.destination, o.depart_date, o.return_date or "", o.price, o.stops,
                        o.duration_minutes or "", o.departure_time or "", "|".join(o.airlines), o.booking_url or ""])


def _progress(done: int, total: int) -> None:
    if total > 1 and sys.stderr.isatty():
        print(f"\rChecking prices... {done}/{total}", end="" if done < total else "\n", file=sys.stderr, flush=True)


def report(result: SearchResult, args, out=None) -> int:
    out = out or sys.stdout
    for err in result.errors:
        print(f"warning: {err}", file=sys.stderr)
    if not result.offers:
        print("No flights found.", file=out)
        return 1 if result.errors else 0

    typical = result.typical_price() if args.command != "dates" else None
    best = result.cheapest
    print(file=out)
    print(f"Cheapest: {_fmt_price(best.price, args.currency)}  {best.origin}-{best.destination}  "
          f"{best.depart_date:%a %d %b %Y}" + (f" to {best.return_date:%a %d %b %Y}" if best.return_date else ""),
          file=out)
    if typical:
        print(f"Typical price across this search: {_fmt_price(typical, args.currency)}", file=out)
        deals = result.deals()
        if deals:
            print(f"{len(deals)} result(s) are at least 20% below typical.", file=out)
    print(file=out)
    print_table(result.offers[: args.top], args.currency, typical, out=out)
    if result.empty:
        names = sorted({lk.destination if args.command == "region" else str(lk.depart) for lk in result.empty})
        print(f"\nNo flights found for: {', '.join(names)}", file=out)
    if best.booking_url:
        print(f"\nOpen the cheapest on Google Flights:\n{best.booking_url}", file=out)
    if args.csv:
        write_csv(args.csv, result.offers)
        print(f"\nSaved {len(result.offers)} rows to {args.csv}", file=out)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    options = SearchOptions(adults=args.adults, seat=args.seat, max_stops=args.max_stops, currency=args.currency.upper())
    provider = DemoProvider() if args.demo else GoogleFlightsProvider()

    try:
        if args.command == "dates":
            result = search_specific(provider, args.origin, args.to, args.depart, args.return_date, options)
        elif args.command == "window":
            result = search_window(provider, args.origin, args.to, args.start, args.end, args.nights, options,
                                   workers=args.workers, on_progress=_progress)
        else:
            dests = resolve_destinations(args.to)
            result = search_region(provider, args.origin, dests, args.depart, args.return_date, options,
                                   workers=args.workers, on_progress=_progress)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return report(result, args)


if __name__ == "__main__":
    sys.exit(main())
