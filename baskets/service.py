from database import get_conn


# ── Baskets ──────────────────────────────────────────────────────────────────

def list_baskets() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT b.id, b.name, b.order_type,
                   COUNT(bp.id) AS position_count
            FROM baskets b
            LEFT JOIN basket_positions bp ON bp.basket_id = b.id
            GROUP BY b.id
            ORDER BY b.id
        """).fetchall()
    return [dict(r) for r in rows]


def create_basket(name: str) -> dict:
    with get_conn() as conn:
        cur = conn.execute("INSERT INTO baskets (name) VALUES (?)", (name,))
        basket_id = cur.lastrowid
        conn.execute("INSERT INTO basket_rm (basket_id) VALUES (?)", (basket_id,))
    return {"id": basket_id, "name": name, "order_type": "LIMIT"}


def get_order_type(basket_id: int) -> str:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT order_type FROM baskets WHERE id=?", (basket_id,)
        ).fetchone()
    return (row["order_type"] or "LIMIT") if row else "LIMIT"


def save_order_type(basket_id: int, order_type: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE baskets SET order_type=? WHERE id=?",
            (order_type if order_type in ("LIMIT", "MARKET") else "LIMIT", basket_id)
        )


def rename_basket(basket_id: int, name: str):
    with get_conn() as conn:
        conn.execute("UPDATE baskets SET name=? WHERE id=?", (name, basket_id))


def delete_basket(basket_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM baskets WHERE id=?", (basket_id,))


# ── Position assignment ───────────────────────────────────────────────────────

def assign_position(basket_id: int, tradingsymbol: str, exchange: str,
                    product: str, instrument_token: int | None):
    with get_conn() as conn:
        # Remove from any existing basket first (one basket per position rule)
        conn.execute("""
            DELETE FROM basket_positions
            WHERE tradingsymbol=? AND exchange=? AND product=?
        """, (tradingsymbol, exchange, product))
        conn.execute("""
            INSERT INTO basket_positions
                (basket_id, tradingsymbol, exchange, product, instrument_token)
            VALUES (?, ?, ?, ?, ?)
        """, (basket_id, tradingsymbol, exchange, product, instrument_token))


def unassign_position(tradingsymbol: str, exchange: str, product: str):
    with get_conn() as conn:
        conn.execute("""
            DELETE FROM basket_positions
            WHERE tradingsymbol=? AND exchange=? AND product=?
        """, (tradingsymbol, exchange, product))


def get_assigned_positions() -> dict[str, int]:
    """Returns {position_key: basket_id} for all assigned positions."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT tradingsymbol, exchange, product, basket_id FROM basket_positions"
        ).fetchall()
    return {f"{r['tradingsymbol']}|{r['exchange']}|{r['product']}": r["basket_id"]
            for r in rows}


# ── RM config ─────────────────────────────────────────────────────────────────

def get_rm(basket_id: int) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM basket_rm WHERE basket_id=?", (basket_id,)
        ).fetchone()
    return dict(row) if row else {}


def save_rm_profit_target(basket_id: int, active: bool, inr: float | None, ticks: int | None):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO basket_rm (basket_id, pt_active, pt_inr, pt_ticks)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(basket_id) DO UPDATE SET
                pt_active=excluded.pt_active,
                pt_inr=excluded.pt_inr,
                pt_ticks=excluded.pt_ticks
        """, (basket_id, int(active), inr, ticks))


def save_rm_loss_guard(basket_id: int, active: bool, inr: float | None, ticks: int | None):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO basket_rm (basket_id, lg_active, lg_inr, lg_ticks)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(basket_id) DO UPDATE SET
                lg_active=excluded.lg_active,
                lg_inr=excluded.lg_inr,
                lg_ticks=excluded.lg_ticks
        """, (basket_id, int(active), inr, ticks))


def save_eod_exit(basket_id: int, enabled: bool):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO basket_rm (basket_id, eod_exit)
            VALUES (?, ?)
            ON CONFLICT(basket_id) DO UPDATE SET eod_exit=excluded.eod_exit
        """, (basket_id, int(enabled)))


def save_rm_profit_shield(basket_id: int, active: bool, trigger: float | None,
                           lock: float | None, step_profit: float | None, step_lock: float | None):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO basket_rm (basket_id, ps_active, ps_trigger, ps_lock, ps_step_profit, ps_step_lock)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(basket_id) DO UPDATE SET
                ps_active=excluded.ps_active,
                ps_trigger=excluded.ps_trigger,
                ps_lock=excluded.ps_lock,
                ps_step_profit=excluded.ps_step_profit,
                ps_step_lock=excluded.ps_step_lock
        """, (basket_id, int(active), trigger, lock, step_profit, step_lock))
