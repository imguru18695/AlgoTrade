from database import get_conn
from instruments import underlying_of


class MixedUnderlyingError(ValueError):
    """Raised by assign_position() when adding a leg would introduce a second,
    different index into a basket that already holds one. Only applies to
    legs that match a known index prefix — a basket of equity/commodity
    positions (no single "underlying" concept) is never subject to this."""
    def __init__(self, existing: str, attempted: str):
        self.existing = existing
        self.attempted = attempted
        super().__init__(
            f"This basket already holds {existing} positions — cannot add a {attempted} position to it."
        )


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
        conn.execute("DELETE FROM basket_positions WHERE basket_id=?", (basket_id,))
        conn.execute("DELETE FROM baskets WHERE id=?", (basket_id,))


# ── Position assignment ───────────────────────────────────────────────────────

def get_basket_underlyings(basket_id: int) -> set[str]:
    """Distinct indices currently assigned to a basket. Legs that don't match
    a known index (equity/commodity) contribute nothing — they don't
    participate in the single-underlying constraint either way."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT tradingsymbol FROM basket_positions WHERE basket_id=?", (basket_id,)
        ).fetchall()
    return {u for r in rows if (u := underlying_of(r["tradingsymbol"]))}


def assign_position(basket_id: int, tradingsymbol: str, exchange: str,
                    product: str, instrument_token: int | None):
    new_underlying = underlying_of(tradingsymbol)
    if new_underlying:
        conflicting = get_basket_underlyings(basket_id) - {new_underlying}
        if conflicting:
            raise MixedUnderlyingError(next(iter(conflicting)), new_underlying)

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


def save_rm_profit_target(basket_id: int, active: bool, inr: float | None, ticks: int | None, qty_pct: int | None = 100):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO basket_rm (basket_id, pt_active, pt_inr, pt_ticks, pt_qty_pct)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(basket_id) DO UPDATE SET
                pt_active=excluded.pt_active,
                pt_inr=excluded.pt_inr,
                pt_ticks=excluded.pt_ticks,
                pt_qty_pct=excluded.pt_qty_pct
        """, (basket_id, int(active), inr, ticks, qty_pct or 100))


def save_rm_loss_guard(basket_id: int, active: bool, inr: float | None, ticks: int | None, qty_pct: int | None = 100):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO basket_rm (basket_id, lg_active, lg_inr, lg_ticks, lg_qty_pct)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(basket_id) DO UPDATE SET
                lg_active=excluded.lg_active,
                lg_inr=excluded.lg_inr,
                lg_ticks=excluded.lg_ticks,
                lg_qty_pct=excluded.lg_qty_pct
        """, (basket_id, int(active), inr, ticks, qty_pct or 100))


def save_rm_hard_pt(basket_id: int, active: bool, inr: float | None, ticks: int | None, qty_pct: int | None = 100):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO basket_rm (basket_id, hard_pt_active, hard_pt_inr, hard_pt_ticks, hard_pt_qty_pct)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(basket_id) DO UPDATE SET
                hard_pt_active=excluded.hard_pt_active,
                hard_pt_inr=excluded.hard_pt_inr,
                hard_pt_ticks=excluded.hard_pt_ticks,
                hard_pt_qty_pct=excluded.hard_pt_qty_pct
        """, (basket_id, int(active), inr, ticks, qty_pct or 100))


def save_rm_hard_lg(basket_id: int, active: bool, inr: float | None, ticks: int | None, qty_pct: int | None = 100):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO basket_rm (basket_id, hard_lg_active, hard_lg_inr, hard_lg_ticks, hard_lg_qty_pct)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(basket_id) DO UPDATE SET
                hard_lg_active=excluded.hard_lg_active,
                hard_lg_inr=excluded.hard_lg_inr,
                hard_lg_ticks=excluded.hard_lg_ticks,
                hard_lg_qty_pct=excluded.hard_lg_qty_pct
        """, (basket_id, int(active), inr, ticks, qty_pct or 100))


def save_delete_on_fire(basket_id: int, enabled: bool):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO basket_rm (basket_id, delete_on_fire)
            VALUES (?, ?)
            ON CONFLICT(basket_id) DO UPDATE SET delete_on_fire=excluded.delete_on_fire
        """, (basket_id, int(enabled)))


def save_eod_exit(basket_id: int, enabled: bool):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO basket_rm (basket_id, eod_exit)
            VALUES (?, ?)
            ON CONFLICT(basket_id) DO UPDATE SET eod_exit=excluded.eod_exit
        """, (basket_id, int(enabled)))


def save_rm_profit_shield(basket_id: int, active: bool, trigger: float | None,
                           lock: float | None, step_profit: float | None, step_lock: float | None,
                           ticks: int | None = None, qty_pct: int | None = 100):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO basket_rm (basket_id, ps_active, ps_trigger, ps_lock, ps_step_profit, ps_step_lock, ps_ticks, ps_qty_pct)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(basket_id) DO UPDATE SET
                ps_active=excluded.ps_active,
                ps_trigger=excluded.ps_trigger,
                ps_lock=excluded.ps_lock,
                ps_step_profit=excluded.ps_step_profit,
                ps_step_lock=excluded.ps_step_lock,
                ps_ticks=excluded.ps_ticks,
                ps_qty_pct=excluded.ps_qty_pct
        """, (basket_id, int(active), trigger, lock, step_profit, step_lock, ticks, qty_pct or 100))


def save_rm_spot_guard(basket_id: int, active: bool, lower: float | None,
                        upper: float | None, ticks: int | None, qty_pct: int | None = 100):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO basket_rm (basket_id, spot_guard_active, spot_lower, spot_upper, spot_guard_ticks, spot_guard_qty_pct)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(basket_id) DO UPDATE SET
                spot_guard_active=excluded.spot_guard_active,
                spot_lower=excluded.spot_lower,
                spot_upper=excluded.spot_upper,
                spot_guard_ticks=excluded.spot_guard_ticks,
                spot_guard_qty_pct=excluded.spot_guard_qty_pct
        """, (basket_id, int(active), lower, upper, ticks, qty_pct or 100))


def save_rm_velocity_guard(basket_id: int, active: bool, pct: float | None, minutes: int | None, qty_pct: int | None = 100):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO basket_rm (basket_id, velocity_guard_active, velocity_pct, velocity_minutes, velocity_guard_qty_pct)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(basket_id) DO UPDATE SET
                velocity_guard_active=excluded.velocity_guard_active,
                velocity_pct=excluded.velocity_pct,
                velocity_minutes=excluded.velocity_minutes,
                velocity_guard_qty_pct=excluded.velocity_guard_qty_pct
        """, (basket_id, int(active), pct, minutes, qty_pct or 100))


def disable_all_rm(basket_id: int):
    """Turns off every check (PT, LG, PS, Spot Range/Velocity Guard, both
    Hard Exits, EOD) in one go, without touching any of their configured
    threshold values - a plain UPDATE rather than the upsert pattern the
    save_rm_* functions above use, since there's nothing to preserve for a
    basket that has no basket_rm row yet (nothing was active to begin with)."""
    with get_conn() as conn:
        conn.execute("""
            UPDATE basket_rm SET
                pt_active = 0,
                lg_active = 0,
                ps_active = 0,
                spot_guard_active = 0,
                velocity_guard_active = 0,
                hard_pt_active = 0,
                hard_lg_active = 0,
                eod_exit = 0
            WHERE basket_id = ?
        """, (basket_id,))
