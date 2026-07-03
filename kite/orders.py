"""
Exit order placement for RM-triggered basket exits.

Flow:
  MARKET: place_order with MARKET type + Zerodha market protection (automatic)
  LIMIT:  place_order at best bid/ask, check every 5s, cancel+replace unfilled qty
"""
import asyncio
import logging
from kite.client import get_kite
from kite.positions import fetch_positions

logger = logging.getLogger(__name__)

LIMIT_CHECK_INTERVAL = 5  # seconds between limit order fill checks
MAX_LIMIT_ATTEMPTS   = 6  # give up after 6 retries (~30 s); engine retries on next tick


def _exit_side(quantity: int) -> str:
    """SELL to exit longs, BUY to exit shorts."""
    return "SELL" if quantity > 0 else "BUY"


async def _get_best_price(kite, tradingsymbol: str, exchange: str, side: str) -> float | None:
    """
    Fetch best bid (for SELL) or best ask (for BUY) from market depth.
    Returns None if depth is unavailable.
    """
    try:
        key = f"{exchange}:{tradingsymbol}"
        quote = await asyncio.to_thread(kite.quote, [key])
        depth = quote[key]["depth"]
        if side == "SELL":
            bids = depth["buy"]
            return bids[0]["price"] if bids else None
        else:
            asks = depth["sell"]
            return asks[0]["price"] if asks else None
    except Exception as e:
        logger.error(f"Failed to fetch depth for {tradingsymbol}: {e}")
        return None


async def _fetch_live_positions() -> list:
    """Fetch Kite positions once, with one retry on empty list (transient blip guard)."""
    positions = await asyncio.to_thread(fetch_positions)
    if not positions:
        await asyncio.sleep(2)
        positions = await asyncio.to_thread(fetch_positions)
        if not positions:
            logger.warning("fetch_positions still empty after retry — treating account as flat")
    return positions or []


def _lookup_qty(live_positions: list, tradingsymbol: str, exchange: str, product: str) -> int:
    """Find current open quantity for a symbol in a pre-fetched positions list."""
    for p in live_positions:
        if (p["tradingsymbol"] == tradingsymbol and
                p["exchange"] == exchange and
                p["product"] == product):
            return p["quantity"]
    return 0


async def _get_order_status(kite, order_id: str) -> tuple[str, int]:
    """
    Returns (status, filled_qty) for a given order_id.
    Status values: COMPLETE, OPEN, CANCELLED, REJECTED, etc.
    """
    try:
        orders = await asyncio.to_thread(kite.orders)
        for o in orders:
            if str(o["order_id"]) == str(order_id):
                return o["status"], o.get("filled_quantity", 0)
    except Exception as e:
        logger.error(f"Failed to fetch order status for {order_id}: {e}")
    return "UNKNOWN", 0


async def place_exit_orders(basket_id: int, positions: list[dict], reason: str, order_type: str = "LIMIT", event_id: int | None = None):
    """
    Place exit orders for all open positions in a basket.
    Called by the RM engine when a rule triggers.

    Args:
        basket_id:  for logging
        positions:  list of position dicts from our context
        reason:     why the exit was triggered (for logging)
        order_type: "LIMIT" or "MARKET"
    """
    kite = get_kite()
    logger.info(f"Basket {basket_id}: EXIT triggered — {reason} | order_type={order_type}")

    live_positions = await _fetch_live_positions()

    tasks = [_exit_one(kite, p, order_type, basket_id, live_positions, event_id) for p in positions]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    # Re-raise CancelledError immediately so app shutdown is not swallowed.
    for r in results:
        if isinstance(r, asyncio.CancelledError):
            raise r
    errors = [r for r in results if isinstance(r, Exception)]
    if errors:
        if len(errors) == len(tasks):
            # Every leg failed — raise so _fire keeps fired=False and engine retries
            raise RuntimeError(
                f"Basket {basket_id}: all {len(tasks)} exits failed: {errors[0]}"
            )
        # Partial failure: some legs were placed, others failed.
        # Do NOT raise — _fire will set fired=True to prevent duplicate storms.
        # Any already-exited legs show qty=0 in Kite so the per-leg qty=0 guard
        # in _exit_one prevents double-exits if the engine somehow retries.
        logger.error(
            f"Basket {basket_id}: {len(errors)}/{len(tasks)} exit leg(s) failed — "
            f"fired=True will be set. Check exit logs. First error: {errors[0]}"
        )
    logger.info(f"Basket {basket_id}: exit processing complete ({len(tasks) - len(errors)}/{len(tasks)} succeeded).")


