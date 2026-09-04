from __future__ import annotations

import pandas as pd


def cpr(daily_df: pd.DataFrame) -> dict[str, list]:
    """
    Central Pivot Range, computed per session from the PRIOR day's H/L/C so
    each row is "today's CPR band" (this is how traders plot it -- the band
    is flat across the whole session, known before the open).

    daily_df: one row per trading day, columns high/low/close, ascending.
    Returns pivot/bc/tc plus the standard R1-R3 / S1-S3 levels.
    """
    prev_high = daily_df["high"].shift(1)
    prev_low = daily_df["low"].shift(1)
    prev_close = daily_df["close"].shift(1)

    pivot = (prev_high + prev_low + prev_close) / 3
    bc = (prev_high + prev_low) / 2
    tc = (pivot - bc) + pivot

    r1 = 2 * pivot - prev_low
    s1 = 2 * pivot - prev_high
    r2 = pivot + (prev_high - prev_low)
    s2 = pivot - (prev_high - prev_low)
    r3 = prev_high + 2 * (pivot - prev_low)
    s3 = prev_low - 2 * (prev_high - pivot)

    def clean(s: pd.Series) -> list:
        return s.round(2).where(s.notna(), None).tolist()

    return {
        "pivot": clean(pivot),
        "bc": clean(bc),
        "tc": clean(tc),
        "r1": clean(r1),
        "r2": clean(r2),
        "r3": clean(r3),
        "s1": clean(s1),
        "s2": clean(s2),
        "s3": clean(s3),
        "width_pct": clean(((tc - bc).abs() / pivot) * 100),  # narrow CPR -> trend day signal
    }
