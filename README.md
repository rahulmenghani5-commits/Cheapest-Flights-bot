# Cheapest flights bot

Finds the cheapest flights on Google Flights from the command line. It needs no API key.

It does three searches:

| Search   | What it answers |
|----------|-----------------|
| `dates`  | What's the cheapest way to fly from A to B on these exact dates? |
| `window` | Which day in this window is cheapest to fly from A to B? Optionally for a trip of N nights. |
| `region` | Which destination in this region is cheapest to fly to on this date? |

## Setup

You need Python 3.10 or newer.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Usage

Use 3-letter airport codes and dates written as `YYYY-MM-DD`. Leave out `--return` or `--nights` to search one-way.

```bash
# 1. Specific dates: Mumbai to London, 20 Dec, back 3 Jan
python -m cheapflights dates --from BOM --to LHR --depart 2026-12-20 --return 2027-01-03

# 2. Flexible dates: any departure in December, staying 6 to 8 nights
python -m cheapflights window --from BOM --to LHR --start 2026-12-01 --end 2026-12-31 --nights 6-8

# 3. Region: anywhere in Southeast Asia on 20 Dec, one-way
python -m cheapflights region --from BOM --to southeast-asia --depart 2026-12-20

# Your own list of airports works too
python -m cheapflights region --from BOM --to DXB,DOH,AUH --depart 2026-12-20
```

Each search prints the cheapest result, then a ranked table. For `window` and `region`, the table also shows how each price compares with the typical (median) price, and it calls out results at least 20% below typical. A Google Flights link to the cheapest option is printed at the end.

Options that work with every search:

| Option | Meaning |
|--------|---------|
| `--adults 2` | number of passengers |
| `--seat business` | `economy`, `premium-economy`, `business` or `first` |
| `--max-stops 0` | non-stop only (use `1` for at most one stop) |
| `--currency INR` | currency for prices (by default Google picks one from your location) |
| `--top 20` | how many rows to print |
| `--csv out.csv` | also save every result to a CSV file |
| `--demo` | use made-up prices, to try the bot without going online |

The built-in regions are `western-europe`, `eastern-europe`, `scandinavia`, `mediterranean`, `middle-east`, `south-asia`, `southeast-asia`, `east-asia`, `oceania`, `north-america`, `caribbean`, `latin-america` and `africa`. To change them, edit `cheapflights/regions.py`.

## Limits

- Prices come from Google Flights through the unofficial [fast-flights](https://github.com/AWeirdDev/fast-flights) library. If Google changes its page or rate-limits you, searches will print warnings until fast-flights is updated.
- Every date, trip length and destination costs one lookup, with about a second between lookups. A month-long window with `--nights 6-8` takes around 93 lookups. Searches over 120 lookups are refused, so narrow the window or the nights range if you hit that limit.
- To use a different price source, such as a paid API, add a class with a `search()` method to `cheapflights/providers.py`.

## Tests

```bash
pip install pytest
python -m pytest
```

## History

This repo began as a fork of [PhoenixDD/Cheapest-Flights-bot](https://github.com/PhoenixDD/Cheapest-Flights-bot), a 2017 Selenium scraper of the old Google Flights Explore page. That page no longer exists. The original script is kept in `legacy/flight_analysis_2017.py` for reference.
