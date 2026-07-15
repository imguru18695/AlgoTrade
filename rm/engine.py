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
MARKET_CLOSE   = (15, 29)  # stop ticks at 15:29 — NSE rejects orders at/after 15:30
EOD_EXIT_TIME  = (15, 25)
CHECK_INTERVAL = 1  # seconds

# Per-basket intraday state — auto-resets each new trading day
# basket_id → {date, floor, fired, pt_checks, lg_checks}
_state: dict[int, dict] = {}

# Strong refs to in-flight exit tasks — prevents GC between ticker ticks.
_active_fires: set[asyncio.Task] = set()


def reset_basket(basket_id: int):
    """Reset tick counters after a manual RM config save.
    Preserves floor (earned by market movement) and fired (exit already placed).
    """
    s = _state.get(basket_id)
    if s is None:
        return
    s["pt_checks"] = 0
    s["lg_checks"] = 0


def rearm_basket(basket_id: int):
    """Full state reset — clears fired, floor, and tick counters.
    Call when the user re-enters a position after a manual exit and wants
    RM protection to apply again for the rest of the trading day.
    """
    _state.pop(basket_id, None)


def get_basket_state(basket_id: int) -> dict:
    """Returns current engine state for a basket (for display/debugging)."""
    return _state.get(basket_id, {})


def _fresh_state() -> dict:
    return {
        "date":      datetime.now(IST).date(),
        "floor":     None,   # Profit Shield current floor (steps up, never down)
        "ps_armed":  False,  # True once pnl >= ps_trigger seen this day; guards overnight floor
        "fired":     False,  # True once exit orders are placed
        "pt_checks": 0,      # consecutive 5-sec checks above PT threshold
        "lg_checks": 0,      # consecutive 5-sec checks below LG threshold
    }


def _get_state(basket_id: int) -> dict:
    today = datetime.now(IST).date()
    s = _state.get(basket_id)
    if s is None:
        _state[basket_id] = _fresh_state()
    elif s["date"] != today:
        # New trading day: reset tick counters and fired flag, but preserve the
        # earned Profit Shield floor so overnight positions keep their protection.
        preserved_floor = s["floor"]
        _state[basket_id] = _fresh_state()
        _state[basket_id]["floor"] = preserved_floor
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


async def _check_basket(
    basket: dict,
    exit_fn: Callable,
    ltp_fn: Callable[[int], float | None],
    no_ltp_fn: Callable[[], None] | None,
):
    """Evaluate one basket's RM rules for a single tick. Fires exit if needed.
    Runs concurrently with other baskets — one basket's long exit does not block others.
    """
    bid       = basket["id"]
    rm        = basket.get("rm") or {}
    positions = [p for p in basket.get("positions", []) if (p.get("quantity") or 0) != 0]

    if not positions:
        return

    if not any([rm.get("pt_active"), rm.get("lg_active"),
                rm.get("ps_active"), rm.get("eod_exit")]):
        return

    # Check market hours inside each basket task so a long exit on basket N
    # doesn't allow basket N+1 to fire after the market has closed.
    if not _in_market_hours():
        return

    state = _get_state(bid)
    if state["fired"]:
        return

    pnl = compute_basket_pnl(positions, ltp_fn)
    if pnl is None:
        logger.warning(f"Basket {bid}: no live prices, skipping RM check.")
        if no_ltp_fn:
            no_ltp_fn()
        return

    logger.debug(f"Basket {bid}: live P&L = ₹{pnl:,.0f}")

    def _spawn_fire(reason: str, is_eod: bool = False):
        """Spawn _fire as a background task so this basket check returns immediately,
        allowing the engine to keep evaluating other baskets without waiting for
        order placement (which can take 5-30 s for LIMIT orders).
        _fire() sets fired=True immediately on entry, so the next tick won't re-trigger.
        pnl is captured from the enclosing scope — it's the live MTM at trigger time.
        """
        task = asyncio.create_task(
            _fire(exit_fn, bid, positions, reason, basket, eod=is_eod, mtm_at_trigger=pnl)
        )
        _active_fires.add(task)
        task.add_done_callback(_active_fires.discard)

    # ── EOD auto-exit ────────────────────────────────────────────────
    if rm.get("eod_exit") and _past_eod_time():
        _spawn_fire("EOD auto-exit at 3:25 PM", is_eod=True)
        return

    # ── Profit Target (takes priority over Profit Shield) ────────────
    if rm.get("pt_active") and rm.get("pt_inr"):
        if pnl >= rm["pt_inr"]:
            needed = rm.get("pt_ticks") or 1
            state["pt_checks"] += 1
            logger.info(f"Basket {bid}: PT check {state['pt_checks']}/{needed}, P&L=₹{pnl:,.0f}")
            if state["pt_checks"] >= needed:
                _spawn_fire(f"Profit Target ₹{rm['pt_inr']:,.0f} hit")
                return
        else:
            if state["pt_checks"] > 0:
                logger.debug(f"Basket {bid}: PT check reset (P&L dropped below target)")
            state["pt_checks"] = 0

    # ── Loss Guard ───────────────────────────────────────────────────
    if rm.get("lg_active") and rm.get("lg_inr"):
        if pnl <= -rm["lg_inr"]:
            needed = rm.get("lg_ticks") or 1
            state["lg_checks"] += 1
            logger.info(f"Basket {bid}: LG check {state['lg_checks']}/{needed}, P&L=₹{pnl:,.0f}")
            if state["lg_checks"] >= needed:
                _spawn_fire(f"Loss Guard -₹{rm['lg_inr']:,.0f} breached")
                return
        else:
            if state["lg_checks"] > 0:
                logger.debug(f"Basket {bid}: LG check reset (P&L recovered)")
            state["lg_checks"] = 0

    # ── Profit Shield ────────────────────────────────────────────────
    if rm.get("ps_active") and rm.get("ps_trigger") and rm.get("ps_lock"):
        trigger   = rm["ps_trigger"]
        base_lock = rm["ps_lock"]
        step_p    = rm.get("ps_step_profit") or 0
        step_l    = rm.get("ps_step_lock") or 0

        if pnl >= trigger:
            if state["floor"] is None:
                state["floor"] = base_lock
                logger.info(f"Basket {bid}: PS activated, floor=₹{base_lock:,.0f}")
            if not state["ps_armed"]:
                state["ps_armed"] = True
                logger.info(f"Basket {bid}: PS armed for today")

            if step_p > 0 and step_l > 0:
                steps     = int((pnl - trigger) / step_p)
                new_floor = base_lock + steps * step_l
                if new_floor > state["floor"]:
                    state["floor"] = new_floor
                    logger.info(f"Basket {bid}: PS floor stepped up to ₹{new_floor:,.0f}")

        # Only fire the floor check if PS was armed this trading day.
        # On day-2 open with an overnight preserved floor, an immediate gap-down
        # must NOT fire — the position must re-reach ps_trigger first.
        if state["ps_armed"] and state["floor"] is not None and pnl < state["floor"]:
            _spawn_fire(f"Profit Shield floor ₹{state['floor']:,.0f} breached")
            return


