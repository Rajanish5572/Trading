from __future__ import annotations

import numpy as np
import pandas as pd


def _atr(df: pd.DataFrame, period: int) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> dict[str, list]:
    """
    Classic Supertrend. Returns the line values plus a per-candle direction
    (1 = bullish/support below price, -1 = bearish/resistance above price)
    so the frontend can color segments green/red without recomputing.
    """
    high, low, close = df["high"], df["low"], df["close"]
    atr = _atr(df, period)

    hl2 = (high + low) / 2
    upper_basic = hl2 + multiplier * atr
    lower_basic = hl2 - multiplier * atr

    upper = upper_basic.copy()
    lower = lower_basic.copy()
    direction = pd.Series(1, index=df.index)
    st = pd.Series(np.nan, index=df.index)

    for i in range(len(df)):
        if i == 0:
            st.iloc[i] = lower_basic.iloc[i]
            direction.iloc[i] = 1
            continue

        upper.iloc[i] = (
            upper_basic.iloc[i]
            if (upper_basic.iloc[i] < upper.iloc[i - 1] or close.iloc[i - 1] > upper.iloc[i - 1])
            else upper.iloc[i - 1]
        )
        lower.iloc[i] = (
            lower_basic.iloc[i]
            if (lower_basic.iloc[i] > lower.iloc[i - 1] or close.iloc[i - 1] < lower.iloc[i - 1])
            else lower.iloc[i - 1]
        )

        if direction.iloc[i - 1] == 1:
            direction.iloc[i] = -1 if close.iloc[i] < lower.iloc[i] else 1
        else:
            direction.iloc[i] = 1 if close.iloc[i] > upper.iloc[i] else -1

        st.iloc[i] = lower.iloc[i] if direction.iloc[i] == 1 else upper.iloc[i]

    return {
        "value": st.round(2).where(st.notna(), None).tolist(),
        "direction": direction.tolist(),
    }
