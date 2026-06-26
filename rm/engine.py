"""
RM execution engine.
Runs every 5 seconds during market hours (9:15 AM – 3:30 PM IST).
Checks each basket's live P&L against configured rules and fires exits.

Usage:
    asyncio.create_task(run_engine(get_baskets_fn, ltp_fn, exit_fn))
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Callable

logger = logging.getLogger(__name__)

IST            = timezone(timedelta(hours=5, minutes=30))
MARKET_OPEN    = (9, 15)
MARKET_CLOSE   = (15, 30)
EOD_EXIT_TIME  = (15, 25)
CHECK_INTERVAL = 5  # seconds

# Per-basket intraday state — auto-resets each new trading day
# basket_id → {date, floor, fired, pt_checks, lg_checks}
_state: dict[int, dict] = {}


def reset_basket(basket_id: int):
    """Force-reset a basket's engine state (e.g. after manual RM config save)."""
    _state.pop(basket_id, None)


def get_basket_state(basket_id: int) -> dict:
    """Returns current engine state for a basket (for display/debugging)."""
    return _state.get(basket_id, {})


def _fresh_state() -> dict:
    return {
        "date":      datetime.now(IST).date(),
        "floor":     None,   # Profit Shield current floor (steps up, never down)
        "fired":     False,  # True once exit orders are placed
        "pt_checks": 0,      # consecutive 5-sec checks above PT threshold
        "lg_checks": 0,      # consecutive 5-sec checks below LG threshold
    }


def _get_state(basket_id: int) -> dict:
    today = datetime.now(IST).date()
    s = _state.get(basket_id)
    if s is None or s["date"] != today:
        _state[basket_id] = _fresh_state()
    return _state[basket_id]


def _now_ist() -> tuple[int, int]:
    now = datetime.now(IST)
    return (now.hour, now.minute)


def _in_market_hours() -> bool:
    t = _now_ist()
    return MARKET_OPEN <= t <= MARKET_CLOSE


def _past_eod_time() -> bool:
    return _now_ist() >= EOD_EXIT_TIME


def compute_basket_pnl(
    positions: list[dict],
    ltp_fn: Callable[[int], float | None],
) -> float | None:
    """
    Returns live basket P&L using LTP from the ticker.
    Returns None if any position has no live price (ticker not connected).
    """
    total = 0.0
    for p in positions:
        ltp = ltp_fn(p.get("instrument_token", 0))
        if ltp is None:
            return None
        qty  = p["quantity"]
        avg  = p["average_price"]
        mult = p.get("multiplier", 1)
        total += (ltp - avg) * qty * mult
    return total


