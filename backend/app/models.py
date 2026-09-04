"""Shared pydantic schemas used across routers."""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel


class TransactionType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    SL_LIMIT = "STOP_LOSS_LIMIT"
    SL_MARKET = "STOP_LOSS_MARKET"


class ProductType(str, Enum):
    MIS = "MIS"
    CNC = "CNC"
    NRML = "NRML"


class Exchange(str, Enum):
    NSE = "NSE"
    BSE = "BSE"
    NFO = "NFO"
    BFO = "BFO"
    MCXFO = "MCXFO"


class PlaceOrderRequest(BaseModel):
    exchange: Exchange
    symbol: str
    quantity: int
    product: ProductType
    order_type: OrderType
    transaction_type: TransactionType
    price: Optional[float] = 0.0
    trigger_price: Optional[float] = None
    disclosed_quantity: int = 0
    tag: Optional[str] = None


class ModifyOrderRequest(BaseModel):
    quantity: Optional[int] = None
    price: Optional[float] = None
    trigger_price: Optional[float] = None
    order_type: Optional[OrderType] = None


class StrategyLeg(BaseModel):
    symbol: str
    token: int = 0  # instrument token, needed for historical candle lookups (backtest)
    strike: float
    option_type: str  # CE / PE / FUT
    transaction_type: TransactionType
    quantity: int
    lot_size: int = 1
    premium: float = 0.0


class PayoffRequest(BaseModel):
    underlying: str
    spot: float
    legs: list[StrategyLeg]
    price_range_pct: float = 0.10  # +/- 10% of spot by default


class BacktestRequest(BaseModel):
    underlying: str
    from_date: str
    to_date: str
    legs: list[StrategyLeg]
    entry_time: str = "09:20"
    exit_time: str = "15:15"
