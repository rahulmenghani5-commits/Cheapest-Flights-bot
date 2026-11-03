"""Named groups of airports for "anywhere in this region" searches.

Each list holds the main international airports, which is where cheap fares
usually show up. Add your own regions here, or pass airports directly with
`--to LHR,CDG,AMS`.
"""

REGIONS: dict[str, list[str]] = {
    "western-europe": ["LHR", "CDG", "AMS", "FRA", "MAD", "BCN", "FCO", "MXP", "MUC", "DUB", "LIS", "BRU", "ZRH", "VIE"],
    "eastern-europe": ["WAW", "KRK", "PRG", "BUD", "OTP", "SOF", "BEG", "ZAG", "VNO", "RIX", "TLL"],
    "scandinavia": ["CPH", "ARN", "OSL", "HEL", "BGO", "GOT", "KEF"],
    "mediterranean": ["ATH", "IST", "NAP", "PMI", "AGP", "NCE", "SPU", "DBV", "MLA", "LCA", "HER", "TFS"],
    "middle-east": ["DXB", "AUH", "DOH", "AMM", "TLV", "MCT", "BAH", "RUH", "JED", "KWI"],
    "south-asia": ["DEL", "BOM", "BLR", "MAA", "HYD", "CCU", "COK", "GOI", "CMB", "KTM", "DAC", "MLE"],
    "southeast-asia": ["BKK", "SIN", "KUL", "SGN", "HAN", "MNL", "CGK", "DPS", "HKT", "PNH", "REP", "CEB"],
    "east-asia": ["NRT", "HND", "KIX", "ICN", "PVG", "PEK", "HKG", "TPE", "FUK", "CTS"],
    "oceania": ["SYD", "MEL", "BNE", "PER", "AKL", "CHC", "NAN", "ADL"],
    "north-america": ["JFK", "LAX", "SFO", "ORD", "MIA", "SEA", "BOS", "IAD", "ATL", "DFW", "YYZ", "YVR", "YUL"],
    "caribbean": ["CUN", "SJU", "PUJ", "MBJ", "NAS", "AUA", "BGI", "SXM", "HAV", "PTY"],
    "latin-america": ["MEX", "BOG", "LIM", "GRU", "EZE", "SCL", "MDE", "UIO", "SJO", "GIG", "CTG"],
    "africa": ["JNB", "CPT", "NBO", "CAI", "CMN", "RAK", "ADD", "ACC", "LOS", "DAR", "ZNZ", "MRU"],
}


def resolve_destinations(value: str) -> list[str]:
    """Turn a region name or a comma-separated airport list into airport codes."""
    key = value.strip().lower()
    if key in REGIONS:
        return list(REGIONS[key])
    codes = [c.strip().upper() for c in value.split(",") if c.strip()]
    bad = [c for c in codes if len(c) != 3 or not c.isalpha()]
    if bad or not codes:
        known = ", ".join(sorted(REGIONS))
        raise ValueError(
            f"'{value}' is not a known region or a list of 3-letter airport codes. Known regions: {known}"
        )
    return codes
