"""
Single choke point for anything that touches orders, positions, or account
limits. Every router imports THIS module, never arrow_client or paper_engine
directly, so paper_mode is enforced in exactly one place and can't be
accidentally bypassed by a new endpoint later.
"""
from __future__ import annotations

from .arrow_client import get_arrow_client
from .config import get_settings
from .paper_engine import get_paper_engine


def _is_paper() -> bool:
    return get_settings().paper_mode


def place_order(**kwargs) -> str:
    if _is_paper():
        return get_paper_engine().place_order(**kwargs)
    return get_arrow_client().place_order(**kwargs)


def modify_order(order_id: str, **kwargs) -> str:
    if _is_paper():
        return get_paper_engine().modify_order(order_id, **kwargs)
    return get_arrow_client().modify_order(order_id, **kwargs)


def cancel_order(order_id: str) -> str:
    if _is_paper():
        return get_paper_engine().cancel_order(order_id)
    return get_arrow_client().cancel_order(order_id)


def get_order_book() -> list:
    if _is_paper():
        return get_paper_engine().get_order_book()
    return get_arrow_client().get_order_book()


def get_positions() -> list:
    if _is_paper():
        return get_paper_engine().get_positions()
    return get_arrow_client().get_positions()


def get_user_limits() -> dict:
    if _is_paper():
        return get_paper_engine().get_user_limits()
    return get_arrow_client().get_user_limits()


def is_paper_mode() -> bool:
    return _is_paper()
