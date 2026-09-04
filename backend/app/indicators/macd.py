from __future__ import annotations

import pandas as pd

from .moving_average import ema


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> dict[str, list]:
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    histogram = macd_line - signal_line

    def clean(s: pd.Series) -> list:
        return s.round(2).where(s.notna(), None).tolist()

    return {"macd": clean(macd_line), "signal": clean(signal_line), "histogram": clean(histogram)}
