"""
Strategy builder tab: payoff diagram, margin estimate for the whole basket,
and a simple day-by-day backtest.

Payoff math is intrinsic-value-at-expiry (the standard "payoff diagram" a
strategy builder shows -- P&L at expiry across a spot price range), not a
today/live theta-adjusted curve. That would need live greeks per leg, which
Arrow's docs flag as possibly unreliable (see routers/analytics.py) -- worth
adding once you've confirmed get_greeks works reliably on your account.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from fastapi import APIRouter, HTTPException

from .. import history_store
from ..arrow_client import get_arrow_client
from ..models import BacktestRequest, PayoffRequest, StrategyLeg

logger = logging.getLogger("terminal.strategy")
router = APIRouter(prefix="/api/strategy", tags=["strategy"])


def _leg_payoff(leg: StrategyLeg, spot: float) -> float:
    if leg.option_type == "FUT":
        intrinsic = spot
        entry = leg.premium  # for futures, "premium" is entry price
    elif leg.option_type == "CE":
        intrinsic = max(spot - leg.strike, 0)
        entry = leg.premium
    elif leg.option_type == "PE":
        intrinsic = max(leg.strike - spot, 0)
        entry = leg.premium
    else:
        raise ValueError(f"Unknown option_type {leg.option_type}")

    sign = 1 if leg.transaction_type == "BUY" else -1
    per_unit = (intrinsic - entry) if leg.option_type != "FUT" else (intrinsic - entry)
    return sign * per_unit * leg.quantity * leg.lot_size


@router.post("/payoff")
def payoff(req: PayoffRequest):
    if not req.legs:
        raise HTTPException(400, "Add at least one leg")

    lo = req.spot * (1 - req.price_range_pct)
    hi = req.spot * (1 + req.price_range_pct)
    points = 121
    step = (hi - lo) / (points - 1)

    curve = []
    for i in range(points):
        p = round(lo + i * step, 2)
        total = round(sum(_leg_payoff(leg, p) for leg in req.legs), 2)
        curve.append({"spot": p, "pnl": total})

    pnls = [pt["pnl"] for pt in curve]
    max_profit = max(pnls)
    max_loss = min(pnls)

    breakevens = []
    for a, b in zip(curve, curve[1:]):
        if a["pnl"] == 0:
            breakevens.append(a["spot"])
        elif (a["pnl"] < 0) != (b["pnl"] < 0):
            # linear interpolation for a cleaner breakeven estimate
            frac = abs(a["pnl"]) / (abs(a["pnl"]) + abs(b["pnl"]))
            breakevens.append(round(a["spot"] + frac * (b["spot"] - a["spot"]), 2))

    uncapped_upside = curve[-1]["pnl"] > curve[-2]["pnl"] > 0 and any(
        leg.transaction_type == "BUY" and leg.option_type in ("CE", "FUT") for leg in req.legs
    )
    uncapped_downside = curve[0]["pnl"] > curve[1]["pnl"] > 0 and any(
        leg.transaction_type == "SELL" for leg in req.legs
    )

    return {
        "curve": curve,
        "max_profit": max_profit,
        "max_loss": max_loss,
        "breakevens": breakevens,
        "max_profit_uncapped": uncapped_upside,
        "max_loss_uncapped": not uncapped_upside and any(l.transaction_type == "SELL" for l in req.legs),
    }


@router.post("/margin")
def margin(req: PayoffRequest):
    orders = [
        {
            "symbol": leg.symbol,
            "exchange": "NFO",
            "quantity": leg.quantity * leg.lot_size,
            "transaction_type": leg.transaction_type,
            "product": "NRML",
            "order_type": "MARKET",
        }
        for leg in req.legs
    ]
    try:
        return get_arrow_client().basket_margin(orders)
    except Exception as exc:
        raise HTTPException(502, f"Margin calculation failed: {exc}") from exc


def _trading_days(from_dt: date, to_dt: date):
    d = from_dt
    while d <= to_dt:
        if d.weekday() < 5:  # Mon-Fri; doesn't account for exchange holidays
            yield d
        d += timedelta(days=1)


@router.post("/backtest")
def backtest(req: BacktestRequest):
    """
    Simple entry-time/exit-time backtest: for each trading day in range, take
    each leg's 1-min candle at entry_time as the entry premium and at
    exit_time as the exit premium, sum P&L across legs, per day.

    Caveats worth knowing before trusting results: no slippage/brokerage
    modeled, assumes the option strike/symbol existed unchanged for the
    whole date range (fine for a single expiry, not for rolling strategies
    across expiries), and skips any day where the broker has no 1-min data
    (illiquid strikes, holidays not already filtered out).
    """
    try:
        from_d = datetime.strptime(req.from_date, "%Y-%m-%d").date()
        to_d = datetime.strptime(req.to_date, "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(400, "from_date/to_date must be YYYY-MM-DD") from exc

    daily_results = []
    for d in _trading_days(from_d, to_d):
        day_pnl = 0.0
        legs_ok = True
        for leg in req.legs:
            entry_dt = f"{d.isoformat()}T{req.entry_time}:00"
            exit_dt = f"{d.isoformat()}T{req.exit_time}:00"
            if not leg.token:
                legs_ok = False
                break
            try:
                candles = history_store.get_candles("NFO", leg.token, "min", entry_dt, exit_dt)
            except Exception:
                legs_ok = False
                break
            if len(candles) < 2:
                legs_ok = False
                break
            entry_price = candles[0]["close"]
            exit_price = candles[-1]["close"]
            sign = 1 if leg.transaction_type == "BUY" else -1
            day_pnl += sign * (exit_price - entry_price) * leg.quantity * leg.lot_size

        if legs_ok:
            daily_results.append({"date": d.isoformat(), "pnl": round(day_pnl, 2)})
        else:
            daily_results.append({"date": d.isoformat(), "pnl": None, "note": "no data for this day"})

    valid = [r["pnl"] for r in daily_results if r["pnl"] is not None]
    cumulative = 0.0
    for r in daily_results:
        if r["pnl"] is not None:
            cumulative += r["pnl"]
            r["cumulative_pnl"] = round(cumulative, 2)

    return {
        "daily_results": daily_results,
        "total_pnl": round(sum(valid), 2) if valid else 0,
        "win_days": sum(1 for v in valid if v > 0),
        "loss_days": sum(1 for v in valid if v < 0),
        "days_with_no_data": sum(1 for r in daily_results if r["pnl"] is None),
    }
