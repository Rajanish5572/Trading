"""
Analytics tab: OI change / buildup classification per near strike, the ATM
straddle price chart, and IV percentile. All filterable by underlying +
expiry via query params, matching the option chain tab's filters.

Buildup classification (the standard four-quadrant read every F&O desk
uses):
  price up   + OI up   -> Long buildup      (fresh longs being added)
  price down + OI up   -> Short buildup     (fresh shorts being added)
  price up   + OI down -> Short covering    (shorts exiting)
  price down + OI down -> Long unwinding    (longs exiting)
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from .. import history_store
from ..arrow_client import get_arrow_client
from ..iv_store import record_and_get_percentile

logger = logging.getLogger("terminal.analytics")
router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def _classify(price_change_pct: float, oi_change: float) -> str:
    if price_change_pct > 0 and oi_change > 0:
        return "Long buildup"
    if price_change_pct < 0 and oi_change > 0:
        return "Short buildup"
    if price_change_pct > 0 and oi_change < 0:
        return "Short covering"
    if price_change_pct < 0 and oi_change < 0:
        return "Long unwinding"
    return "Neutral"


_INTERPRETATION = {
    "Long buildup": "Fresh longs being added -- bullish, trend likely to continue.",
    "Short buildup": "Fresh shorts being added -- bearish, trend likely to continue.",
    "Short covering": "Shorts exiting into strength -- can fuel a sharp bounce, often short-lived.",
    "Long unwinding": "Longs exiting into weakness -- can fuel a sharp drop, often short-lived.",
    "Neutral": "No clear directional OI signal at this strike.",
}


@router.get("/oi-buildup")
def oi_buildup(
    underlying: str = Query(...),
    exchange: str = Query("NFO"),
    expiry: str = Query(...),
    count: int = Query(10, description="Strikes on each side of ATM to analyze"),
):
    client = get_arrow_client()
    try:
        legs = client.get_option_chain(underlying, exchange, expiry, count)
    except Exception as exc:
        raise HTTPException(502, f"Could not fetch option chain: {exc}") from exc

    rows = []
    for leg in legs:
        try:
            quote = client.get_quote("OHLCV", leg["symbol"], exchange)
        except Exception:
            logger.warning("Quote failed for %s, skipping", leg.get("symbol"))
            continue

        ltp = quote.get("ltp") or quote.get("close") or 0
        prev_close = quote.get("close") or ltp
        current_oi = quote.get("oi") or 0
        opening_oi = leg.get("openingOI") or 0

        price_change_pct = round(((ltp - prev_close) / prev_close) * 100, 2) if prev_close else 0.0
        oi_change = current_oi - opening_oi
        oi_change_pct = round((oi_change / opening_oi) * 100, 2) if opening_oi else 0.0
        buildup = _classify(price_change_pct, oi_change)

        rows.append({
            "symbol": leg["symbol"],
            "strike": leg.get("strikePrice"),
            "option_type": leg.get("optionType"),
            "ltp": ltp,
            "price_change_pct": price_change_pct,
            "current_oi": current_oi,
            "opening_oi": opening_oi,
            "oi_change": oi_change,
            "oi_change_pct": oi_change_pct,
            "buildup": buildup,
            "interpretation": _INTERPRETATION[buildup],
        })

    rows.sort(key=lambda r: abs(r["oi_change"]), reverse=True)
    return {"underlying": underlying, "expiry": expiry, "strikes": rows, "most_active": rows[:5]}


@router.get("/straddle")
def straddle_chart(
    underlying: str = Query(...),
    exchange: str = Query("NFO"),
    expiry: str = Query(...),
    strike: float = Query(..., description="Strike to build the CE+PE straddle for -- pass the ATM strike"),
    interval: str = Query("5min"),
    from_dt: str = Query(...),
    to_dt: str = Query(...),
):
    client = get_arrow_client()
    try:
        legs = client.get_option_chain(underlying, exchange, expiry, count=50)
    except Exception as exc:
        raise HTTPException(502, f"Could not fetch option chain: {exc}") from exc

    ce = next((l for l in legs if l.get("strikePrice") == strike and l.get("optionType") == "CE"), None)
    pe = next((l for l in legs if l.get("strikePrice") == strike and l.get("optionType") == "PE"), None)
    if not ce or not pe:
        raise HTTPException(404, f"Strike {strike} not found in chain for {underlying} {expiry}")

    try:
        ce_candles = history_store.get_candles(exchange, ce["token"], interval, from_dt, to_dt)
        pe_candles = history_store.get_candles(exchange, pe["token"], interval, from_dt, to_dt)
    except Exception as exc:
        raise HTTPException(502, f"Could not fetch option candles: {exc}") from exc

    pe_by_ts = {c["ts"]: c["close"] for c in pe_candles}
    combined = [
        {"ts": c["ts"], "ce": c["close"], "pe": pe_by_ts.get(c["ts"]), "straddle": c["close"] + pe_by_ts.get(c["ts"], 0)}
        for c in ce_candles
        if c["ts"] in pe_by_ts
    ]
    return {"underlying": underlying, "strike": strike, "expiry": expiry, "series": combined}


@router.get("/iv-percentile")
def iv_percentile(
    underlying: str = Query(...),
    exchange: str = Query("NFO"),
    expiry: str = Query(...),
):
    client = get_arrow_client()
    try:
        legs = client.get_option_chain(underlying, exchange, expiry, count=4)
        tokens = [l["token"] for l in legs]
        greeks = client.client().get_greeks(tokens)  # documented as possibly unavailable on some envs
    except Exception as exc:
        raise HTTPException(
            502,
            "Could not fetch greeks/IV from broker. Arrow's docs flag get_greeks as "
            f"potentially disabled on some environments -- verify with Arrow support. ({exc})",
        ) from exc

    ivs = [g["iv"] for g in greeks if g.get("iv")]
    if not ivs:
        raise HTTPException(502, "Broker returned no usable IV values")
    atm_iv = sum(ivs) / len(ivs)

    result = record_and_get_percentile(underlying, round(atm_iv, 2))
    if not result["reliable"]:
        result["note"] = (
            "Fewer than ~60 daily samples collected so far -- this percentile isn't statistically "
            "meaningful yet. It improves automatically the longer the terminal runs, or you can "
            "backfill iv_store.backfill() from an external historical-IV source."
        )
    return result
