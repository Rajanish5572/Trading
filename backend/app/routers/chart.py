"""
Chart tab: historical candles + on-demand indicator calculation, and the
subscribe endpoint that tells the market-data bridge which tokens the
frontend currently cares about (so we don't subscribe to everything Arrow
offers, just what's on screen).
"""
from __future__ import annotations

import logging

import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import history_store, indicators
from ..ws_relay import bridge

logger = logging.getLogger("terminal.chart")
router = APIRouter(prefix="/api/chart", tags=["chart"])


class IndicatorConfig(BaseModel):
    id: str  # "ma", "supertrend", "cpr", "rsi", "macd", "volume_profile"
    params: dict = {}


class CandlesRequest(BaseModel):
    exchange: str
    token: int
    symbol: str
    interval: str = "5min"
    from_dt: str
    to_dt: str
    oi: bool = False
    indicators: list[IndicatorConfig] = []


def _to_df(raw_candles: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(raw_candles)
    expected = {"ts", "open", "high", "low", "close", "volume"}
    missing = expected - set(df.columns)
    if missing:
        raise HTTPException(500, f"Broker candle payload missing fields: {missing}")
    return df.sort_values("ts").reset_index(drop=True)


@router.post("/candles")
def get_candles(req: CandlesRequest):
    try:
        raw = history_store.get_candles(req.exchange, req.token, req.interval, req.from_dt, req.to_dt, req.oi)
    except Exception as exc:
        logger.exception("Historical candle fetch failed")
        raise HTTPException(502, f"Could not fetch candles from broker: {exc}") from exc

    df = _to_df(raw)
    result: dict = {
        "symbol": req.symbol,
        "candles": df.to_dict(orient="records"),
    }

    computed: dict = {}
    for ind in req.indicators:
        if ind.id == "ma":
            computed["ma"] = indicators.moving_averages(df, ind.params.get("configs", [{"type": "SMA", "period": 20}]))
        elif ind.id == "supertrend":
            computed["supertrend"] = indicators.supertrend(
                df, ind.params.get("period", 10), ind.params.get("multiplier", 3.0)
            )
        elif ind.id == "cpr":
            # CPR needs daily H/L/C; caller passes daily-resampled candles for this token separately
            # via /api/chart/cpr -- kept out of the intraday candle response to avoid double-fetching.
            continue
        elif ind.id == "rsi":
            computed["rsi"] = indicators.rsi(df["close"], ind.params.get("period", 14))
        elif ind.id == "macd":
            computed["macd"] = indicators.macd(
                df["close"], ind.params.get("fast", 12), ind.params.get("slow", 26), ind.params.get("signal", 9)
            )
        elif ind.id == "volume_profile":
            computed["volume_profile"] = indicators.volume_profile(df, ind.params.get("bins", 24))
        else:
            logger.warning("Unknown indicator requested: %s", ind.id)

    result["indicators"] = computed
    return result


@router.post("/cpr")
def get_cpr(req: CandlesRequest):
    """Separate endpoint: fetch daily candles for the same token and compute CPR bands."""
    try:
        raw = history_store.get_candles(req.exchange, req.token, "day", req.from_dt, req.to_dt)
    except Exception as exc:
        raise HTTPException(502, f"Could not fetch daily candles for CPR: {exc}") from exc
    df = _to_df(raw)
    return indicators.cpr(df)


class SubscribeRequest(BaseModel):
    mode: str = "QUOTE"  # LTP | QUOTE | FULL
    instruments: dict[int, str]  # token -> symbol


@router.post("/subscribe")
def subscribe(req: SubscribeRequest):
    bridge.subscribe(req.mode, req.instruments)
    return {"subscribed": list(req.instruments.values())}
