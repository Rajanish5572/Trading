"""
Entry point. Serves the frontend as static files and exposes:
  - REST routers for chart / option chain / analytics / strategy / positions
  - WebSocket endpoints /ws/market and /ws/orders that the browser connects
    to for live ticks and order/fill updates (fed by ws_relay.bridge)

Run with:  uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
(from inside backend/, with the venv from requirements.txt active)
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .routers import analytics, chart, option_chain, positions, strategy
from .ws_relay import bridge, manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("terminal.main")

app = FastAPI(title="Trading Terminal")

app.include_router(chart.router)
app.include_router(option_chain.router)
app.include_router(analytics.router)
app.include_router(strategy.router)
app.include_router(positions.router)


@app.get("/api/health")
def health():
    settings = get_settings()
    return {"status": "ok", "paper_mode": settings.paper_mode}


@app.websocket("/ws/market")
async def ws_market(websocket: WebSocket):
    await manager.connect("market", websocket)
    try:
        while True:
            await websocket.receive_text()  # frontend doesn't need to send anything; just keep the socket open
    except WebSocketDisconnect:
        await manager.disconnect("market", websocket)


@app.websocket("/ws/orders")
async def ws_orders(websocket: WebSocket):
    await manager.connect("orders", websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect("orders", websocket)


@app.on_event("startup")
def startup() -> None:
    settings = get_settings()
    mode = "PAPER" if settings.paper_mode else "LIVE"
    logger.info("Starting terminal in %s mode", mode)

    # bridge.start() logs into Arrow and opens a websocket -- both are network
    # calls with no guaranteed timeout inside pyarrow_client. If either hangs
    # (bad credentials that the broker doesn't fail fast on, a firewall that
    # silently drops packets instead of rejecting, IP mismatch, etc.), running
    # this inline would block FastAPI's entire startup and the UI would never
    # become reachable -- exactly what happened when this blocked instead of
    # erroring. Running it on a background thread means the web server starts
    # and the UI loads immediately regardless of whether Arrow ever connects;
    # if it fails or hangs, you'll just see no live ticks until it's fixed,
    # not a dead app.
    def _start_bridge_in_background() -> None:
        try:
            bridge.start()
        except Exception:
            logger.exception("Market data bridge failed to start -- check .env credentials")

    threading.Thread(target=_start_bridge_in_background, daemon=True, name="arrow-bridge-startup").start()


frontend_dir = Path(__file__).resolve().parent.parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
