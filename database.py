import sqlite3
import contextlib
from config import DB_FILE


@contextlib.contextmanager
def get_conn():
    """Context manager that opens a SQLite connection, commits on success,
    rolls back on error, and ALWAYS closes the connection — releasing the
    file descriptor immediately without relying on the cyclic GC.
    """
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=3000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        # Safe migrations for existing DBs
        for migration in [
            "ALTER TABLE basket_rm ADD COLUMN eod_exit INTEGER DEFAULT 0",
            "ALTER TABLE baskets ADD COLUMN order_type TEXT DEFAULT 'LIMIT'",
            "ALTER TABLE basket_rm ADD COLUMN delete_on_fire INTEGER DEFAULT 1",
            "ALTER TABLE basket_rm ADD COLUMN spot_guard_active INTEGER DEFAULT 0",
            "ALTER TABLE basket_rm ADD COLUMN spot_lower REAL",
            "ALTER TABLE basket_rm ADD COLUMN spot_upper REAL",
            "ALTER TABLE basket_rm ADD COLUMN spot_guard_ticks INTEGER",
            "ALTER TABLE basket_rm ADD COLUMN velocity_guard_active INTEGER DEFAULT 0",
            "ALTER TABLE basket_rm ADD COLUMN velocity_pct REAL",
            "ALTER TABLE basket_rm ADD COLUMN velocity_minutes INTEGER",
            # Qty % per check (25/50/75/100) — captured for every check so a
            # partial-exit size can be configured, but NOT YET wired into
            # _fire()'s order sizing (rm/engine.py still exits 100% of the
            # basket regardless). Defaults to 100 so existing baskets keep
            # today's exact behavior until the per-check partial-exit logic
            # is specified and this is actually wired up.
            "ALTER TABLE basket_rm ADD COLUMN pt_qty_pct INTEGER DEFAULT 100",
            "ALTER TABLE basket_rm ADD COLUMN lg_qty_pct INTEGER DEFAULT 100",
            "ALTER TABLE basket_rm ADD COLUMN ps_qty_pct INTEGER DEFAULT 100",
            "ALTER TABLE basket_rm ADD COLUMN spot_guard_qty_pct INTEGER DEFAULT 100",
            "ALTER TABLE basket_rm ADD COLUMN velocity_guard_qty_pct INTEGER DEFAULT 100",
            # Profit Shield confirm-ticks — PS previously fired the instant pnl
            # dropped below the floor, no debounce at all (unlike PT/LG). Adding
            # this so it can be desensitized to a single bad print the same way.
            "ALTER TABLE basket_rm ADD COLUMN ps_ticks INTEGER",
            # Hard Exits (Not time bound) — a second, independent Target
            # Profit / Loss Guard pair, separate from the P&L Checks tab's
            # pt_*/lg_* above. Same mechanics (confirm-ticks, 100% exit).
            "ALTER TABLE basket_rm ADD COLUMN hard_pt_active INTEGER DEFAULT 0",
            "ALTER TABLE basket_rm ADD COLUMN hard_pt_inr REAL",
            "ALTER TABLE basket_rm ADD COLUMN hard_pt_ticks INTEGER",
            "ALTER TABLE basket_rm ADD COLUMN hard_pt_qty_pct INTEGER DEFAULT 100",
            "ALTER TABLE basket_rm ADD COLUMN hard_lg_active INTEGER DEFAULT 0",
            "ALTER TABLE basket_rm ADD COLUMN hard_lg_inr REAL",
            "ALTER TABLE basket_rm ADD COLUMN hard_lg_ticks INTEGER",
            "ALTER TABLE basket_rm ADD COLUMN hard_lg_qty_pct INTEGER DEFAULT 100",
        ]:
            try:
                conn.execute(migration)
                conn.commit()
            except Exception:
                pass

        # Safe migrations for log tables
        for migration in [
            "ALTER TABLE exit_events ADD COLUMN order_type TEXT DEFAULT 'LIMIT'",
            "ALTER TABLE exit_events ADD COLUMN mtm_at_trigger REAL",
            "ALTER TABLE exit_events ADD COLUMN peak_pnl REAL",
            "ALTER TABLE exit_events ADD COLUMN ps_floor_at_trigger REAL",
        ]:
            try:
                conn.execute(migration)
                conn.commit()
            except Exception:
                pass

        conn.executescript("""
            CREATE TABLE IF NOT EXISTS exit_events (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                basket_id       INTEGER NOT NULL,
                basket_name     TEXT NOT NULL,
                triggered_at    TEXT NOT NULL,
                trigger_reason  TEXT NOT NULL,
                order_type          TEXT NOT NULL DEFAULT 'LIMIT',
                rm_snapshot         TEXT NOT NULL,
                mtm_at_trigger      REAL,
                peak_pnl            REAL,
                ps_floor_at_trigger REAL
            );

            CREATE TABLE IF NOT EXISTS exit_orders (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id        INTEGER NOT NULL REFERENCES exit_events(id) ON DELETE CASCADE,
                tradingsymbol   TEXT NOT NULL,
                exchange        TEXT NOT NULL,
                product         TEXT NOT NULL,
                side            TEXT NOT NULL,
                qty_placed      INTEGER NOT NULL,
                limit_price     REAL,
                order_id        TEXT,
                filled_qty      INTEGER,
                status          TEXT,
                attempt         INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS baskets (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                order_type  TEXT DEFAULT 'LIMIT',
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS basket_positions (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                basket_id           INTEGER NOT NULL REFERENCES baskets(id) ON DELETE CASCADE,
                tradingsymbol       TEXT NOT NULL,
                exchange            TEXT NOT NULL,
                instrument_token    INTEGER,
                product             TEXT,
                UNIQUE(tradingsymbol, exchange, product)
            );

            CREATE TABLE IF NOT EXISTS login_accounts (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                username        TEXT NOT NULL UNIQUE,
                password_hash   TEXT NOT NULL,
                is_active       INTEGER NOT NULL DEFAULT 1,
                failed_attempts INTEGER NOT NULL DEFAULT 0,
                locked_until    TEXT,
                last_login_at   TEXT,
                created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS basket_rm (
                basket_id       INTEGER PRIMARY KEY REFERENCES baskets(id) ON DELETE CASCADE,
                -- Profit Target
                pt_active       INTEGER DEFAULT 0,
                pt_inr          REAL,
                pt_ticks        INTEGER,
                pt_qty_pct      INTEGER DEFAULT 100,
                -- Loss Guard
                lg_active       INTEGER DEFAULT 0,
                lg_inr          REAL,
                lg_ticks        INTEGER,
                lg_qty_pct      INTEGER DEFAULT 100,
                -- Profit Shield
                ps_active       INTEGER DEFAULT 0,
                ps_trigger      REAL,
                ps_lock         REAL,
                ps_step_profit  REAL,
                ps_step_lock    REAL,
                ps_ticks        INTEGER,
                ps_qty_pct      INTEGER DEFAULT 100,
                -- EOD auto-exit
                eod_exit        INTEGER DEFAULT 0,
                -- Auto-delete basket after RM fires
                delete_on_fire  INTEGER DEFAULT 1,
                -- Spot Range Guard
                spot_guard_active     INTEGER DEFAULT 0,
                spot_lower            REAL,
                spot_upper            REAL,
                spot_guard_ticks      INTEGER,
                spot_guard_qty_pct    INTEGER DEFAULT 100,
                -- Spot Velocity Guard
                velocity_guard_active INTEGER DEFAULT 0,
                velocity_pct          REAL,
                velocity_minutes      INTEGER,
                velocity_guard_qty_pct INTEGER DEFAULT 100,
                -- Hard Exits (Not time bound) — independent 2nd PT/LG pair
                hard_pt_active  INTEGER DEFAULT 0,
                hard_pt_inr     REAL,
                hard_pt_ticks   INTEGER,
                hard_pt_qty_pct INTEGER DEFAULT 100,
                hard_lg_active  INTEGER DEFAULT 0,
                hard_lg_inr     REAL,
                hard_lg_ticks   INTEGER,
                hard_lg_qty_pct INTEGER DEFAULT 100
            );
        """)
        conn.commit()
