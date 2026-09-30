"""Shared instrument-classification helpers. Used by both rm/engine.py's
Spot Range/Velocity Guards (to know which live index to check spot against)
and baskets/service.py (to enforce single-underlying-per-basket) - kept in
one place so the two can never silently drift apart on what "the same
underlying" means for a given tradingsymbol.
"""

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
