"""
Symbol -> (exchange, token) lookup, backing the search box on the Chart tab
(and usable from the Strategy Builder's leg form) instead of typing raw
instrument tokens in by hand.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from .. import instrument_store

logger = logging.getLogger("terminal.instruments")
router = APIRouter(prefix="/api/instruments", tags=["instruments"])


@router.get("/search")
def search_instruments(q: str = Query(..., min_length=1), exchange: str | None = None, limit: int = 25):
    try:
        return instrument_store.search(q, exchange, limit)
    except Exception as exc:
        logger.exception("Instrument search failed")
        raise HTTPException(502, f"Could not search instruments: {exc}") from exc


@router.post("/refresh")
def refresh_instruments():
    try:
        count = instrument_store.download(force=True)
    except Exception as exc:
        logger.exception("Instrument master download failed")
        raise HTTPException(502, f"Could not download instrument master: {exc}") from exc
    return {"cached_instruments": count}
