"""
In-memory paper trading engine.

Arrow's API has no sandbox/simulation mode, so this is the safety net: while
PAPER_MODE=true (the default -- see config.py), every order placed through
order_gateway.py lands here instead of going to the broker. Fills are
simulated against the last known LTP for the symbol; positions, cash, and a
trade log are kept in memory for the life of the process.

This is deliberately simple (no partial fills, no slippage model, no queue
position) -- it exists to let you exercise the whole terminal (chart ->
option chain -> strategy builder -> positions tab -> order execution) without
risking capital while you find bugs, not to be a realistic backtester. Real
backtesting against historical data lives in routers/strategy.py.
"""
from __future__ import annotations

import itertools
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from .config import get_settings
from . import trade_log


@dataclass
class PaperOrder:
    order_id: str
    exchange: str
    symbol: str
    quantity: int
    product: str
    order_type: str
    transaction_type: str
    price: float
    trigger_price: Optional[float]
    status: str = "OPEN"  # OPEN, COMPLETE, CANCELLED, REJECTED
    filled_price: Optional[float] = None
    placed_at: float = field(default_factory=time.time)


@dataclass
class PaperPosition:
    exchange: str
    symbol: str
    product: str
    quantity: int = 0  # net qty, +ve long, -ve short
    avg_price: float = 0.0
    realized_pnl: float = 0.0


