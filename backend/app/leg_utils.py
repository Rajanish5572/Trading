"""
Shared helper for option-chain legs, used by both option_chain.py and
analytics.py.

Confirmed against a real Arrow response (2026-09, MIDCPNIFTY chain):
every field comes back as a string, even numeric ones --
`"strikePrice": "14650.00"`, `"token": "72950"`, `"openingOI": "15960"`.
Without this normalization, code that does arithmetic or sorting on these
(ATM distance, OI sums, PCR) either crashes or silently gives wrong answers
(string-sorting "9000" above "14650").
"""
from __future__ import annotations


def normalize_leg(leg: dict) -> dict:
    for key, caster in (("strikePrice", float), ("openingOI", int), ("lotSize", int),
                        ("tickSize", float), ("token", int), ("pricePrecision", int)):
        if key in leg and leg[key] not in (None, ""):
            try:
                leg[key] = caster(leg[key])
            except (TypeError, ValueError):
                pass  # leave as-is rather than crash the whole request over one odd value
    return leg


def normalize_legs(legs: list[dict]) -> list[dict]:
    return [normalize_leg(leg) for leg in legs]