async def run_engine(
    get_baskets_fn: Callable,
    ltp_fn: Callable[[int], float | None],
    exit_fn: Callable[[int, list, str], None],
    no_ltp_fn: Callable[[], None] | None = None,
):
    """
    Main engine loop. Start as an asyncio background task:
        asyncio.create_task(run_engine(...))

    Args:
        get_baskets_fn: () -> list of basket dicts, each with keys:
                         id, rm (dict), positions (list of position dicts)
        ltp_fn:         (instrument_token: int) -> float | None
        exit_fn:        (basket_id, open_positions, reason) -> None
        no_ltp_fn:      optional callback when LTP is unavailable
    """
    logger.info("RM engine started.")
    while True:
        await asyncio.sleep(CHECK_INTERVAL)

        if not _in_market_hours():
            continue

        try:
            baskets = get_baskets_fn()
        except Exception as e:
            logger.error(f"RM engine: failed to get baskets: {e}")
            continue

        for basket in baskets:
            bid       = basket["id"]
            rm        = basket.get("rm") or {}
            positions = [p for p in basket.get("positions", []) if (p.get("quantity") or 0) != 0]

            if not positions:
                continue

            # Skip if no RM rules are active at all
            if not any([rm.get("pt_active"), rm.get("lg_active"),
                        rm.get("ps_active"), rm.get("eod_exit")]):
                continue

            state = _get_state(bid)
            if state["fired"]:
                continue

            # Compute live P&L
            pnl = compute_basket_pnl(positions, ltp_fn)
            if pnl is None:
                logger.warning(f"Basket {bid}: no live prices, skipping RM check.")
                if no_ltp_fn:
                    no_ltp_fn()
                continue

            logger.debug(f"Basket {bid}: live P&L = ₹{pnl:,.0f}")

            # ── EOD auto-exit ────────────────────────────────────────────────
            if rm.get("eod_exit") and _past_eod_time():
                _fire(exit_fn, bid, positions, "EOD auto-exit at 3:25 PM", state)
                continue

            # ── Profit Target (takes priority over Profit Shield) ────────────
            if rm.get("pt_active") and rm.get("pt_inr"):
                if pnl >= rm["pt_inr"]:
                    needed = rm.get("pt_ticks") or 1
                    state["pt_checks"] += 1
                    logger.info(f"Basket {bid}: PT check {state['pt_checks']}/{needed}, P&L=₹{pnl:,.0f}")
                    if state["pt_checks"] >= needed:
                        _fire(exit_fn, bid, positions,
                              f"Profit Target ₹{rm['pt_inr']:,.0f} hit", state)
                        continue
                else:
                    if state["pt_checks"] > 0:
                        logger.debug(f"Basket {bid}: PT check reset (P&L dropped below target)")
                    state["pt_checks"] = 0

            if state["fired"]:
                continue

            # ── Loss Guard ───────────────────────────────────────────────────
            if rm.get("lg_active") and rm.get("lg_inr"):
                if pnl <= -rm["lg_inr"]:
                    needed = rm.get("lg_ticks") or 1
                    state["lg_checks"] += 1
                    logger.info(f"Basket {bid}: LG check {state['lg_checks']}/{needed}, P&L=₹{pnl:,.0f}")
                    if state["lg_checks"] >= needed:
                        _fire(exit_fn, bid, positions,
                              f"Loss Guard -₹{rm['lg_inr']:,.0f} breached", state)
                        continue
                else:
                    if state["lg_checks"] > 0:
                        logger.debug(f"Basket {bid}: LG check reset (P&L recovered)")
                    state["lg_checks"] = 0

            if state["fired"]:
                continue

            # ── Profit Shield ────────────────────────────────────────────────
            if rm.get("ps_active") and rm.get("ps_trigger") and rm.get("ps_lock"):
                trigger   = rm["ps_trigger"]
                base_lock = rm["ps_lock"]
                step_p    = rm.get("ps_step_profit") or 0
                step_l    = rm.get("ps_step_lock") or 0

                if pnl >= trigger:
                    # Initialise floor on first breach
                    if state["floor"] is None:
                        state["floor"] = base_lock
                        logger.info(f"Basket {bid}: PS activated, floor=₹{base_lock:,.0f}")

                    # Step up floor (never steps down)
                    if step_p > 0 and step_l > 0:
                        steps     = int((pnl - trigger) / step_p)
                        new_floor = base_lock + steps * step_l
                        if new_floor > state["floor"]:
                            state["floor"] = new_floor
                            logger.info(f"Basket {bid}: PS floor stepped up to ₹{new_floor:,.0f}")

                    # Fire if profit drops below current floor
                    if pnl < state["floor"]:
                        _fire(exit_fn, bid, positions,
                              f"Profit Shield floor ₹{state['floor']:,.0f} breached", state)


def _fire(exit_fn, basket_id, positions, reason, state):
    logger.info(f"Basket {basket_id}: FIRING EXIT — {reason}")
    try:
        exit_fn(basket_id, positions, reason)
    except Exception as e:
        logger.error(f"Basket {basket_id}: exit_fn failed: {e}")
        return  # Don't mark fired if exit_fn threw — allows retry
    state["fired"] = True
