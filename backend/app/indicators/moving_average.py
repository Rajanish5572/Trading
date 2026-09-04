from __future__ import annotations

import pandas as pd


def sma(close: pd.Series, period: int) -> pd.Series:
    return close.rolling(window=period, min_periods=period).mean()


def ema(close: pd.Series, period: int) -> pd.Series:
    return close.ewm(span=period, adjust=False, min_periods=period).mean()


def moving_averages(df: pd.DataFrame, configs: list[dict]) -> dict[str, list]:
    """
    configs: [{"type": "SMA"|"EMA", "period": 9}, ...] -- as many as the user
    adds from the chart toolbar. Returns {"SMA_9": [...], "EMA_21": [...]}.
    """
    out: dict[str, list] = {}
    for cfg in configs:
        period = int(cfg["period"])
        kind = cfg.get("type", "SMA").upper()
        series = ema(df["close"], period) if kind == "EMA" else sma(df["close"], period)
        out[f"{kind}_{period}"] = series.round(2).where(series.notna(), None).tolist()
    return out