class PaperEngine:
    def __init__(self) -> None:
        settings = get_settings()
        self.cash = settings.paper_starting_cash
        self.starting_cash = settings.paper_starting_cash
        self._orders: dict[str, PaperOrder] = {}
        self._positions: dict[str, PaperPosition] = {}
        self._id_counter = itertools.count(1)
        self._lock = threading.Lock()
        self._last_ltp: dict[str, float] = {}  # symbol -> last seen LTP, fed by ws_relay

    # ------------------------------------------------------------------
    def on_tick(self, symbol: str, ltp: float) -> None:
        """Called by ws_relay on every tick so pending LIMIT orders can be checked."""
        with self._lock:
            self._last_ltp[symbol] = ltp
            for order in list(self._orders.values()):
                if order.status != "OPEN" or order.symbol != symbol:
                    continue
                self._try_fill(order, ltp)

    def _try_fill(self, order: PaperOrder, ltp: float) -> None:
        should_fill = False
        if order.order_type in ("MARKET",):
            should_fill = True
        elif order.order_type == "LIMIT":
            if order.transaction_type == "BUY" and ltp <= order.price:
                should_fill = True
            elif order.transaction_type == "SELL" and ltp >= order.price:
                should_fill = True
        elif order.order_type in ("STOP_LOSS_LIMIT", "STOP_LOSS_MARKET"):
            trigger = order.trigger_price or order.price
            if order.transaction_type == "BUY" and ltp >= trigger:
                should_fill = True
            elif order.transaction_type == "SELL" and ltp <= trigger:
                should_fill = True

        if should_fill:
            self._fill(order, ltp)

    def _fill(self, order: PaperOrder, fill_price: float) -> None:
        order.status = "COMPLETE"
        order.filled_price = fill_price

        pos = self._positions.setdefault(
            order.symbol,
            PaperPosition(exchange=order.exchange, symbol=order.symbol, product=order.product),
        )
        signed_qty = order.quantity if order.transaction_type == "BUY" else -order.quantity
        new_qty = pos.quantity + signed_qty

        if pos.quantity == 0 or (pos.quantity > 0) == (signed_qty > 0):
            # adding to (or opening) a position -> blend average price
            total_cost = pos.avg_price * abs(pos.quantity) + fill_price * abs(signed_qty)
            pos.avg_price = total_cost / abs(new_qty) if new_qty != 0 else 0.0
        else:
            # reducing or flipping -> realize pnl on the closed portion
            closed_qty = min(abs(signed_qty), abs(pos.quantity))
            direction = 1 if pos.quantity > 0 else -1
            pos.realized_pnl += direction * (fill_price - pos.avg_price) * closed_qty
            if abs(signed_qty) > abs(pos.quantity):
                pos.avg_price = fill_price  # flipped through zero into the other side

        pos.quantity = new_qty
        self.cash -= signed_qty * fill_price

        trade_log.append_fill(
            order_id=order.order_id, exchange=order.exchange, symbol=order.symbol,
            transaction_type=order.transaction_type, quantity=order.quantity,
            price=fill_price, product=order.product, paper=True,
        )

    # ------------------------------------------------------------------
    # Public API mirrors arrow_client's order methods
    # ------------------------------------------------------------------
    def place_order(self, exchange, symbol, quantity, product, order_type, transaction_type, price=0.0,
                     trigger_price=None, disclosed_quantity=0, tag=None, **_ignored) -> str:
        with self._lock:
            order_id = f"PAPER-{next(self._id_counter)}"
            order = PaperOrder(
                order_id=order_id,
                exchange=str(exchange),
                symbol=symbol,
                quantity=quantity,
                product=str(product),
                order_type=str(order_type),
                transaction_type=str(transaction_type),
                price=price or 0.0,
                trigger_price=trigger_price,
            )
            self._orders[order_id] = order
            ltp = self._last_ltp.get(symbol)
            if ltp is not None:
                self._try_fill(order, ltp)
            return order_id

    def modify_order(self, order_id: str, **kwargs) -> str:
        with self._lock:
            order = self._orders.get(order_id)
            if not order or order.status != "OPEN":
                raise ValueError(f"Cannot modify order {order_id} (not found or not open)")
            for key in ("quantity", "price", "trigger_price"):
                if kwargs.get(key) is not None:
                    setattr(order, key, kwargs[key])
            if kwargs.get("order_type"):
                order.order_type = str(kwargs["order_type"])
            return order_id

    def cancel_order(self, order_id: str) -> str:
        with self._lock:
            order = self._orders.get(order_id)
            if not order or order.status != "OPEN":
                raise ValueError(f"Cannot cancel order {order_id} (not found or not open)")
            order.status = "CANCELLED"
            return order_id

    def get_order_book(self) -> list[dict]:
        with self._lock:
            return [self._order_to_dict(o) for o in self._orders.values()]

    def get_positions(self) -> list[dict]:
        with self._lock:
            out = []
            for pos in self._positions.values():
                ltp = self._last_ltp.get(pos.symbol, pos.avg_price)
                unrealized = (ltp - pos.avg_price) * pos.quantity if pos.quantity else 0.0
                out.append({
                    "exchange": pos.exchange,
                    "symbol": pos.symbol,
                    "product": pos.product,
                    "quantity": pos.quantity,
                    "avg_price": round(pos.avg_price, 2),
                    "ltp": round(ltp, 2),
                    "realized_pnl": round(pos.realized_pnl, 2),
                    "unrealized_pnl": round(unrealized, 2),
                })
            return out

    def get_user_limits(self) -> dict:
        with self._lock:
            mtm = sum(
                (self._last_ltp.get(p.symbol, p.avg_price) - p.avg_price) * p.quantity
                for p in self._positions.values()
            )
            return {
                "totalCash": round(self.starting_cash, 2),
                "usableMargin": round(self.cash, 2),
                "netPnl": round(mtm + sum(p.realized_pnl for p in self._positions.values()), 2),
                "mtmLoss": round(min(mtm, 0), 2),
                "paperMode": True,
            }

    @staticmethod
    def _order_to_dict(o: PaperOrder) -> dict:
        return {
            "order_id": o.order_id,
            "exchange": o.exchange,
            "symbol": o.symbol,
            "quantity": o.quantity,
            "product": o.product,
            "order_type": o.order_type,
            "transaction_type": o.transaction_type,
            "price": o.price,
            "trigger_price": o.trigger_price,
            "status": o.status,
            "filled_price": o.filled_price,
            "placed_at": o.placed_at,
        }


_engine: Optional[PaperEngine] = None


def get_paper_engine() -> PaperEngine:
    global _engine
    if _engine is None:
        _engine = PaperEngine()
    return _engine