async def _exit_one(kite, position: dict, order_type: str, basket_id: int, live_positions: list, event_id: int | None = None):
    sym      = position["tradingsymbol"]
    exchange = position["exchange"]
    product  = position["product"]

    # Derive side from the live quantity fetched once before the gather.
    # A position that reversed direction since the page loaded still exits correctly.
    live_qty = _lookup_qty(live_positions, sym, exchange, product)

    if live_qty == 0:
        logger.info(f"Basket {basket_id}: {sym} qty=0 in live positions — already closed or API mismatch, skipping.")
        return

    qty  = abs(live_qty)
    side = _exit_side(live_qty)
    logger.info(f"Basket {basket_id}: exiting {sym} | side={side} qty={qty} type={order_type}")

    if order_type == "MARKET":
        await _place_market(kite, sym, exchange, product, side, qty, basket_id, event_id)
    else:
        await _place_limit_with_retry(kite, sym, exchange, product, side, qty, basket_id, event_id)


async def _place_market(kite, sym, exchange, product, side, qty, basket_id, event_id=None):
    try:
        order_id = await asyncio.to_thread(
            kite.place_order,
            variety=kite.VARIETY_REGULAR,
            exchange=exchange,
            tradingsymbol=sym,
            transaction_type=side,
            quantity=qty,
            product=product,
            order_type=kite.ORDER_TYPE_MARKET,
        )
        logger.info(f"Basket {basket_id}: MARKET order placed for {sym} | order_id={order_id}")
        if event_id is not None:
            from logs.service import log_exit_order
            await asyncio.to_thread(
                log_exit_order, event_id, sym, exchange, product,
                side, qty, None, str(order_id), None, "PLACED", 1,
            )
    except Exception as e:
        logger.error(f"Basket {basket_id}: MARKET order failed for {sym}: {e}")
        raise


