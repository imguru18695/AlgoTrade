"""Shared instrument-classification helpers. Used by both rm/engine.py's
Spot Range/Velocity Guards (to know which live index to check spot against)
and baskets/service.py (to enforce single-underlying-per-basket) - kept in
one place so the two can never silently drift apart on what "the same
underlying" means for a given tradingsymbol.
"""
import time

# Checked longest-prefix-first only because it reads clearer that way - none
# of these names actually collide as string prefixes of one another.
UNDERLYING_PREFIXES = ("BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTY", "SENSEX")


def underlying_of(tradingsymbol: str) -> str | None:
    """The index a single option tradingsymbol belongs to, or None if it
    doesn't match a known index prefix (equity/commodity - those aren't
    subject to the single-underlying-per-basket constraint, nor do the Spot
    Guards apply to them)."""
    for prefix in UNDERLYING_PREFIXES:
        if tradingsymbol.startswith(prefix):
            return prefix
    return None


# Lot sizes are per-tradingsymbol, not per-underlying-prefix: equity F&O
# alone spans hundreds of stocks, each with its own lot size, and NSE/BSE
# revise them periodically (most recently under SEBI's minimum-contract-value
# framework). A hardcoded table would need constant upkeep and would silently
# go stale, so this fetches Kite's own instrument master instead - the same
# live source Kite itself trades against - and caches it. Mirrors the caching
# convention in market/live.py's _resolve_tokens (module-level dict + TTL,
# refreshed lazily on the next call after expiry).
_LOT_SIZE_CACHE: dict[tuple[str, str], int] = {}
_LOT_SIZE_CACHE_TS = 0.0
_LOT_SIZE_CACHE_TTL = 24 * 3600


def _refresh_lot_sizes(kite) -> None:
    global _LOT_SIZE_CACHE_TS
    fresh: dict[tuple[str, str], int] = {}
    for exch in ("NFO", "BFO"):   # NSE and BSE F&O - covers every index AND equity derivative
        try:
            dump = kite.instruments(exch)
        except Exception:
            continue
        for row in dump:
            fresh[(row["exchange"], row["tradingsymbol"])] = row["lot_size"]
    if fresh:
        _LOT_SIZE_CACHE.clear()
        _LOT_SIZE_CACHE.update(fresh)
        _LOT_SIZE_CACHE_TS = time.time()


def lots_of(tradingsymbol: str, exchange: str, quantity: int, kite=None) -> int | None:
    """Signed lot count for a position (negative = short). Looks up the lot
    size from Kite's live instrument master (kite.instruments("NFO"/"BFO")),
    refreshed at most once a day. Returns None when the symbol isn't found
    there (cash equities have no F&O lot size - NSE/BSE list those at
    lot_size=1, which isn't worth showing alongside the raw quantity) or when
    no kite session is available yet - callers should leave the lot count
    blank rather than guess."""
    if kite is not None and (not _LOT_SIZE_CACHE or time.time() - _LOT_SIZE_CACHE_TS >= _LOT_SIZE_CACHE_TTL):
        _refresh_lot_sizes(kite)
    lot_size = _LOT_SIZE_CACHE.get((exchange, tradingsymbol))
    if not lot_size or lot_size <= 1:
        return None
    return round(quantity / lot_size)
