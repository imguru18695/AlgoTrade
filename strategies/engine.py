"""
Strategy auto-execution engine.

Ticks every 60 seconds during market hours and checks all enabled templates:
  1. Not already triggered today?
  2. Entry time matches current HH:MM IST?
  3. VIX within configured range?
→ Compute strikes → Place orders → Auto-set RM

All I/O is injected (get_chain_fn, place_orders_fn, set_rm_fn, get_vix_fn)
so the same engine runs in demo and live with different backends.
"""
import asyncio
import logging
from datetime import date, datetime, time as dtime, timedelta, timezone
from typing import Callable, Optional

log = logging.getLogger(__name__)

IST          = timezone(timedelta(hours=5, minutes=30))
MARKET_OPEN  = dtime(9, 15)
MARKET_CLOSE = dtime(15, 30)
TICK_INTERVAL = 60   # seconds


# ── Helpers ───────────────────────────────────────────────────────────────────

def ist_now() -> datetime:
    return datetime.now(IST)


def is_market_hours() -> bool:
    t = ist_now().time()
    return MARKET_OPEN <= t <= MARKET_CLOSE


def expiry_for_rule(rule: str) -> str:
    """Return ISO date string for the expiry implied by rule."""
    today = date.today()
    days_to_thu = (3 - today.weekday()) % 7 or 7
    nearest = today + timedelta(days=days_to_thu)

    if rule == "nearest_weekly":
        return nearest.isoformat()

    if rule == "next_weekly":
        return (nearest + timedelta(weeks=1)).isoformat()

    if rule == "nearest_monthly":
        for delta_m in (0, 1):
            m = (today.month + delta_m - 1) % 12 + 1
            y = today.year + (today.month + delta_m - 1) // 12
            last = (date(y, m % 12 + 1, 1) - timedelta(days=1)
                    if m < 12 else date(y, 12, 31))
            while last.weekday() != 3:
                last -= timedelta(days=1)
            if last >= today:
                return last.isoformat()

    return nearest.isoformat()   # fallback


# ── Strike / leg builders ─────────────────────────────────────────────────────

def _sym(symbol: str, expiry: str, strike: int, opt_type: str) -> str:
    d = date.fromisoformat(expiry)
    return f"{symbol}{str(d.year)[2:]}{d.month}{d.day}{strike}{opt_type}"


def build_legs(strat_type: str, symbol: str, expiry: str,
               chain: dict, qty: int) -> list[dict]:
    """
    Return a list of leg dicts for the given strategy type.
    Each leg: {tradingsymbol, exchange, product, side, qty, order_type, price, strike, opt_type}
    """
    strikes = chain["strikes"]
    # Build strike → data lookup
    by_strike = {s["strike"]: s for s in strikes}

    atm  = chain["atm"]
    step = strikes[1]["strike"] - strikes[0]["strike"] if len(strikes) > 1 else 50

    atm_data = by_strike.get(atm)
    if not atm_data:
        raise ValueError(f"ATM strike {atm} not in chain")

    def leg(strike, opt_type, side):
        data = by_strike.get(strike)
        if not data:
            raise ValueError(f"Strike {strike} not found in chain")
        ltp = data[opt_type.lower()]["ltp"]
        return {
            "tradingsymbol": _sym(symbol, expiry, int(strike), opt_type),
            "exchange":      "NFO",
            "product":       "NRML",
            "side":          side,
            "qty":           qty,
            "order_type":    "LIMIT",
            "price":         ltp,
            "strike":        strike,
            "opt_type":      opt_type,
        }

    if strat_type == "short_straddle":
        return [
            leg(atm, "CE", "SELL"),
            leg(atm, "PE", "SELL"),
        ]

    if strat_type == "short_strangle":
        # Default: 2 strikes OTM on each side
        otm = 2
        return [
            leg(atm + step * otm, "CE", "SELL"),
            leg(atm - step * otm, "PE", "SELL"),
        ]

    if strat_type == "iron_condor":
        otm, wing = 2, 4
        return [
            leg(atm + step * otm,  "CE", "SELL"),
            leg(atm + step * wing, "CE", "BUY"),
            leg(atm - step * otm,  "PE", "SELL"),
            leg(atm - step * wing, "PE", "BUY"),
        ]

    if strat_type == "bull_spread":
        return [
            leg(atm,        "CE", "BUY"),
            leg(atm + step, "CE", "SELL"),
        ]

    if strat_type == "bear_spread":
        return [
            leg(atm,        "PE", "BUY"),
            leg(atm - step, "PE", "SELL"),
        ]

    raise ValueError(f"Unknown strategy type: {strat_type}")


