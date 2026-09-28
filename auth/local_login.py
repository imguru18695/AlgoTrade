"""Page-specific login for this domain — independent of convexitysystems.com's
login_accounts table by design, so this dashboard's login never depends on a
different server or database being reachable. Same bcrypt + durable-lockout
+ timing-safety shape as the convexity login, just SQLite instead of Postgres.
"""
import logging
from datetime import datetime, timedelta, timezone

import bcrypt

from database import get_conn

logger = logging.getLogger(__name__)

_DUMMY_HASH = bcrypt.hashpw(b"not-a-real-account", bcrypt.gensalt())
_MAX_ATTEMPTS = 5
_LOCKOUT_MINUTES = 15


def verify_login(username: str, password: str) -> bool:
    """True if the credentials are correct, the account is active, and it
    isn't currently locked out from prior failed attempts."""
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT id, password_hash, is_active, failed_attempts, locked_until
            FROM login_accounts WHERE username = ?
            """,
            (username,),
        ).fetchone()

        if row is None:
            bcrypt.checkpw(password.encode(), _DUMMY_HASH)
            return False

        now = datetime.now(timezone.utc)

        if not row["is_active"]:
            bcrypt.checkpw(password.encode(), _DUMMY_HASH)
            return False

        if row["locked_until"] and datetime.fromisoformat(row["locked_until"]) > now:
            bcrypt.checkpw(password.encode(), _DUMMY_HASH)
            logger.warning(f"Login blocked — account {username!r} is locked until {row['locked_until']}")
            return False

        if not bcrypt.checkpw(password.encode(), row["password_hash"].encode()):
            new_failed = row["failed_attempts"] + 1
            new_locked_until = (now + timedelta(minutes=_LOCKOUT_MINUTES)).isoformat() if new_failed >= _MAX_ATTEMPTS else None
            conn.execute(
                "UPDATE login_accounts SET failed_attempts = ?, locked_until = ? WHERE id = ?",
                (new_failed, new_locked_until, row["id"]),
            )
            if new_locked_until:
                logger.warning(f"Account {username!r} locked until {new_locked_until} after {new_failed} failed attempts")
            return False

        conn.execute(
            "UPDATE login_accounts SET failed_attempts = 0, locked_until = NULL, last_login_at = ? WHERE id = ?",
            (now.isoformat(), row["id"]),
        )
        return True
