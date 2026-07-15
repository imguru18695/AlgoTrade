import json
from datetime import datetime, timedelta, timezone
from database import get_conn

IST = timezone(timedelta(hours=5, minutes=30))


def create_exit_event(
    basket_id: int,
    basket_name: str,
    triggered_at: str,
    trigger_reason: str,
    order_type: str,
    rm_snapshot: dict,
    mtm_at_trigger: float | None = None,
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO exit_events
                (basket_id, basket_name, triggered_at, trigger_reason, order_type, rm_snapshot, mtm_at_trigger)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (basket_id, basket_name, triggered_at, trigger_reason, order_type,
             json.dumps(rm_snapshot), mtm_at_trigger),
        )
        conn.commit()
        return cur.lastrowid


def log_exit_order(
    event_id: int,
    tradingsymbol: str,
    exchange: str,
    product: str,
    side: str,
    qty_placed: int,
    limit_price: float | None,
    order_id: str | None,
    filled_qty: int | None,
    status: str,
    attempt: int,
):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO exit_orders
                (event_id, tradingsymbol, exchange, product, side,
                 qty_placed, limit_price, order_id, filled_qty, status, attempt)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (event_id, tradingsymbol, exchange, product, side,
             qty_placed, limit_price, order_id, filled_qty, status, attempt),
        )
        conn.commit()


def get_basket_names() -> list[str]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT basket_name FROM exit_events ORDER BY basket_name"
        ).fetchall()
    return [r["basket_name"] for r in rows]


def get_logs(
    basket_name: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> list[dict]:
    conditions: list[str] = []
    params: list = []

    if basket_name:
        conditions.append("e.basket_name = ?")
        params.append(basket_name)
    if from_date:
        conditions.append("DATE(e.triggered_at) >= ?")
        params.append(from_date)
    if to_date:
        conditions.append("DATE(e.triggered_at) <= ?")
        params.append(to_date)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    with get_conn() as conn:
        events = conn.execute(
            f"SELECT * FROM exit_events e {where} ORDER BY e.triggered_at DESC",
            params,
        ).fetchall()

        result = []
        for ev in events:
            ev_dict = dict(ev)
            ev_dict["rm_snapshot"] = json.loads(ev_dict["rm_snapshot"] or "{}")
            orders = conn.execute(
                "SELECT * FROM exit_orders WHERE event_id = ? ORDER BY tradingsymbol, attempt",
                (ev_dict["id"],),
            ).fetchall()
            ev_dict["orders"] = [dict(o) for o in orders]
            result.append(ev_dict)

    return result


def clear_logs(event_ids: list[int]):
    if not event_ids:
        return
    placeholders = ",".join("?" * len(event_ids))
    with get_conn() as conn:
        conn.execute(f"DELETE FROM exit_events WHERE id IN ({placeholders})", event_ids)
        conn.commit()