async def run_engine(
    get_baskets_fn: Callable,
    ltp_fn: Callable[[int], float | None],
    exit_fn: Callable[[int, list, str], None],
    no_ltp_fn: Callable[[], None] | None = None,
):
    """
    Main engine loop. Start as an asyncio background task:
        asyncio.create_task(run_engine(...))

    Each tick evaluates all baskets concurrently — one basket's long LIMIT exit
    does not delay RM evaluation for other baskets.

    Args:
        get_baskets_fn: () -> list of basket dicts, each with keys:
                         id, rm (dict), positions (list of position dicts)
        ltp_fn:         (instrument_token: int) -> float | None
        exit_fn:        async (basket_id, open_positions, reason) -> None
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

        # Fire each basket check as an independent background task so one basket's
        # multi-second LIMIT exit does not delay RM evaluation for all other baskets.
        for b in baskets:
            task = asyncio.create_task(_check_basket_safe(b, exit_fn, ltp_fn, no_ltp_fn))
            _active_fires.add(task)
            task.add_done_callback(_active_fires.discard)


async def _check_basket_safe(basket, exit_fn, ltp_fn, no_ltp_fn):
    """Wrapper that catches all exceptions so a failed basket check never silently
    kills the background task without a traceback."""
    try:
        await _check_basket(basket, exit_fn, ltp_fn, no_ltp_fn)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error("RM engine: unhandled error in basket check", exc_info=e)


async def _fire(exit_fn, basket_id, positions, reason, basket, eod: bool = False,
               mtm_at_trigger: float | None = None):
    logger.info(f"Basket {basket_id}: FIRING EXIT — {reason} | MTM=₹{mtm_at_trigger:,.0f}" if mtm_at_trigger is not None else f"Basket {basket_id}: FIRING EXIT — {reason}")

    # Set fired=True immediately — prevents the next engine tick from re-triggering
    # this basket while order placement is in progress (which can take 5-30 seconds
    # for LIMIT orders). On non-EOD failure we reset it below to allow a retry.
    current = _state.setdefault(basket_id, _fresh_state())
    current["fired"] = True

    try:
        from logs.service import create_exit_event
        basket_name = basket.get("name", f"Basket {basket_id}")
        rm_snapshot = basket.get("rm") or {}
        order_type  = basket.get("order_type", "LIMIT")
        triggered_at = datetime.now(IST).isoformat()
        event_id = await asyncio.to_thread(
            create_exit_event,
            basket_id, basket_name, triggered_at, reason, order_type, rm_snapshot,
            mtm_at_trigger,
        )
    except Exception as e:
        logger.error(f"Basket {basket_id}: failed to create exit event log: {e}")
        event_id = None

    exit_succeeded = True
    try:
        await exit_fn(basket_id, positions, reason, event_id)
    except asyncio.CancelledError:
        raise  # Let task cancellation (app shutdown) propagate cleanly
    except Exception as e:
        exit_succeeded = False
        logger.error(f"Basket {basket_id}: exit_fn failed: {e}")
        if not eod:
            # PT/LG/PS: reset fired so the engine retries on the next tick.
            # Legs that already filled show qty=0 in live positions, so _exit_one's
            # qty=0 guard prevents them from being double-exited on retry.
            s = _state.get(basket_id)
            if s:
                s["fired"] = False
            return
        # EOD: keep fired=True regardless — prevents a storm of duplicate orders
        # after 15:25. Operator must close any remaining positions manually.
        logger.error(
            f"Basket {basket_id}: EOD exit failed — fired=True to prevent duplicates. "
            f"Check exit logs and close positions manually if needed."
        )

    # Re-fetch state — rearm_basket() may have popped it while exit_fn was awaiting.
    # If popped, re-insert a fired entry so the engine doesn't double-fire on the
    # next tick against positions that are already being exited.
    current = _state.get(basket_id)
    if current is None:
        _state[basket_id] = _fresh_state()
        current = _state[basket_id]
    current["fired"] = True
    if exit_succeeded:
        logger.info(f"Basket {basket_id}: exit confirmed, fired=True")
