from __future__ import annotations

import numpy as np
import pandas as pd


def volume_profile(df: pd.DataFrame, bins: int = 24, value_area_pct: float = 0.70) -> dict:
    """
    Volume-by-price histogram over the given candle window (caller decides
    the window -- session, last N candles, visible chart range, etc).
    Each candle's volume is split evenly across bins its high-low range
    touches, which is the standard approximation when tick-level data isn't
    available.

    Returns bin edges/volumes, the point of control (POC = highest-volume
    price bin), and the value area (the tightest band of bins containing
    value_area_pct of total volume, expanded outward from the POC).
    """
    lo, hi = df["low"].min(), df["high"].max()
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        return {"bins": [], "volumes": [], "poc": None, "value_area_low": None, "value_area_high": None}

    edges = np.linspace(lo, hi, bins + 1)
    volumes = np.zeros(bins)

    for _, row in df.iterrows():
        row_lo, row_hi, vol = row["low"], row["high"], row.get("volume", 0) or 0
        if vol == 0 or row_hi <= row_lo:
            continue
        touched = np.where((edges[:-1] < row_hi) & (edges[1:] > row_lo))[0]
        if len(touched):
            volumes[touched] += vol / len(touched)

    poc_idx = int(np.argmax(volumes)) if volumes.sum() > 0 else bins // 2
    total = volumes.sum()

    # expand outward from POC until value_area_pct of volume is covered
    included = {poc_idx}
    low_i, high_i = poc_idx, poc_idx
    covered = volumes[poc_idx]
    while total > 0 and covered / total < value_area_pct and (low_i > 0 or high_i < bins - 1):
        below = volumes[low_i - 1] if low_i > 0 else -1
        above = volumes[high_i + 1] if high_i < bins - 1 else -1
        if above >= below:
            high_i += 1
            covered += volumes[high_i]
        else:
            low_i -= 1
            covered += volumes[low_i]

    centers = ((edges[:-1] + edges[1:]) / 2).round(2)
    return {
        "bins": centers.tolist(),
        "volumes": volumes.round(0).tolist(),
        "poc": float(centers[poc_idx]),
        "value_area_low": float(centers[low_i]),
        "value_area_high": float(centers[high_i]),
    }
