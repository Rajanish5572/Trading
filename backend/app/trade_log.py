"""
Local fill log, keyed by expiry, so the Positions tab can show "closed
positions for this expiry" even if you closed the trade on an earlier day.

Why this exists: Arrow's REST API gives you *current* positions and
*today's* order/trade book, not a history grouped by expiry. Neither
paper mode nor live mode gets that grouping for free, so we log every fill
ourselves (paper fills from paper_engine, live fills from the order-update
websocket in ws_relay) and derive the grouping here. This file is the
source of truth for "what happened on this expiry so far", independent of
whatever the broker's snapshot currently shows.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

_STORE_PATH = Path(__file__).resolve().parent.parent / "data" / "trade_log.json"
_EXPIRY_RE = re.compile(r"(\d{2}[A-Z]{3}\d{2})")


def parse_expiry(symbol: str) -> str | None:
    """'NIFTY16JUN26C23150' -> '16JUN26'. Returns None for plain equity symbols."""
    match = _EXPIRY_RE.search(symbol)
    return match.group(1) if match else None


def _load() -> list[dict]:
    if not _STORE_PATH.exists():
        return []
    try:
        return json.loads(_STORE_PATH.read_text())
    except Exception:
        return []


def _save(fills: list[dict]) -> None:
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STORE_PATH.write_text(json.dumps(fills, indent=2))


def append_fill(order_id: str, exchange: str, symbol: str, transaction_type: str, quantity: int,
                 price: float, product: str, paper: bool) -> None:
    fills = _load()
    fills.append({
        "order_id": order_id,
        "exchange": exchange,
        "symbol": symbol,
        "expiry": parse_expiry(symbol),
        "transaction_type": transaction_type,
        "quantity": quantity,
        "price": price,
        "product": product,
        "paper": paper,
        "filled_at": time.time(),
    })
    _save(fills)


def get_fills(expiry: str | None = None) -> list[dict]:
    fills = _load()
    if expiry:
        fills = [f for f in fills if f["expiry"] == expiry]
    return fills


def closed_positions_by_expiry(open_symbols: set[str]) -> list[dict]:
    """
    Net every fill per symbol; anything netting to zero quantity that isn't
    currently an open position is a "closed this expiry" row -- including
    ones closed on an earlier day, as long as we've logged the fills.
    """
    fills = _load()
    by_symbol: dict[str, dict] = {}
    for f in fills:
        agg = by_symbol.setdefault(f["symbol"], {
            "symbol": f["symbol"], "expiry": f["expiry"], "exchange": f["exchange"],
            "net_qty": 0, "buy_value": 0.0, "sell_value": 0.0, "buy_qty": 0, "sell_qty": 0,
        })
        signed = f["quantity"] if f["transaction_type"] == "BUY" else -f["quantity"]
        agg["net_qty"] += signed
        if f["transaction_type"] == "BUY":
            agg["buy_value"] += f["price"] * f["quantity"]
            agg["buy_qty"] += f["quantity"]
        else:
            agg["sell_value"] += f["price"] * f["quantity"]
            agg["sell_qty"] += f["quantity"]

    closed = []
    for symbol, agg in by_symbol.items():
        if agg["net_qty"] == 0 and symbol not in open_symbols and agg["buy_qty"] and agg["sell_qty"]:
            avg_buy = agg["buy_value"] / agg["buy_qty"]
            avg_sell = agg["sell_value"] / agg["sell_qty"]
            realized = (avg_sell - avg_buy) * min(agg["buy_qty"], agg["sell_qty"])
            closed.append({
                "symbol": symbol,
                "expiry": agg["expiry"],
                "exchange": agg["exchange"],
                "avg_buy_price": round(avg_buy, 2),
                "avg_sell_price": round(avg_sell, 2),
                "quantity": min(agg["buy_qty"], agg["sell_qty"]),
                "realized_pnl": round(realized, 2),
            })
    return closed
