"""Add or rotate the local login account for this dashboard.

Usage:
    venv/bin/python scripts/create_login.py <username>

Prompts for the password (hidden input, not a CLI argument, so it never
lands in shell history or a process listing). Re-running for an existing
username rotates its password and clears any lockout.
"""
import getpass
import sys

sys.path.insert(0, ".")

import bcrypt

from database import get_conn, init_db


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)

    username = sys.argv[1]

    password = getpass.getpass("Password: ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Passwords don't match.")
        sys.exit(1)
    if len(password) < 12:
        print("Password must be at least 12 characters.")
        sys.exit(1)

    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    init_db()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO login_accounts (username, password_hash)
            VALUES (?, ?)
            ON CONFLICT(username) DO UPDATE SET
                password_hash = excluded.password_hash,
                is_active = 1,
                failed_attempts = 0,
                locked_until = NULL
            """,
            (username, pw_hash),
        )

    print(f"Account {username!r} created/updated.")


if __name__ == "__main__":
    main()