async def _place_limit_with_retry(kite, sym, exchange, product, side, qty, basket_id, event_id=None):
    from logs.service import log_exit_order

    async def _log(placed_qty, price, oid, filled, status, att):
        if event_id is not None:
            await asyncio.to_thread(
                log_exit_order, event_id, sym, exchange, product,
                side, placed_qty, price, oid, filled, status, att,
            )

    remaining_qty = qty
    attempt = 0
    no_depth_checks = 0

    while remaining_qty > 0 and attempt < MAX_LIMIT_ATTEMPTS:
        placed_this_attempt = remaining_qty

        # Fetch fresh best bid/ask
        price = await _get_best_price(kite, sym, exchange, side)
        if price is None:
            no_depth_checks += 1
            logger.warning(
                f"Basket {basket_id}: no depth for {sym} (check {no_depth_checks}), waiting..."
            )
            if no_depth_checks >= MAX_LIMIT_ATTEMPTS:
                raise RuntimeError(
                    f"Basket {basket_id}: {sym} — no market depth after "
                    f"{no_depth_checks} checks; engine will retry on next tick."
                )
            await asyncio.sleep(LIMIT_CHECK_INTERVAL)
            continue
        no_depth_checks = 0  # reset whenever we get a valid price

        attempt += 1  # only counts actual order placement attempts

        # Place limit order
        order_id = None
        try:
            order_id = await asyncio.to_thread(
                kite.place_order,
                variety=kite.VARIETY_REGULAR,
                exchange=exchange,
                tradingsymbol=sym,
                transaction_type=side,
                quantity=remaining_qty,
                product=product,
                order_type=kite.ORDER_TYPE_LIMIT,
                price=price,
            )
            logger.info(f"Basket {basket_id}: LIMIT order placed for {sym} "
                        f"| qty={remaining_qty} price={price} order_id={order_id} attempt={attempt}")
        except Exception as e:
            logger.error(f"Basket {basket_id}: LIMIT order failed for {sym}: {e}")
            await asyncio.sleep(LIMIT_CHECK_INTERVAL)
            continue

        # Wait then check fill status
        await asyncio.sleep(LIMIT_CHECK_INTERVAL)
        status, filled_qty = await _get_order_status(kite, order_id)
        logger.info(f"Basket {basket_id}: {sym} order {order_id} status={status} filled={filled_qty}")

        if status == "COMPLETE":
            logger.info(f"Basket {basket_id}: {sym} fully filled.")
            await _log(placed_this_attempt, price, str(order_id), filled_qty, "COMPLETE", attempt)
            remaining_qty = 0

        elif status in ("OPEN", "TRIGGER PENDING"):
            # Attempt cancel, then always re-fetch final status.
            # The order may have filled between our status check and the cancel call —
            # re-fetching after cancel gives the true final filled qty regardless.
            try:
                await asyncio.to_thread(
                    kite.cancel_order,
                    variety=kite.VARIETY_REGULAR,
                    order_id=order_id,
                )
            except Exception as e:
                logger.warning(f"Basket {basket_id}: cancel attempt for {order_id} raised: {e} — re-fetching status anyway")
            # Always re-fetch after cancel (or failed cancel) to get true filled qty.
            final_status, final_filled = await _get_order_status(kite, order_id)
            if final_status == "UNKNOWN":
                await _log(placed_this_attempt, price, str(order_id), final_filled, "UNKNOWN", attempt)
                raise RuntimeError(
                    f"Basket {basket_id}: {sym} order {order_id} status unknown after cancel "
                    f"— aborting to prevent double-exit. Engine will retry on next tick."
                )
            unfilled = remaining_qty - final_filled
            if unfilled < 0:
                logger.critical(
                    f"Basket {basket_id}: {sym} OVERFILL detected — asked {remaining_qty}, "
                    f"got {final_filled}. Position may be over-exited. Manual review required."
                )
                remaining_qty = 0
            else:
                remaining_qty = unfilled
            await _log(placed_this_attempt, price, str(order_id), final_filled, final_status, attempt)
            logger.info(f"Basket {basket_id}: post-cancel status={final_status} "
                        f"final_filled={final_filled} unfilled={remaining_qty}, retrying...")

        elif status in ("REJECTED", "CANCELLED"):
            # Account for any partial fill before the rejection/cancellation.
            remaining_qty = max(0, remaining_qty - filled_qty)
            await _log(placed_this_attempt, price, str(order_id), filled_qty, status, attempt)
            logger.warning(f"Basket {basket_id}: order {order_id} {status} (filled={filled_qty}), remaining={remaining_qty}, retrying...")

        else:
            # UNKNOWN = order status fetch failed. Attempt a best-effort cancel to
            # prevent the original order from filling after we place a new one, then
            # abort this position — do NOT loop back and place another order, as that
            # risks a double-exit if the original was actually COMPLETE.
            logger.warning(f"Basket {basket_id}: unknown status for {order_id}, attempting cancel then aborting...")
            try:
                await asyncio.to_thread(
                    kite.cancel_order, variety=kite.VARIETY_REGULAR, order_id=order_id
                )
            except Exception:
                pass  # Best-effort — order may already be filled or not exist
            await _log(placed_this_attempt, price, str(order_id), 0, "UNKNOWN", attempt)
            raise RuntimeError(
                f"Basket {basket_id}: {sym} order {order_id} status unknown at attempt {attempt} "
                f"— aborting to prevent double-exit. Engine will retry on next tick."
            )

    if remaining_qty > 0:
        raise RuntimeError(
            f"Basket {basket_id}: {sym} still has {remaining_qty} unfilled after "
            f"{attempt} attempts — engine will retry on next tick."
        )
