"""
Positions tab: open positions, closed positions for the current (unexpired)
expiry even if closed on an earlier day, the order book split into
open/filled/cancelled, and order placement/modify/cancel -- all routed
through order_gateway so paper_mode is respected without this file needing
to know or care which mode is active.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from .. import order_gateway, trade_log
from ..models import ModifyOrderRequest, PlaceOrderRequest

logger = logging.getLogger("terminal.positions")
router = APIRouter(prefix="/api/positions", tags=["positions"])


@router.get("")
def get_positions():
    try:
        open_positions = order_gateway.get_positions()
    except Exception as exc:
        raise HTTPException(502, f"Could not fetch positions: {exc}") from exc

    open_symbols = {p["symbol"] for p in open_positions if p.get("quantity")}
    closed_positions = trade_log.closed_positions_by_expiry(open_symbols)

    return {
        "paper_mode": order_gateway.is_paper_mode(),
        "open": [p for p in open_positions if p.get("quantity")],
        "closed_same_expiry": closed_positions,
    }


@router.get("/limits")
def get_limits():
    try:
        return order_gateway.get_user_limits()
    except Exception as exc:
        raise HTTPException(502, f"Could not fetch account limits: {exc}") from exc


@router.get("/orders")
def get_orders():
    try:
        orders = order_gateway.get_order_book()
    except Exception as exc:
        raise HTTPException(502, f"Could not fetch order book: {exc}") from exc

    open_statuses = {"OPEN", "PENDING", "TRIGGER_PENDING", "PENDINGNEW"}
    return {
        "open": [o for o in orders if o.get("status") in open_statuses],
        "filled": [o for o in orders if o.get("status") == "COMPLETE"],
        "cancelled_or_rejected": [o for o in orders if o.get("status") in ("CANCELLED", "REJECTED")],
        "all": orders,
    }


@router.post("/orders")
def place_order(req: PlaceOrderRequest):
    try:
        order_id = order_gateway.place_order(
            exchange=req.exchange.value, symbol=req.symbol, quantity=req.quantity,
            product=req.product.value, order_type=req.order_type.value,
            transaction_type=req.transaction_type.value, price=req.price or 0.0,
            trigger_price=req.trigger_price, disclosed_quantity=req.disclosed_quantity, tag=req.tag,
        )
    except Exception as exc:
        logger.exception("Order placement failed")
        raise HTTPException(502, f"Order rejected: {exc}") from exc
    return {"order_id": order_id, "paper_mode": order_gateway.is_paper_mode()}


@router.put("/orders/{order_id}")
def modify_order(order_id: str, req: ModifyOrderRequest):
    try:
        order_gateway.modify_order(
            order_id, quantity=req.quantity, price=req.price,
            trigger_price=req.trigger_price, order_type=req.order_type.value if req.order_type else None,
        )
    except Exception as exc:
        raise HTTPException(502, f"Modify failed: {exc}") from exc
    return {"order_id": order_id, "status": "modified"}


@router.delete("/orders/{order_id}")
def cancel_order(order_id: str):
    try:
        order_gateway.cancel_order(order_id)
    except Exception as exc:
        raise HTTPException(502, f"Cancel failed: {exc}") from exc
    return {"order_id": order_id, "status": "cancelled"}
