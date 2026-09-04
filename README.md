# Terminal -- personal trading terminal on Arrow (iRage) API

A locally-run trading terminal: live chart with indicators, option chain,
OI/straddle/IV analytics, a multi-leg strategy builder with payoff diagrams
and backtesting, and a positions/orders tab with order execution -- all
backed by Arrow's (arrow.trade) Python SDK.

## Status: scaffold

Every tab is wired end to end against real endpoint shapes, but this has
**not been run against a live Arrow account yet**. Treat it as a working
skeleton to fill in and harden, not a finished product. Known gaps are
called out in comments where they matter (search for "TODO" and read the
module docstrings in `backend/app/`).

## Safety: paper mode is on by default

`PAPER_MODE=true` in `.env` routes every order to an in-memory simulator
(`backend/app/paper_engine.py`) instead of the broker. Live market data
still flows in either mode -- only order execution is simulated. Arrow's
API has no sandbox of its own, so **do not flip `PAPER_MODE=false` until
you've exercised every tab in paper mode and trust the flow**, including:
placing/modifying/cancelling orders, seeing fills land in the Positions
tab, and seeing live ticks update the chart and depth panel.

Paper mode state (positions, cash, order book) lives in memory and resets
every time you restart the server. Fill history for the Positions tab's
"closed this expiry" table is separately persisted to
`backend/data/trade_log.json` so it survives restarts.

## Where historical data comes from, and where it's saved

Candles (chart tab, straddle chart, backtests) come from Arrow's
`historical-api.arrow.trade`, fetched on demand -- there's no bulk
download step. The first time you ask for a given (exchange, token,
interval, date range), it hits Arrow's API; after that, `history_store.py`
caches it locally in a SQLite file at `backend/data/market_data.db`, and
later requests for the same range are served from disk instead of
re-fetching. Today's still-forming candles are always re-fetched fresh
(the cache only trusts *closed* days), so the chart still updates live.

This matters most for the backtest: re-running the same date range while
you tune a strategy hits the network once, not once per run. It's a
single file, not a database server -- nothing to install or run
separately.

`backend/data/` (this cache, the trade log, and the IV history) is
git-ignored -- it's regenerable local state, not something to version or
share. If you move to a new machine, it starts empty and rebuilds itself
as you use the terminal.

## Moving this to another machine / git

The repo is safe to push to a personal GitHub as-is -- `.gitignore` already
excludes `backend/.env`, `backend/.arrow_token.json`, and `backend/data/`,
so credentials and local runtime state never leave this machine. From
here:

```bash
cd /path/to/trading-terminal
git init
git add .
git commit -m "Initial terminal scaffold"
git remote add origin <your-personal-repo-url>
git push -u origin main
```

Then on the other machine: `git clone <url>`, and pick back up at step 2
of Setup below (`.env` isn't in the repo, so you'll fill it in fresh there
with the same credentials -- or new ones if you re-registered the API app
with that machine's IP).

## Setup

1. Get Arrow API credentials at https://arrow.trade (app_id, app_secret,
   your client login, TOTP secret for `auto_login`). SEBI's Feb-2025 algo
   circular requires a static IP registered with the broker for API
   access -- if you're running this from home, that means your home IP
   (may need a static IP add-on from your ISP), or a small VPS if you'd
   rather not depend on your home connection.

2. ```bash
   cd backend
   python3 -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env   # then fill in your Arrow credentials
   ```

3. Run:
   ```bash
   uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
   ```
   Open http://127.0.0.1:8000 in your browser.

## Layout

```
backend/
  app/
    main.py            FastAPI app, static file serving, websocket endpoints
    config.py           settings from .env (paper_mode lives here)
    arrow_client.py      wrapper around pyarrow_client (auth, quotes, orders, margin)
    paper_engine.py       simulated fills against live LTP
    order_gateway.py       single branch point: paper vs live, used by every router
    ws_relay.py            bridges Arrow's callback-based WS into FastAPI's asyncio WS
    trade_log.py           local fill log, grouped by expiry (for Positions tab)
    iv_store.py             local daily IV history, for the IV percentile card
    history_store.py         local SQLite cache for historical candles
    indicators/            MA, Supertrend, CPR, RSI, MACD, volume profile -- pure functions
    routers/
      chart.py              candles + indicators, live-tick subscribe
      option_chain.py        strikes for underlying+expiry, ATM + PCR
      analytics.py            OI buildup classification, straddle chart, IV percentile
      strategy.py              payoff diagram, basket margin, day-by-day backtest
      positions.py             positions, closed-same-expiry, orders, place/modify/cancel
frontend/
  index.html             tab shell (chart tab markup is static; others render via JS)
  js/                    one file per tab + api.js (fetch wrapper) + ws.js (live feed)
```

## What still needs real-world hardening before you trust it with size

- **Multi-leg execution**: Arrow has no atomic basket order. The strategy
  builder computes payoff/margin for a basket, but *placing* a multi-leg
  trade means firing each leg's order separately from the Positions tab's
  order ticket -- there's no "execute this strategy" button yet, and if
  you want one, you'll need to decide how to handle a leg that fails to
  fill after others already have.
- **Instrument tokens**: several endpoints (`chart` candles, `strategy`
  backtest) need the Arrow instrument *token*, not just the symbol. Wire
  up `get_arrow_client().client().get_instruments()` and cache it locally
  so the UI can resolve symbol -> token instead of you typing tokens in by
  hand (the current UI has raw token inputs as a placeholder).
- **IV percentile** needs months of accumulated daily samples (or a
  backfill from an external source) before it's statistically meaningful
  -- see the docstring in `iv_store.py`.
- **get_greeks reliability**: Arrow's own docs flag this endpoint as
  possibly disabled on some environments. Confirm it works on your account
  before leaning on the IV percentile card.
- **Rate limits**: not documented anywhere Arrow's docs dump exposed for
  the standard REST API. The analytics OI-buildup endpoint currently
  fires one quote request per strike in a loop -- if you hit limits,
  batch these through the WebSocket FULL-mode subscription instead.
- **No backtest slippage/brokerage model** -- `strategy.py`'s backtest is
  intentionally simple (entry-time price vs exit-time price, per leg, per
  day). Good for sanity-checking an idea's direction, not for sizing
  expected live P&L.
- **Holidays**: the backtest's trading-day loop only skips weekends, not
  exchange holidays. Days with no data are reported as such rather than
  silently skipped, but you'll see a few false "no data" rows around
  holidays.

## Regulatory note (not legal advice)

If the strategy builder's backtest results tempt you toward fully
automated, signal-driven order placement (no human clicking the button),
that likely falls under SEBI's algo trading framework for retail/API
usage, which has its own registration and tagging requirements separate
from just having API access. Manually clicking Buy/Sell in this UI based
on what you see is a different regulatory posture than a script that
places orders on its own -- worth checking current SEBI circulars (or
Arrow's own compliance docs) before wiring the strategy builder directly
to the order gateway.
