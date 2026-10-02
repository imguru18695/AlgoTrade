"""Shared instrument-classification helpers. Used by both rm/engine.py's
Spot Range/Velocity Guards (to know which live index to check spot against)
and baskets/service.py (to enforce single-underlying-per-basket) - kept in
one place so the two can never silently drift apart on what "the same
underlying" means for a given tradingsymbol.
"""
import math
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


def detect_underlying(positions: list[dict]) -> str | None:
    """Best-effort index a basket's option legs belong to, parsed from the
    first leg's tradingsymbol prefix. None for a basket with no positions or
    whose legs don't match a known index (equity/commodity, or an index spot
    prices aren't fetched for yet). Baskets are constrained to a single
    underlying at assignment time (baskets/service.py), so in practice every
    leg agrees anyway - this just reads the first one rather than re-deriving
    a set each call. Shared by rm/engine.py (Spot Guards) and baskets/analytics.py
    (Greeks need to know which index's spot to price legs against)."""
    for p in positions:
        u = underlying_of(p.get("tradingsymbol", ""))
        if u:
            return u
    return None


# Per-tradingsymbol instrument info (lot size, strike, expiry, instrument
# type), not a per-underlying-prefix table: equity F&O alone spans hundreds
# of stocks each with their own lot size, and NSE/BSE revise these
# periodically (most recently under SEBI's minimum-contract-value framework).
# A hardcoded table would need constant upkeep and would silently go stale,
# so this fetches Kite's own instrument master instead - the same live
# source Kite itself trades against - and caches it. Mirrors the caching
# convention in market/live.py's _resolve_tokens (module-level dict + TTL,
# refreshed lazily on the next call after expiry). One cache for everything
# Kite's dump gives us per-row, rather than a separate fetch+cache per field,
# since they all come from the exact same kite.instruments() call.
_INSTRUMENT_CACHE: dict[tuple[str, str], dict] = {}
_INSTRUMENT_CACHE_TS = 0.0
_INSTRUMENT_CACHE_TTL = 24 * 3600


def _refresh_instruments(kite) -> None:
    global _INSTRUMENT_CACHE_TS
    fresh: dict[tuple[str, str], dict] = {}
    for exch in ("NFO", "BFO"):   # NSE and BSE F&O - covers every index AND equity derivative
        try:
            dump = kite.instruments(exch)
        except Exception:
            continue
        for row in dump:
            fresh[(row["exchange"], row["tradingsymbol"])] = {
                "lot_size":        row["lot_size"],
                "strike":          row.get("strike") or None,
                "expiry":          row.get("expiry"),
                "instrument_type": row.get("instrument_type"),   # "CE" / "PE" / "FUT"
            }
    if fresh:
        _INSTRUMENT_CACHE.clear()
        _INSTRUMENT_CACHE.update(fresh)
        _INSTRUMENT_CACHE_TS = time.time()


def instrument_info(tradingsymbol: str, exchange: str, kite=None) -> dict | None:
    """Raw {lot_size, strike, expiry, instrument_type} from Kite's live
    instrument master, refreshed at most once a day. None when the symbol
    isn't found there (cash equities) or no kite session is available yet -
    callers should treat that as "not an option we can price", not guess."""
    if kite is not None and (not _INSTRUMENT_CACHE or time.time() - _INSTRUMENT_CACHE_TS >= _INSTRUMENT_CACHE_TTL):
        _refresh_instruments(kite)
    return _INSTRUMENT_CACHE.get((exchange, tradingsymbol))


def _lot_size_of(tradingsymbol: str, exchange: str, kite=None) -> int:
    """Raw lot size from Kite's live instrument master. Returns 1 (not None)
    when the symbol isn't found there (cash equities - NSE/BSE list those at
    lot_size=1 - or no kite session yet) so every lot-based formula
    downstream degrades cleanly to operating on raw quantity instead of
    needing its own fallback."""
    info = instrument_info(tradingsymbol, exchange, kite)
    return info["lot_size"] if info else 1


def lots_of(tradingsymbol: str, exchange: str, quantity: int, kite=None) -> int | None:
    """Signed lot count for a position (negative = short), or None when the
    underlying has no real lot size (cash equities) - callers should leave
    the lot count blank rather than claim "1 lot" for every single share."""
    lot_size = _lot_size_of(tradingsymbol, exchange, kite)
    if lot_size <= 1:
        return None
    return round(quantity / lot_size)


def exit_quantity(tradingsymbol: str, exchange: str, quantity: int, qty_pct: int, kite=None) -> int:
    """Signed order quantity to close for a partial-exit RM fire (negative =
    buy-to-cover a short, matching `quantity`'s own sign).

    Formula (as specified): outstanding lots x qty_pct%, rounded UP to the
    next whole lot, converted back to raw quantity - e.g. 2 lots at 25% ->
    0.5 -> ceil -> 1 lot. qty_pct >= 100 always returns `quantity` unchanged,
    bypassing lot math entirely, so every existing 100%-exit basket (the
    default) is completely unaffected by lot-size lookups or rounding.

    For a symbol with no known lot size (cash equity, or no kite session),
    `_lot_size_of` returns 1, so this degrades to rounding up a fraction of
    the raw share quantity - the same formula, just with a 1-share "lot"."""
    if qty_pct >= 100 or not quantity:
        return quantity
    lot_size = _lot_size_of(tradingsymbol, exchange, kite)
    outstanding_lots = abs(quantity) / lot_size
    exit_lots = math.ceil(outstanding_lots * qty_pct / 100)
    exit_qty = min(exit_lots * lot_size, abs(quantity))   # never exceed what's actually open
    return exit_qty if quantity > 0 else -exit_qty
