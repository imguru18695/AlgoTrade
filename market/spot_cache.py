"""
Rolling spot-price cache for the RM engine's underlying-based checks (Spot
Range Guard, Spot Velocity Guard). Reuses the exact same live-quote sources
Dashboard already depends on (market.live_nse for NIFTY, market.live for
SENSEX/BANKNIFTY via Kite) on its own short cadence, decoupled from
Dashboard's poll rate — so the RM engine's 1-second tick loop never makes a
network call itself, only ever reads this cache.
"""
import asyncio
import logging
import time

logger = logging.getLogger(__name__)

REFRESH_INTERVAL = 5        # seconds between spot refreshes
HISTORY_MAX_MINUTES = 120   # covers any velocity window a basket could reasonably configure

_current: dict[str, float] = {}
_history: dict[str, list[tuple[float, float]]] = {}  # underlying -> [(monotonic_ts, spot), ...]


def get_spot(underlying: str) -> float | None:
    return _current.get(underlying)


def get_spot_n_min_ago(underlying: str, minutes: int) -> float | None:
    """Spot closest to (but not newer than) `minutes` ago. None if we don't
    have that much history yet — the velocity check simply skips that tick
    rather than firing on incomplete data, same as the LTP-unavailable guard
    the engine already has for P&L."""
    hist = _history.get(underlying)
    if not hist:
        return None
    target = time.monotonic() - minutes * 60
    if hist[0][0] > target:
        return None
    result = hist[0][1]
    for ts, spot in hist:
        if ts > target:
            break
        result = spot
    return result


def _record(underlying: str, spot: float):
    now = time.monotonic()
    _current[underlying] = spot
    hist = _history.setdefault(underlying, [])
    hist.append((now, spot))
    cutoff = now - HISTORY_MAX_MINUTES * 60
    while hist and hist[0][0] < cutoff:
        hist.pop(0)


def _refresh_sync(kite):
    """Blocking — call via asyncio.to_thread, never directly on the event loop."""
    from market import live_nse as mnse
    nse_spot = None
    try:
        nse_spot = mnse.fetch_nifty_spot()
    except Exception as e:
        logger.warning(f"spot_cache: fetch_nifty_spot failed: {e}")
    if nse_spot:
        _record("NIFTY", nse_spot)

    if kite is not None:
        from market import live as mlive
        keys_needed = ["SENSEX", "BANKNIFTY"] + ([] if nse_spot else ["NIFTY"])
        try:
            quotes = mlive.fetch_quotes(kite, keys_needed)
        except Exception as e:
            logger.warning(f"spot_cache: fetch_quotes failed: {e}")
            quotes = {}
        for key, q in quotes.items():
            _record(key, q["spot"])


async def refresh_loop(get_kite_fn):
    """Background task — mirrors main.py's _refresh_loop pattern.
    get_kite_fn() should return an authenticated Kite client, or None when no
    session is active (NIFTY via jugaad still works either way)."""
    while True:
        await asyncio.sleep(REFRESH_INTERVAL)
        try:
            kite = get_kite_fn() if get_kite_fn else None
            await asyncio.to_thread(_refresh_sync, kite)
        except Exception as e:
            logger.error(f"spot_cache: refresh failed: {e}")
