"""
Live NSE (jugaad-data) connection — NIFTY spot only.

This is the "NSE from jugaad, BSE from Kite" split: NIFTY's live spot comes
from here (nseindia.com's own AJAX endpoints, no credentials, free) so it
never touches the Kite session's rate-limit budget — that stays reserved for
SENSEX (BSE isn't covered by jugaad) and, more importantly, the live-trading
RM engine's own Kite usage.

Every call is defensive: wrapped in try/except, returns None on any failure
so market/snapshot.py falls back cleanly (to Kite's series-derived spot, or
simulated) rather than risking the live app.

NOT sourced here: NIFTY's DAILY HISTORY (the series feeding EMA/RSI/MACD/
OBV/A-D/Stochastic/52W/last5). jugaad's niftyindices.com historical-data path
(NSEIndexHistory / index_df) was verified BROKEN as of 2026-09-24 — it
returns niftyindices.com's HTML shell (200 OK) instead of JSON, an anti-bot/
session wall the library doesn't handle; a fresh call reproduces it on demand.
Until that's fixed upstream (or a workaround is found), NIFTY's history stays
on Kite (market/live.py), which is proven reliable and low-frequency (5 min
cache) so the marginal Kite cost of keeping it there is small.
"""
from __future__ import annotations

import logging
import time

log = logging.getLogger("market.live_nse")

_QUOTE_CACHE: dict[str, tuple[float, dict]] = {}
_QUOTE_CACHE_TTL = 15

_client = None   # lazy singleton — constructing NSELive() opens a requests.Session


def _get_client():
    global _client
    if _client is None:
        from jugaad_data.nse import NSELive
        _client = NSELive()
    return _client


def fetch_nifty_spot() -> float | None:
    """Live NIFTY 50 underlying value, via NSE's option-chain endpoint (the
    cheapest live-value call jugaad exposes — there is no separate
    'just the index value' endpoint). Caller supplies its own previous-close
    (from whatever series it already has) to compute a change percentage."""
    now = time.time()
    cached = _QUOTE_CACHE.get("NIFTY")
    if cached and now - cached[0] < _QUOTE_CACHE_TTL:
        return cached[1]

    try:
        data = _get_client().index_option_chain("NIFTY")
        spot = data.get("records", {}).get("underlyingValue")
    except Exception as e:
        log.warning(f"market.live_nse: NIFTY spot fetch failed: {e}")
        return None
    if not spot:
        return None

    _QUOTE_CACHE["NIFTY"] = (now, spot)
    return spot
