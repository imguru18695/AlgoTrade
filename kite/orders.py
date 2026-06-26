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

LIMIT_CHECK_INTERVAL = 5   # seconds between limit order fill checks
MAX_LIMIT_ATTEMPTS   = 20  # give up after 20 retries (~100 seconds)


def _exit_side(quantity: int) -> str:
    """SELL to exit longs, BUY to exit shorts."""
    return "SELL" if quantity > 0 else "BUY"


def _get_best_price(kite, tradingsymbol: str, exchange: str, side: str) -> float | None:
    """
    Fetch best bid (for SELL) or best ask (for BUY) from market depth.
    Returns None if depth is unavailable.
    """
    try:
        key = f"{exchange}:{tradingsymbol}"
        quote = kite.quote([key])
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


def _live_qty(tradingsymbol: str, exchange: str, product: str) -> int:
    """Fetch current open quantity from Kite (pre-exit verification)."""
    try:
        positions = fetch_positions()
        for p in positions:
            if (p["tradingsymbol"] == tradingsymbol and
                    p["exchange"] == exchange and
                    p["product"] == product):
                return p["quantity"]
    except Exception as e:
        logger.error(f"Failed to verify live qty for {tradingsymbol}: {e}")
    return 0


def _get_order_status(kite, order_id: str) -> tuple[str, int]:
    """
    Returns (status, filled_qty) for a given order_id.
    Status values: COMPLETE, OPEN, CANCELLED, REJECTED, etc.
    """
    try:
        orders = kite.orders()
        for o in orders:
            if str(o["order_id"]) == str(order_id):
                return o["status"], o.get("filled_quantity", 0)
    except Exception as e:
        logger.error(f"Failed to fetch order status for {order_id}: {e}")
    return "UNKNOWN", 0


async def place_exit_orders(basket_id: int, positions: list[dict], reason: str, order_type: str = "LIMIT"):
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

    tasks = [
        _exit_one(kite, p, order_type, basket_id)
        for p in positions
    ]
    await asyncio.gather(*tasks)
    logger.info(f"Basket {basket_id}: all exit orders processed.")


async def _exit_one(kite, position: dict, order_type: str, basket_id: int):
    sym      = position["tradingsymbol"]
    exchange = position["exchange"]
    product  = position["product"]
    side     = _exit_side(position["quantity"])

    # Pre-exit verification — confirm position is still open in Kite
    live_qty = _live_qty(sym, exchange, product)
    if live_qty == 0:
        logger.info(f"Basket {basket_id}: {sym} already closed in Kite, skipping.")
        return

    qty = abs(live_qty)
    logger.info(f"Basket {basket_id}: exiting {sym} | side={side} qty={qty} type={order_type}")

    if order_type == "MARKET":
        await _place_market(kite, sym, exchange, product, side, qty, basket_id)
    else:
        await _place_limit_with_retry(kite, sym, exchange, product, side, qty, basket_id)


async def _place_market(kite, sym, exchange, product, side, qty, basket_id):
    try:
        order_id = kite.place_order(
            variety=kite.VARIETY_REGULAR,
            exchange=exchange,
            tradingsymbol=sym,
            transaction_type=side,
            quantity=qty,
            product=product,
            order_type=kite.ORDER_TYPE_MARKET,
        )
        logger.info(f"Basket {basket_id}: MARKET order placed for {sym} | order_id={order_id}")
    except Exception as e:
        logger.error(f"Basket {basket_id}: MARKET order failed for {sym}: {e}")


async def _place_limit_with_retry(kite, sym, exchange, product, side, qty, basket_id):
    remaining_qty = qty
    attempt = 0

    while remaining_qty > 0 and attempt < MAX_LIMIT_ATTEMPTS:
        attempt += 1

        # Fetch fresh best bid/ask
        price = _get_best_price(kite, sym, exchange, side)
        if price is None:
            logger.warning(f"Basket {basket_id}: no depth for {sym}, waiting 5s...")
            await asyncio.sleep(LIMIT_CHECK_INTERVAL)
            continue

        # Place limit order
        order_id = None
        try:
            order_id = kite.place_order(
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
        status, filled_qty = _get_order_status(kite, order_id)
        logger.info(f"Basket {basket_id}: {sym} order {order_id} status={status} filled={filled_qty}")

        if status == "COMPLETE":
            logger.info(f"Basket {basket_id}: {sym} fully filled.")
            remaining_qty = 0

        elif status in ("OPEN", "TRIGGER PENDING"):
            # Cancel and retry with updated price for unfilled quantity
            unfilled = remaining_qty - filled_qty
            try:
                kite.cancel_order(variety=kite.VARIETY_REGULAR, order_id=order_id)
                logger.info(f"Basket {basket_id}: cancelled {order_id}, unfilled={unfilled}, retrying...")
            except Exception as e:
                logger.error(f"Basket {basket_id}: cancel failed for {order_id}: {e}")
            remaining_qty = unfilled

        elif status in ("REJECTED", "CANCELLED"):
            logger.warning(f"Basket {basket_id}: order {order_id} {status}, retrying...")

        else:
            logger.warning(f"Basket {basket_id}: unexpected status {status} for {order_id}")

    if remaining_qty > 0:
        logger.error(f"Basket {basket_id}: {sym} still has {remaining_qty} unfilled after "
                     f"{attempt} attempts. Manual intervention required.")
