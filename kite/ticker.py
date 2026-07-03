"""
Manages the KiteTicker WebSocket connection.
Maintains an in-memory LTP store that the rest of the app reads from.

Design:
- Only ONE KiteTicker instance is ever alive at a time.
- subscribe() is idempotent: creates the ticker on first call, updates the
  subscription on subsequent calls if already connected.
- on_connect re-subscribes all accumulated tokens after reconnect.
- seed_ltp() only seeds tokens not yet in the store — preserves fresher
  WebSocket data already received.
"""
import threading
import logging
from kiteconnect import KiteTicker
from config import KITE_API_KEY
from auth.token_store import load_token

logger = logging.getLogger(__name__)

# In-memory LTP store: {instrument_token: last_price}
ltp_store: dict[int, float] = {}

_ticker: KiteTicker | None = None
_lock = threading.Lock()
_subscribed_tokens: list[int] = []
_connected: bool = False


def get_ltp(instrument_token: int) -> float | None:
    return ltp_store.get(instrument_token)


def subscribe(instrument_tokens: list[int]):
    """Subscribe to LTP updates. Creates the WebSocket on first call; updates
    subscription on subsequent calls without tearing down the connection.
    """
    global _ticker, _subscribed_tokens

    auth_token = load_token()
    if not auth_token or not instrument_tokens:
        return

    with _lock:
        # Merge new tokens into accumulated set
        new_set = set(_subscribed_tokens) | set(instrument_tokens)
        _subscribed_tokens = list(new_set)

        if _ticker is None:
            _create_ticker(auth_token)
        elif _connected:
            # Already live — just update subscription in place
            try:
                _ticker.subscribe(_subscribed_tokens)
                _ticker.set_mode(_ticker.MODE_LTP, _subscribed_tokens)
            except Exception as e:
                logger.warning(f"KiteTicker: failed to update subscription: {e}")


def _create_ticker(auth_token: str):
    """Create and connect a new KiteTicker. Must be called with _lock held."""
    global _ticker, _connected

    _ticker = KiteTicker(KITE_API_KEY, auth_token)
    _connected = False

    def on_ticks(ws, ticks):
        for tick in ticks:
            ltp_store[tick["instrument_token"]] = tick.get("last_price", 0)

    def on_connect(ws, response):
        global _connected
        _connected = True
        with _lock:
            tokens = list(_subscribed_tokens)
        if tokens:
            ws.subscribe(tokens)
            ws.set_mode(ws.MODE_LTP, tokens)
        logger.info(f"KiteTicker connected, subscribed {len(tokens)} tokens")

    def on_close(ws, code, reason):
        global _connected
        _connected = False
        logger.warning(f"KiteTicker closed {code}: {reason}")

    def on_reconnect(ws, attempts_count):
        logger.warning(f"KiteTicker reconnecting, attempt {attempts_count}")

    def on_noreconnect(ws):
        logger.error("KiteTicker max reconnect attempts exceeded — manual restart required")

    def on_error(ws, code, reason):
        logger.error(f"KiteTicker error {code}: {reason}")

    _ticker.on_ticks = on_ticks
    _ticker.on_connect = on_connect
    _ticker.on_close = on_close
    _ticker.on_reconnect = on_reconnect
    _ticker.on_noreconnect = on_noreconnect
    _ticker.on_error = on_error

    _ticker.connect(threaded=True)


def seed_ltp(positions: list[dict], kite) -> None:
    """Seed ltp_store with quote API prices for tokens not yet in the store.
    Only seeds missing tokens — preserves fresher WebSocket data already received.
    Called at startup and on each background refresh, before the WebSocket has
    received its first tick for an instrument.
    """
    if not positions:
        return
    # Only fetch quotes for tokens the WebSocket hasn't yet priced
    missing = [
        p for p in positions
        if p.get("instrument_token") and p["instrument_token"] not in ltp_store
    ]
    if not missing:
        return
    token_map = {
        f"{p['exchange']}:{p['tradingsymbol']}": p["instrument_token"]
        for p in missing
    }
    try:
        quotes = kite.quote(list(token_map.keys()))
        for key, data in quotes.items():
            token = token_map.get(key)
            if token and data.get("last_price"):
                ltp_store[token] = data["last_price"]
        logger.info(f"LTP seeded for {len(token_map)} token(s) via quote API")
    except Exception as e:
        logger.warning(f"LTP seeding via quote() failed: {e}")


def stop():
    global _ticker, _connected
    with _lock:
        if _ticker:
            _ticker.close()
            _ticker = None
            _connected = False
