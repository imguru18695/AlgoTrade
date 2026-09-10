"""
Execution engine — places, tracks, and manages entry orders via Kite.

Order lifecycle:
  OPEN → COMPLETE / REJECTED / CANCELLED

On COMPLETE: auto-assigns the filled position to the target basket via assign_fn.
Background poller (poll_orders) syncs every 4 seconds when there are open orders.
"""
import asyncio
import logging
import time
from typing import Callable, Optional

log = logging.getLogger(__name__)

# ── In-memory order book ──────────────────────────────────────────────────────
# Persists for the lifetime of the process (session-scoped).
# Structure: order_id (str) → order record dict.
_order_book: dict[str, dict] = {}
_lock = asyncio.Lock()

# ── Constants ─────────────────────────────────────────────────────────────────
TERMINAL_STATUSES = {"COMPLETE", "REJECTED", "CANCELLED"}
POLL_INTERVAL     = 4   # seconds between Kite order-book polls


# ── Order record schema ────────────────────────────────────────────────────────

def _new_record(
    order_id:      str,
    basket_id:     Optional[int],
    basket_name:   str,
    tradingsymbol: str,
    exchange:      str,
    product:       str,
    side:          str,       # "BUY" | "SELL"
    qty:           int,
    order_type:    str,       # "LIMIT" | "MARKET" | "SL" | "SL-M"
    price:         Optional[float],
    strategy_name: str = "",
) -> dict:
    return {
        "order_id":      order_id,
        "basket_id":     basket_id,
        "basket_name":   basket_name,
        "tradingsymbol": tradingsymbol,
        "exchange":      exchange,
        "product":       product,
        "side":          side,
        "qty":           qty,
        "order_type":    order_type,
        "price":         price,
        "status":        "OPEN",
        "filled_qty":    0,
        "avg_price":     None,
        "placed_at":     time.time(),
        "strategy_name": strategy_name,
        "reject_reason": None,
    }


# ── Placement ─────────────────────────────────────────────────────────────────

async def place_leg(
    basket_id:     Optional[int],
    basket_name:   str,
    tradingsymbol: str,
    exchange:      str,
    product:       str,
    side:          str,
    qty:           int,
    order_type:    str,
    price:         Optional[float],
    strategy_name: str = "",
) -> dict:
    """Place one leg via Kite. Returns the order record on success; raises on failure."""
    from kite.client import get_kite
    kite = get_kite()

    params: dict = {
        "tradingsymbol":    tradingsymbol,
        "exchange":         exchange,
        "transaction_type": side,           # Kite uses transaction_type
        "quantity":         qty,
        "variety":          "regular",
        "order_type":       order_type,
        "product":          product,
        "validity":         "DAY",
    }
    if order_type in ("LIMIT", "SL") and price is not None:
        params["price"] = round(float(price), 2)

    result     = await asyncio.to_thread(kite.place_order, **params)
    # Kite returns {"order_id": "..."} as a dict on newer SDK versions,
    # or the bare order_id string on older ones.
    order_id   = str(result.get("order_id") if isinstance(result, dict) else result)

    rec = _new_record(order_id, basket_id, basket_name, tradingsymbol, exchange,
                      product, side, qty, order_type, price, strategy_name)
    async with _lock:
        _order_book[order_id] = rec
    log.info(f"Execution: placed {side} {qty}x {tradingsymbol} → order_id={order_id}")
    return rec


# ── Cancel / Modify ────────────────────────────────────────────────────────────

async def cancel_order(order_id: str) -> None:
    from kite.client import get_kite
    await asyncio.to_thread(get_kite().cancel_order, variety="regular", order_id=order_id)
    async with _lock:
        if order_id in _order_book:
            _order_book[order_id]["status"] = "CANCELLED"
    log.info(f"Execution: cancelled order {order_id}")


async def modify_order(order_id: str, new_price: float) -> None:
    from kite.client import get_kite
    rec = _order_book.get(order_id)
    if not rec:
        raise ValueError(f"Order {order_id} not found in book")
    if rec["status"] in TERMINAL_STATUSES:
        raise ValueError(f"Cannot modify a {rec['status']} order")
    await asyncio.to_thread(
        get_kite().modify_order,
        variety="regular",
        order_id=order_id,
        price=round(float(new_price), 2),
    )
    async with _lock:
        _order_book[order_id]["price"] = round(float(new_price), 2)
    log.info(f"Execution: modified order {order_id} → price={new_price}")


# ── Query ──────────────────────────────────────────────────────────────────────

def get_orders(active_only: bool = False) -> list[dict]:
    """Return order records, newest first."""
    orders = list(_order_book.values())
    if active_only:
        orders = [o for o in orders if o["status"] not in TERMINAL_STATUSES]
    return sorted(orders, key=lambda o: o["placed_at"], reverse=True)


def get_order(order_id: str) -> Optional[dict]:
    return _order_book.get(order_id)


# ── Background poller ──────────────────────────────────────────────────────────

async def poll_orders(assign_fn: Optional[Callable] = None) -> None:
    """
    Background task: poll Kite every POLL_INTERVAL seconds and sync status.

    assign_fn(basket_id, tradingsymbol, exchange, product) is called (as an
    asyncio task) when an order transitions to COMPLETE so the filled position
    can be auto-assigned to its basket.
    """
    while True:
        await asyncio.sleep(POLL_INTERVAL)

        # Skip polling when there are no tracked open orders
        open_orders = [o for o in _order_book.values()
                       if o["status"] not in TERMINAL_STATUSES]
        if not open_orders:
            continue

        try:
            from kite.client import get_kite
            kite_orders = await asyncio.to_thread(get_kite().orders)
            kite_map    = {str(o["order_id"]): o for o in kite_orders}
        except Exception as e:
            log.warning(f"Execution poller: failed to fetch orders: {e}")
            continue

        async with _lock:
            for oid, rec in list(_order_book.items()):
                ko = kite_map.get(oid)
                if not ko:
                    continue

                prev_status        = rec["status"]
                rec["status"]      = ko.get("status", prev_status)
                rec["filled_qty"]  = ko.get("filled_quantity", rec["filled_qty"])
                rec["avg_price"]   = ko.get("average_price") or rec["avg_price"]
                rec["reject_reason"] = ko.get("status_message")

                # Auto-assign on fresh fill
                if (rec["status"] == "COMPLETE"
                        and prev_status != "COMPLETE"
                        and assign_fn
                        and rec.get("basket_id") is not None):
                    asyncio.create_task(assign_fn(
                        rec["basket_id"],
                        rec["tradingsymbol"],
                        rec["exchange"],
                        rec["product"],
                    ))
                    log.info(
                        f"Execution: {oid} filled — auto-assigning "
                        f"{rec['tradingsymbol']} → basket {rec['basket_id']}"
                    )
