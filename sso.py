"""Minimal signed-token handoff between convexitysystems.com's login and
each trading account's own app. Not a general session framework — just
enough to prove "this visitor just passed the convexitysystems.com login
for account X" without either side needing to share a database or call
the other's API synchronously.

Token shape (base64url of "account:expiry:signature"):
  - account: which login (e.g. "neeraja") this token vouches for
  - expiry: unix timestamp after which the token is dead
  - signature: HMAC-SHA256 over "account:expiry" using SSO_SHARED_SECRET,
    the one value that must match exactly across every system involved

Used two ways with different lifetimes: a short-lived (~90s) token in the
login redirect URL, and a longer-lived one re-issued as a session cookie
by the receiving app so the visitor doesn't have to redo this every click.
"""
import base64
import hashlib
import hmac
import os
import time

from dotenv import load_dotenv

# Self-sufficient regardless of import order or where else load_dotenv() is
# called — this module needs SSO_SHARED_SECRET at import time, so it can't
# depend on some other module happening to load .env first.
load_dotenv()

_SECRET = os.environ["SSO_SHARED_SECRET"].encode()


def _sign(payload: str) -> str:
    return hmac.new(_SECRET, payload.encode(), hashlib.sha256).hexdigest()


def make_token(account: str, ttl_seconds: int) -> str:
    expiry = int(time.time()) + ttl_seconds
    payload = f"{account}:{expiry}"
    raw = f"{payload}:{_sign(payload)}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def verify_token(token: str) -> str | None:
    """Returns the account name if the token is validly signed and not
    expired, else None. Never raises on malformed input."""
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        account, expiry_str, sig = raw.rsplit(":", 2)
        expiry = int(expiry_str)
    except Exception:
        return None
    if not hmac.compare_digest(sig, _sign(f"{account}:{expiry}")):
        return None
    if time.time() > expiry:
        return None
    return account
