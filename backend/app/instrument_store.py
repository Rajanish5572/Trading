"""
Local cache + search over Arrow's instrument master, so the UI can resolve
"NIFTY" or "RELIANCE" to the (exchange, token) pair every other endpoint
actually needs, instead of you looking up and typing in raw token numbers.

Arrow's `get_instruments()` returns the full CSV instrument master as a
list of rows and refreshes once daily after 8:00 AM IST -- so we download
it once, cache it in SQLite, and only re-download when the cache is empty
or older than a day (or when you hit /api/instruments/refresh). Field
names in the raw payload aren't nailed down in Arrow's docs (it's
described as "the CSV master" without a published schema), so `_get()`
below tries a handful of likely key spellings per field rather than
assuming one -- if none match on your account, `download()` will raise a
clear error telling you to inspect a sample row and add the right key.
"""
from __future__ import annotations

import logging
import sqlite3
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("terminal.instrument_store")

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "instruments.db"
_REFRESH_INTERVAL_SECONDS = 24 * 3600

_SCHEMA = """
CREATE TABLE IF NOT EXISTS instruments (
    token INTEGER NOT NULL,
    exchange TEXT NOT NULL,
    symbol TEXT NOT NULL,
    name TEXT,
    segment TEXT,
    instrument_type TEXT,
    expiry TEXT,
    strike REAL,
    lot_size INTEGER,
    tick_size REAL,
    PRIMARY KEY (exchange, token)
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(_SCHEMA)
    return conn


def _get(row: dict, *keys: str):
    for k in keys:
        if k in row and row[k] not in (None, ""):
            return row[k]
    return None


def _normalize(row: dict) -> Optional[dict]:
    token = _get(row, "token", "instrument_token", "instrumentToken", "symid")
    symbol = _get(row, "symbol", "tradingsymbol", "tradingSymbol")
    exchange = _get(row, "exchange", "exch")
    if token is None or symbol is None or exchange is None:
        return None
    return {
        "token": int(token),
        "exchange": str(exchange),
        "symbol": str(symbol),
        "name": _get(row, "name", "companyName", "company_name") or "",
        "segment": _get(row, "segment") or "",
        "instrument_type": _get(row, "instrument_type", "instrumentType", "optionType") or "",
        "expiry": _get(row, "expiry", "expiryDate") or "",
        "strike": _get(row, "strike", "strikePrice") or 0,
        "lot_size": _get(row, "lot_size", "lotSize") or 1,
        "tick_size": _get(row, "tick_size", "tickSize") or 0.05,
    }


def download(force: bool = False) -> int:
    """Fetch the instrument master from Arrow and (re)populate the cache. Returns row count."""
    from .arrow_client import get_arrow_client

    conn = _connect()
    try:
        last = conn.execute("SELECT value FROM meta WHERE key='last_download'").fetchone()
        if not force and last and time.time() - float(last[0]) < _REFRESH_INTERVAL_SECONDS:
            count = conn.execute("SELECT COUNT(*) FROM instruments").fetchone()[0]
            if count > 0:
                return count  # already fresh enough, don't hammer the broker

        raw_rows = get_arrow_client().client().get_instruments()
        normalized = [n for n in (_normalize(r) for r in raw_rows) if n]
        if not normalized and raw_rows:
            sample = raw_rows[0]
            raise RuntimeError(
                f"get_instruments() returned {len(raw_rows)} rows but none had recognizable "
                f"token/symbol/exchange fields. Sample row keys: {list(sample.keys())} -- "
                f"add the real key names to _normalize() in instrument_store.py."
            )

        conn.execute("DELETE FROM instruments")
        conn.executemany(
            """INSERT OR REPLACE INTO instruments
               (token, exchange, symbol, name, segment, instrument_type, expiry, strike, lot_size, tick_size)
               VALUES (:token,:exchange,:symbol,:name,:segment,:instrument_type,:expiry,:strike,:lot_size,:tick_size)""",
            normalized,
        )
        conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('last_download', ?)", (str(time.time()),))
        conn.commit()
        logger.info("Cached %d instruments", len(normalized))
        return len(normalized)
    finally:
        conn.close()


def search(query: str, exchange: Optional[str] = None, limit: int = 25) -> list[dict]:
    conn = _connect()
    try:
        count = conn.execute("SELECT COUNT(*) FROM instruments").fetchone()[0]
        if count == 0:
            download()  # first-ever search triggers the initial download

        sql = "SELECT token, exchange, symbol, name, segment, instrument_type, expiry, strike, lot_size, tick_size " \
              "FROM instruments WHERE (symbol LIKE ? OR name LIKE ?)"
        params: list = [f"%{query.upper()}%", f"%{query.upper()}%"]
        if exchange:
            sql += " AND exchange = ?"
            params.append(exchange)
        sql += " ORDER BY LENGTH(symbol) ASC LIMIT ?"
        params.append(limit)

        cols = ["token", "exchange", "symbol", "name", "segment", "instrument_type", "expiry", "strike", "lot_size", "tick_size"]
        rows = conn.execute(sql, params).fetchall()
        return [dict(zip(cols, r)) for r in rows]
    finally:
        conn.close()


def resolve(symbol: str, exchange: str) -> Optional[dict]:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT token, exchange, symbol, name, segment, instrument_type, expiry, strike, lot_size, tick_size "
            "FROM instruments WHERE symbol = ? AND exchange = ?",
            (symbol, exchange),
        ).fetchone()
        if not row:
            return None
        cols = ["token", "exchange", "symbol", "name", "segment", "instrument_type", "expiry", "strike", "lot_size", "tick_size"]
        return dict(zip(cols, row))
    finally:
        conn.close()
