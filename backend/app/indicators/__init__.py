"""
Indicator library. Every function takes a pandas DataFrame of OHLCV candles
with columns: ts, open, high, low, close, volume (ts = ISO string or
datetime, ascending order, one row per candle) and returns either a
pandas Series aligned to the same index, or a small dict of summary values.

Kept as plain pandas/numpy functions (no classes) so they're trivial to
unit test and to call from routers/chart.py and routers/strategy.py
(backtesting reuses the exact same functions the live chart uses).
"""
from .moving_average import sma, ema, moving_averages
from .supertrend import supertrend
from .cpr import cpr
from .rsi import rsi
from .macd import macd
from .volume_profile import volume_profile

__all__ = [
    "sma",
    "ema",
    "moving_averages",
    "supertrend",
    "cpr",
    "rsi",
    "macd",
    "volume_profile",
]
