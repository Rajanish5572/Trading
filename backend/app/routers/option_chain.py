"""
Option chain tab: strikes for a chosen underlying + expiry, with ATM
highlighting and a PCR summary. Arrow's get_option_chain gives us per-strike
legs natively -- we don't rebuild it from the instrument master.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from ..arrow_client import get_arrow_client
from ..leg_utils import normalize_legs

logger = logging.getLogger("terminal.option_chain")
router = APIRouter(prefix="/api/option-chain", tags=["option-chain"])


@router.get("/symbols")
def list_underlyings():
    """Underlying -> valid expiry list, for the index/expiry filter dropdowns."""
    try:
        return get_arrow_client().get_option_chain_symbols()
    except Exception as exc:
        logger.exception("Failed to fetch option chain symbol map")
        raise HTTPException(502, str(exc)) from exc


@router.get("/indices")
def list_indices():
    try:
        return get_arrow_client().get_index_list()
    except Exception as exc:
        raise HTTPException(502, str(exc)) from exc


@router.get("")
def get_chain(
    underlying: str = Query(...),
    exchange: str = Query("INDEX", description="Confirmed 'INDEX' works for major indices (NIFTY etc). "
                                                 "Equity-underlying option chains haven't been verified yet -- "
                                                 "may need 'NFO' instead, untested."),
    expiry: str = Query(...),
    count: int = Query(20, description="Strikes on each side of ATM"),
    spot: float | None = Query(None, description="Current spot, for ATM + PCR calc; fetched live if omitted"),
):
    try:
        legs = get_arrow_client().get_option_chain(underlying, exchange, expiry, count)
    except Exception as exc:
        logger.exception("Option chain fetch failed")
        raise HTTPException(502, f"Could not fetch option chain: {exc}") from exc

    legs = normalize_legs(legs)

    if spot is None:
        try:
            # Best-effort guess: index spot quotes are commonly served under
            # NSE even when the option chain itself lives under "INDEX" --
            # not independently confirmed the way the option chain call was.
            quote_exchange = "NSE" if exchange in ("INDEX", "NFO") else "BSE"
            quote = get_arrow_client().get_quote("LTP", underlying, quote_exchange)
            spot = quote.get("ltp")
        except Exception:
            logger.warning("Could not resolve live spot for ATM calc, falling back to nearest strike")
            spot = None

    strikes = sorted({leg["strikePrice"] for leg in legs})
    atm_strike = min(strikes, key=lambda s: abs(s - spot)) if spot and strikes else None

    total_ce_oi = sum(leg.get("openingOI", 0) or 0 for leg in legs if leg.get("optionType") == "CE")
    total_pe_oi = sum(leg.get("openingOI", 0) or 0 for leg in legs if leg.get("optionType") == "PE")
    pcr = round(total_pe_oi / total_ce_oi, 3) if total_ce_oi else None

    for leg in legs:
        leg["is_atm"] = leg.get("strikePrice") == atm_strike

    return {
        "underlying": underlying,
        "expiry": expiry,
        "spot": spot,
        "atm_strike": atm_strike,
        "pcr": pcr,
        "total_ce_oi": total_ce_oi,
        "total_pe_oi": total_pe_oi,
        "legs": legs,
    }