def build_rm(tmpl: dict, total_premium: float) -> dict:
    """
    Build RM config dict from template %-of-premium settings.
    PT and LG are derived from total premium collected on SELL legs.
    """
    pt_inr = round(total_premium * (tmpl.get("pt_pct", 50)  / 100), 0)
    lg_inr = round(total_premium * (tmpl.get("lg_pct", 100) / 100), 0)

    rm = {
        "pt_active":      pt_inr > 0,
        "pt_inr":         pt_inr if pt_inr > 0 else None,
        "pt_ticks":       None,
        "lg_active":      lg_inr > 0,
        "lg_inr":         lg_inr if lg_inr > 0 else None,
        "lg_ticks":       None,
        "ps_active":      bool(tmpl.get("ps_active", False)),
        "ps_trigger":     None,
        "ps_lock":        None,
        "ps_step_profit": None,
        "ps_step_lock":   None,
        "eod_exit":       bool(tmpl.get("eod_exit", True)),
        "delete_on_fire": 1,
    }

    if rm["ps_active"]:
        if tmpl.get("ps_trigger_pct"):
            rm["ps_trigger"] = round(total_premium * tmpl["ps_trigger_pct"] / 100, 0)
        if tmpl.get("ps_lock_pct"):
            rm["ps_lock"]    = round(total_premium * tmpl["ps_lock_pct"] / 100, 0)

    return rm


def total_sell_premium(legs: list[dict]) -> float:
    return sum(l["price"] * l["qty"] for l in legs if l["side"] == "SELL")


# ── Per-template execution ────────────────────────────────────────────────────

async def execute_template(
    tmpl:             dict,
    get_chain_fn:     Callable,   # (symbol, expiry) → chain dict
    place_orders_fn:  Callable,   # async (tmpl, legs) → basket_id
    set_rm_fn:        Callable,   # (basket_id, rm_dict)
) -> int:
    """
    Execute one template: compute legs → place → set RM.
    Returns the basket_id created.
    """
    symbol   = tmpl["underlying"]
    expiry   = expiry_for_rule(tmpl.get("expiry_rule", "nearest_weekly"))
    lots     = tmpl.get("lots", 1)
    chain    = get_chain_fn(symbol, expiry)
    lot_size = chain["lot_size"]
    qty      = lots * lot_size

    legs     = build_legs(tmpl["strategy_type"], symbol, expiry, chain, qty)
    premium  = total_sell_premium(legs)
    basket_id = await place_orders_fn(tmpl, legs)
    rm        = build_rm(tmpl, premium)
    set_rm_fn(basket_id, rm)

    log.info(
        f"execute_template: '{tmpl['name']}' → basket {basket_id}, "
        f"legs={len(legs)}, premium={premium:.2f}"
    )
    return basket_id


# ── Scheduler loop ────────────────────────────────────────────────────────────

async def run_strategy_engine(
    get_templates_fn: Callable,   # () → list[dict]
    get_vix_fn:       Callable,   # () → float | None
    get_chain_fn:     Callable,   # (symbol, expiry) → chain dict
    place_orders_fn:  Callable,   # async (tmpl, legs) → basket_id
    set_rm_fn:        Callable,   # (basket_id, rm_dict)
    set_status_fn:    Callable,   # (tid, status, date_str, basket_id)
):
    log.info("Strategy scheduler started.")
    while True:
        await asyncio.sleep(TICK_INTERVAL)

        if not is_market_hours():
            continue

        now       = ist_now()
        today_str = now.strftime("%Y-%m-%d")
        now_hhmm  = now.strftime("%H:%M")

        for tmpl in get_templates_fn():
            if not tmpl.get("enabled"):
                continue
            if tmpl.get("last_triggered_date") == today_str:
                continue  # already fired today
            if tmpl.get("entry_time") != now_hhmm:
                continue  # not entry time yet

            log.info(f"Strategy scheduler: '{tmpl['name']}' (id={tmpl['id']}) — checking conditions")

            # VIX gate
            vix = get_vix_fn()
            vix_ok = _check_vix(vix, tmpl.get("vix_min"), tmpl.get("vix_max"))
            if not vix_ok:
                log.info(f"  VIX {vix} outside range [{tmpl.get('vix_min')}, {tmpl.get('vix_max')}] — skip")
                continue

            # Fire
            set_status_fn(tmpl["id"], "triggering", today_str, None)
            try:
                bid = await execute_template(tmpl, get_chain_fn, place_orders_fn, set_rm_fn)
                set_status_fn(tmpl["id"], "active", today_str, bid)
            except Exception as e:
                log.error(f"  '{tmpl['name']}' failed: {e}")
                set_status_fn(tmpl["id"], "error", today_str, None)


def _check_vix(vix: Optional[float], vix_min: Optional[float], vix_max: Optional[float]) -> bool:
    if vix is None:
        return True   # can't check → allow
    if vix_min is not None and vix < vix_min:
        return False
    if vix_max is not None and vix > vix_max:
        return False
    return True
