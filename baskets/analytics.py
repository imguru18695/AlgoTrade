"""Live Greeks, PCR, and theoretical payoff/breakeven for a basket's open
option legs.

Reuses strategies/greeks.py's Black-Scholes engine - built for the
Strategies precheck panel's hypothetical "what if I entered this" analysis -
against a basket's actual, already-open positions instead. The maths is
identical; only how the leg list is assembled differs (see _option_legs).
"""
from datetime import date, datetime, timedelta, timezone

from instruments import instrument_info
from strategies.greeks import greeks_for_leg, greeks_profile, position_payoff, position_pcr

IST = timezone(timedelta(hours=5, minutes=30))
RISK_FREE_RATE = 0.065   # matches strategies/greeks.py's own callers (demo.py's /api/precheck)


def _option_legs(positions: list[dict], kite) -> list[dict] | None:
    """Resolves each position's strike/expiry/instrument_type from Kite's
    instrument master, keeping only CE/PE legs - futures and equities have
    no Black-Scholes Greeks to speak of. None if nothing resolved (an
    all-futures/equity basket, or no kite session yet)."""
    legs = []
    for p in positions:
        info = instrument_info(p["tradingsymbol"], p["exchange"], kite)
        if not info or info["instrument_type"] not in ("CE", "PE") or not info["strike"] or not info["expiry"]:
            continue
        expiry = info["expiry"]
        if isinstance(expiry, datetime):
            expiry = expiry.date()
        elif isinstance(expiry, str):
            expiry = date.fromisoformat(expiry[:10])
        legs.append({
            "strike":        info["strike"],
            "opt_type":      info["instrument_type"],
            "quantity":      p["quantity"],                    # signed: +long, -short
            "last_price":    p.get("last_price") or 0.0,
            "average_price": abs(p.get("average_price") or 0.0),
            "expiry":        expiry,
        })
    return legs or None


def compute_basket_analytics(positions: list[dict], spot: float | None, kite=None) -> dict | None:
    """Greeks, PCR, and theoretical max-profit/loss/breakeven for a basket's
    live option legs. None if there's nothing to price (no option legs, or
    spot/kite unavailable).

    Assumes every leg shares one expiry (true for the single-underlying
    baskets this system enforces in the common case - a calendar spread
    mixing two expiries would price everything off the first leg's expiry,
    which is a known simplification, not a silent bug).
    """
    if not spot:
        return None
    legs = _option_legs(positions, kite)
    if not legs:
        return None

    today = datetime.now(IST).date()
    dte_days = max((legs[0]["expiry"] - today).days, 0)

    # Greeks: resolve the RAW (long-convention) per-unit greek via side="BUY"
    # always, then apply the position's own SIGNED quantity ourselves. Passing
    # the real side here too would double-apply the sign (once via side, once
    # via a short position's already-negative quantity). This is deliberately
    # NOT the precheck panel's "per unit" convention (which sums unweighted
    # per-leg greeks - fine there, where legs share one notional; wrong here,
    # where a live basket's legs can carry different quantities) - this gives
    # true quantity-weighted exposure instead.
    agg = {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0}
    for leg in legs:
        g = greeks_for_leg(spot, leg["strike"], dte_days, RISK_FREE_RATE,
                            leg["last_price"], leg["opt_type"], "BUY")
        for k in agg:
            agg[k] = round(agg[k] + g[k] * leg["quantity"], 2)

    # PCR reads the position's CURRENT composition: last_price, magnitude only
    # (direction doesn't matter for "how much of this basket is puts vs calls").
    pcr = position_pcr([
        {"opt_type": l["opt_type"], "price": l["last_price"], "qty": abs(l["quantity"])}
        for l in legs
    ])

    # Payoff/breakeven answer "given what I actually paid or received, what's
    # my P&L at expiry" - average_price (the real cost basis), not last_price.
    payoff = position_payoff([{
        "strike": l["strike"], "opt_type": l["opt_type"],
        "price": l["average_price"], "qty": abs(l["quantity"]),
        "side": "BUY" if l["quantity"] > 0 else "SELL",
    } for l in legs], spot, dte_days, r=RISK_FREE_RATE)

    return {
        "greeks":      agg,
        "profile":     greeks_profile(agg),
        "pcr":         pcr,
        "max_profit":  payoff["max_profit"],
        "max_loss":    payoff["max_loss"],
        "pop":         payoff["pop"],
        "net_premium": payoff["net_premium"],
        "atm_iv_pct":  payoff["atm_iv_pct"],
        "breakevens":  payoff["breakevens"],
    }
