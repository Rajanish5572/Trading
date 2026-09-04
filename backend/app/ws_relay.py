"""
Bridges Arrow's own WebSocket feeds (market data ticks + order updates,
callback-based, run on their own background thread by pyarrow_client) into
FastAPI's asyncio-native WebSocket endpoints that the browser connects to.

Market data ticks always come from the live feed, even in paper mode --
paper mode only changes what happens to *orders*, not where prices come
from. Every tick is also handed to the paper engine so pending simulated
limit/SL orders can be checked.

Design: one MarketDataBridge per process, started once at startup. The
frontend doesn't talk to Arrow directly -- it subscribes to symbols by
calling POST /api/chart/subscribe, and receives ticks over GET /ws/market
-- and receives ticks over ws://.../ws/market as JSON.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import WebSocket

from .arrow_client import get_arrow_client
from .paper_engine import get_paper_engine
from . import trade_log

logger = logging.getLogger("terminal.ws_relay")


class ConnectionManager:
    def __init__(self) -> None:
        self._channels: dict[str, set[WebSocket]] = {"market": set(), "orders": set()}
        self._lock = asyncio.Lock()

    async def connect(self, channel: str, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._channels.setdefault(channel, set()).add(ws)

    async def disconnect(self, channel: str, ws: WebSocket) -> None:
        async with self._lock:
            self._channels.get(channel, set()).discard(ws)

    async def broadcast(self, channel: str, message: dict) -> None:
        dead = []
        for ws in list(self._channels.get(channel, set())):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._channels.get(channel, set()).discard(ws)


manager = ConnectionManager()


class MarketDataBridge:
    """Owns the connection to Arrow's streaming API and fans ticks out."""

    def __init__(self) -> None:
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._token_to_symbol: dict[int, str] = {}
        self._started = False

    def register_symbol(self, token: int, symbol: str) -> None:
        self._token_to_symbol[token] = symbol

    def start(self, loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
        """
        Call once from FastAPI's startup event. Runs on a background thread
        (see main.py) so a slow/hung Arrow login can't block the app itself
        from starting -- which means this thread has no event loop of its
        own. `loop` must be the actual running asyncio loop (captured on the
        main thread via asyncio.get_running_loop()) so ticks can be handed
        back to it with run_coroutine_threadsafe. Without this, ticks would
        have nowhere safe to go.
        """
        if self._started:
            return
        self._started = True
        self._loop = loop

        try:
            streams = get_arrow_client().streams()
        except Exception:
            logger.exception(
                "Could not connect to Arrow streams -- check credentials in .env. "
                "The UI will still load but no live ticks will arrive."
            )
            return

        def on_tick(tick) -> None:
            symbol = self._token_to_symbol.get(getattr(tick, "token", None))
            payload = {
                "token": getattr(tick, "token", None),
                "symbol": symbol,
                "ltp": getattr(tick, "ltp", None),
                "net_change": getattr(tick, "net_change", None),
                "volume": getattr(tick, "volume", None),
                "oi": getattr(tick, "oi", None),
                "bids": getattr(tick, "bids", None),
                "asks": getattr(tick, "asks", None),
            }
            if symbol and payload["ltp"] is not None:
                get_paper_engine().on_tick(symbol, float(payload["ltp"]))
            if self._loop:
                asyncio.run_coroutine_threadsafe(manager.broadcast("market", payload), self._loop)

        def on_order_update(update) -> None:
            data = dict(getattr(update, "__dict__", update) or {})
            if data.get("orderStatus") == "COMPLETE":
                try:
                    trade_log.append_fill(
                        order_id=data.get("orderId", ""), exchange=data.get("exchange", ""),
                        symbol=data.get("symbol", ""), transaction_type=data.get("transactionType", ""),
                        quantity=data.get("quantity", 0), price=data.get("averagePrice", 0.0),
                        product=data.get("product", ""), paper=False,
                    )
                except Exception:
                    logger.exception("Failed to log live fill")
            if self._loop:
                asyncio.run_coroutine_threadsafe(manager.broadcast("orders", data), self._loop)

        streams.data_stream.on_ticks = on_tick
        if hasattr(streams, "order_stream"):
            streams.order_stream.on_update = on_order_update

        streams.connect_all()
        logger.info("Connected to Arrow market data + order streams")

    def subscribe(self, mode: str, tokens_to_symbols: dict[int, str]) -> None:
        for token, symbol in tokens_to_symbols.items():
            self.register_symbol(token, symbol)
        try:
            from pyarrow_client import DataMode

            get_arrow_client().streams().subscribe_market_data(getattr(DataMode, mode), list(tokens_to_symbols.keys()))
        except Exception:
            logger.exception("Subscribe failed -- streams may not be connected yet")


bridge = MarketDataBridge()
