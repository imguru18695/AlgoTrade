from kiteconnect import KiteConnect
from config import KITE_API_KEY
from auth.token_store import load_token


def get_kite() -> KiteConnect:
    kite = KiteConnect(api_key=KITE_API_KEY)
    token = load_token()
    if token:
        kite.set_access_token(token)
    return kite
