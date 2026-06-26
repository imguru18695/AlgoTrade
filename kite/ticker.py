"""
Manages the KiteTicker WebSocket connection.
Maintains an in-memory LTP store that the rest of the app reads from.
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


def get_ltp(instrument_token: int) -> float | None:
    return ltp_store.get(instrument_token)


def subscribe(instrument_tokens: list[int]):
    global _ticker

    token = load_token()
    if not token or not instrument_tokens:
        return

    with _lock:
        if _ticker is not None:
            try:
                _ticker.close()
            except Exception:
                pass

        _ticker = KiteTicker(KITE_API_KEY, token)

        def on_ticks(ws, ticks):
            for tick in ticks:
                ltp_store[tick["instrument_token"]] = tick.get("last_price", 0)

        def on_connect(ws, response):
            ws.subscribe(instrument_tokens)
            ws.set_mode(ws.MODE_LTP, instrument_tokens)

        def on_error(ws, code, reason):
            logger.error(f"KiteTicker error {code}: {reason}")

        def on_close(ws, code, reason):
            logger.warning(f"KiteTicker closed {code}: {reason}")

        _ticker.on_ticks = on_ticks
        _ticker.on_connect = on_connect
        _ticker.on_error = on_error
        _ticker.on_close = on_close

        # Runs in a background thread
        _ticker.connect(threaded=True)


def stop():
    global _ticker
    with _lock:
        if _ticker:
            _ticker.close()
            _ticker = None
