from kiteconnect import KiteConnect
from config import KITE_API_KEY
from auth.token_store import load_token, clear_token

# Singleton KiteConnect instance — reused across all calls so the underlying
# requests.Session (and its socket pool) is never recreated, preventing fd leaks.
_kite: KiteConnect | None = None


def _on_session_expiry():
    """Called by KiteConnect when the server invalidates the session.
    Clears both the token file AND the singleton — otherwise subsequent get_kite()
    calls skip creation (singleton is non-None) and skip set_access_token (token is
    None), returning a client that still carries the expired token indefinitely.
    """
    clear_token()
    global _kite
    _kite = None


def get_kite() -> KiteConnect:
    global _kite
    if _kite is None:
        _kite = KiteConnect(api_key=KITE_API_KEY)
        _kite.set_session_expiry_hook(_on_session_expiry)
    token = load_token()
    if token:
        _kite.set_access_token(token)
    return _kite


def reset_kite():
    """Call after logout so a fresh token gets a fresh client instance."""
    global _kite
    _kite = None
