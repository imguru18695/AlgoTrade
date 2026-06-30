import sqlite3
from config import DB_FILE


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=3000")
    return conn


def init_db():
    with get_conn() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        # Safe migrations for existing DBs
        for migration in [
            "ALTER TABLE basket_rm ADD COLUMN eod_exit INTEGER DEFAULT 0",
            "ALTER TABLE baskets ADD COLUMN order_type TEXT DEFAULT 'LIMIT'",
        ]:
            try:
                conn.execute(migration)
                conn.commit()
            except Exception:
                pass

        conn.executescript("""
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

            CREATE TABLE IF NOT EXISTS basket_rm (
                basket_id       INTEGER PRIMARY KEY REFERENCES baskets(id) ON DELETE CASCADE,
                -- Profit Target
                pt_active       INTEGER DEFAULT 0,
                pt_inr          REAL,
                pt_ticks        INTEGER,
                -- Loss Guard
                lg_active       INTEGER DEFAULT 0,
                lg_inr          REAL,
                lg_ticks        INTEGER,
                -- Profit Shield
                ps_active       INTEGER DEFAULT 0,
                ps_trigger      REAL,
                ps_lock         REAL,
                ps_step_profit  REAL,
                ps_step_lock    REAL,
                -- EOD auto-exit
                eod_exit        INTEGER DEFAULT 0
            );
        """)
