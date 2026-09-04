"""
Thin wrapper around pyarrow_client (the Arrow / iRage broker SDK).

Everything the rest of the app needs from the broker goes through this one
module: authentication + token caching, quotes, historical candles, option
chain, margin, and (live) order placement. Routers never import
pyarrow_client directly -- they import this module, so swapping the paper
engine in/out (see paper_engine.py) is a single branch point.

Arrow session tokens are valid for 24h (SEBI rule) and there is no refresh
endpoint, so we cache the raw token to disk and only re-authenticate when it
is missing or the broker rejects it.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Optional

from .config import get_settings

logger = logging.getLogger("terminal.arrow_client")


class ArrowClientWrapper:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._client = None
        self._streams = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------
    def _load_cached_token(self) -> Optional[str]:
        path = Path(self.settings.token_cache_path)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            if time.time() - data.get("saved_at", 0) < 23 * 3600:  # leave margin before 24h
                return data.get("token")
        except Exception:
            logger.exception("Could not read cached token, ignoring")
        return None

    def _save_token(self, token: str) -> None:
        path = Path(self.settings.token_cache_path)
        path.write_text(json.dumps({"token": token, "saved_at": time.time()}))

    def client(self):
        """Return an authenticated ArrowClient, logging in if needed."""
        with self._lock:
            if self._client is not None:
                return self._client

            from pyarrow_client import ArrowClient  # imported lazily so the

            # rest of the app can boot even before the SDK is installed
            c = ArrowClient(app_id=self.settings.arrow_app_id)

            cached = self._load_cached_token()
            if cached:
                c.set_token(cached)
                logger.info("Reusing cached Arrow session token")
            else:
                logger.info("No usable cached token, running auto_login")
                c.auto_login(
                    user_id=self.settings.arrow_user_id,
                    password=self.settings.arrow_password,
                    api_secret=self.settings.arrow_app_secret,
                    totp_secret=self.settings.arrow_totp_secret,
                )
                self._save_token(c.get_token())

            self._client = c
            return self._client

    def streams(self):
        """Return a connected ArrowStreams instance (market data + order updates)."""
        with self._lock:
            if self._streams is not None:
                return self._streams

            from pyarrow_client import ArrowStreams

            token = self.client().get_token()
            s = ArrowStreams(appID=self.settings.arrow_app_id, token=token, debug=False)
            self._streams = s
            return self._streams

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------
    def get_quote(self, mode: str, symbol: str, exchange: str) -> dict:
        from pyarrow_client import QuoteMode, Exchange as ArrowExchange

        return self.client().get_quote(getattr(QuoteMode, mode), symbol, getattr(ArrowExchange, exchange))

    def get_candles(self, exchange: str, token: int, interval: str, start_iso: str, end_iso: str, oi: bool = False):
        return self.client().get_historical_candles(
            exchange=exchange, token=token, interval=interval, from_dt=start_iso, to_dt=end_iso, oi=oi
        )

    def get_option_chain(self, underlying: str, exchange: str, expiry: str, count: int = 20):
        return self.client().get_option_chain(underlying=underlying, exchange=exchange, count=count, expiry=expiry)

    def get_option_chain_symbols(self):
        return self.client().get_option_chain_symbols()

    def get_index_list(self):
        return self.client().get_index_list()

    # ------------------------------------------------------------------
    # Orders / portfolio -- LIVE. Never call these directly from a router;
    # go through order_gateway.py so paper mode is respected everywhere.
    # ------------------------------------------------------------------
    def place_order(self, **kwargs) -> str:
        return self.client().place_order(**kwargs)

    def modify_order(self, order_id: str, **kwargs) -> str:
        return self.client().modify_order(order_id, **kwargs)

    def cancel_order(self, order_id: str) -> str:
        return self.client().cancel_order(order_id)

    def get_order_book(self) -> list:
        return self.client().get_order_book()

    def get_positions(self) -> list:
        return self.client().get_positions()

    def get_holdings(self) -> list:
        return self.client().get_holdings()

    def get_user_limits(self) -> dict:
        return self.client().get_user_limits()

    def order_margin(self, **kwargs) -> dict:
        return self.client().order_margin(**kwargs)

    def basket_margin(self, orders: list) -> dict:
        return self.client().basket_margin(orders)


_wrapper: Optional[ArrowClientWrapper] = None


def get_arrow_client() -> ArrowClientWrapper:
    global _wrapper
    if _wrapper is None:
        _wrapper = ArrowClientWrapper()
    return _wrapper
