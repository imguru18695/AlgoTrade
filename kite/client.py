from kiteconnect import KiteConnect
from config import KITE_API_KEY
from auth.token_store import load_token, clear_token

# Singleton KiteConnect instance — reused across all calls so the underlying
# requests.Session (and its socket pool) is never recreated, preventing fd leaks.
_kite: KiteConnect | None = None


def get_kite() -> KiteConnect:
    global _kite
    if _kite is None:
        _kite = KiteConnect(api_key=KITE_API_KEY)
        _kite.set_session_expiry_hook(clear_token)
    token = load_token()
    if token:
        _kite.set_access_token(token)
    return _kite


def reset_kite():
    """Call after logout so a fresh token gets a fresh client instance."""
    global _kite
    _kite = None
