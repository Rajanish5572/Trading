"""
Local cache for historical candles, backed by SQLite (a single file, no
server to run -- ships with Python).

Why this exists: without it, every chart load, every straddle-chart pull,
and every backtest run re-fetches the same candles from
historical-api.arrow.trade. That's slow, and burns against whatever rate
limit Arrow enforces (their docs don't publish a number for this endpoint --
see README). A backtest over 30 days that you re-run five times while
tuning a strategy should hit the network once, not five times.

Storage location: backend/data/market_data.db. This grows unbounded as you
use the terminal -- it's just raw OHLCV(+OI), so even a year of 1-min data
across a few symbols is a few hundred MB at most. Not committed to git (see
.gitignore) since it's regenerable local state, not source.

Caching strategy is deliberately simple, not a general-purpose time-series
cache: for a given (exchange, token, interval) series, if the local table
already fully covers the requested [from_dt, to_dt] window AND the window
doesn't include today, serve entirely from disk. Otherwise (partial
coverage, or the window touches today's still-forming candles) refetch the
*whole* requested range from Arrow and upsert -- correctness over cleverness.
If you later find yourself re-fetching huge historical ranges repeatedly,
the fix is to split the request into a "today" tail and a "everything
before today" head at the call site, not to make this cache smarter.
"""
from __future__ import annotations

import datetime
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "market_data.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS candles (
    exchange TEXT NOT NULL,
    token INTEGER NOT NULL,
    interval TEXT NOT NULL,
    ts TEXT NOT NULL,
    open REAL, high REAL, low REAL, close REAL, volume REAL, oi REAL,
    PRIMARY KEY (exchange, token, interval, ts)
)
"""


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(_SCHEMA)
    return conn


def _upsert(conn: sqlite3.Connection, exchange: str, token: int, interval: str, rows: list[dict]) -> None:
    conn.executemany(
        """INSERT OR REPLACE INTO candles
           (exchange, token, interval, ts, open, high, low, close, volume, oi)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        [
            (exchange, token, interval, r["ts"], r.get("open"), r.get("high"), r.get("low"),
             r.get("close"), r.get("volume"), r.get("oi"))
            for r in rows
        ],
    )


def _row_to_dict(row: tuple, want_oi: bool) -> dict:
    d = {"ts": row[0], "open": row[1], "high": row[2], "low": row[3], "close": row[4], "volume": row[5]}
    if want_oi:
        d["oi"] = row[6]
    return d


def get_candles(exchange: str, token: int, interval: str, from_dt: str, to_dt: str, oi: bool = False) -> list[dict]:
    from .arrow_client import get_arrow_client  # local import avoids a circular import at module load

    conn = _connect()
    try:
        min_ts, max_ts, count = conn.execute(
            "SELECT MIN(ts), MAX(ts), COUNT(*) FROM candles WHERE exchange=? AND token=? AND interval=? AND ts>=? AND ts<=?",
            (exchange, token, interval, from_dt, to_dt),
        ).fetchone()

        touches_today = to_dt[:10] >= datetime.date.today().isoformat()
        fully_cached = count and min_ts <= from_dt and max_ts >= to_dt

        if fully_cached and not touches_today:
            rows = conn.execute(
                "SELECT ts, open, high, low, close, volume, oi FROM candles "
                "WHERE exchange=? AND token=? AND interval=? AND ts>=? AND ts<=? ORDER BY ts",
                (exchange, token, interval, from_dt, to_dt),
            ).fetchall()
            return [_row_to_dict(r, oi) for r in rows]

        fresh = get_arrow_client().get_candles(exchange, token, interval, from_dt, to_dt, oi)
        _upsert(conn, exchange, token, interval, fresh)
        conn.commit()
        return fresh
    finally:
        conn.close()


def cache_stats() -> dict:
    conn = _connect()
    try:
        total, series = conn.execute("SELECT COUNT(*), COUNT(DISTINCT exchange || token || interval) FROM candles").fetchone()
        return {"total_rows": total, "distinct_series": series, "db_path": str(DB_PATH)}
    finally:
        conn.close()
