"""
Live Kite Connect data connection for the market dashboard.

Kite covers both NSE and BSE through one authenticated session, so it is the
single live source for NIFTY (NSE) and SENSEX (BSE) — no separate NSE/BSE
integration needed. Every call here is defensive: wrapped in try/except,
returns None on any failure so market/snapshot.py falls back to simulated
data per-index rather than risking the live trading app (this module runs
inside main.py's process, alongside the RM engine).

All Kite SDK calls are BLOCKING (kiteconnect-python uses `requests`) — callers
MUST invoke these through asyncio.to_thread(), same convention as the rest of
main.py (see _refresh_cache). Nothing in this module is async on its own.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

# EC2 runs in UTC (confirmed via `timedatectl`), not IST — date.today() would
# be a full calendar day behind IST during IST's 00:00-05:30 window (UTC
# 18:30-23:59 the previous day), silently fetching Kite history one day
# stale for anyone checking the dashboard in the evening/night. Always derive
# "today" from IST explicitly, never from the server's local clock.
IST = timezone(timedelta(hours=5, minutes=30))

log = logging.getLogger("market.live")

# "EXCHANGE:TRADINGSYMBOL" keys Kite's quote() accepts directly for indices —
# no instrument_token lookup needed for a live quote.
_QUOTE_KEYS = {
    "NIFTY":     "NSE:NIFTY 50",
    "SENSEX":    "BSE:SENSEX",
    "BANKNIFTY": "NSE:NIFTY BANK",
    "INDIA VIX": "NSE:INDIA VIX",
}

# (exchange, tradingsymbol) to resolve instrument_token for historical_data,
# which needs a numeric token rather than the quote()-style string key.
_INDEX_LOOKUP = {
    "NIFTY":  ("NSE", "NIFTY 50"),
    "SENSEX": ("BSE", "SENSEX"),
}

# ── Caches (module-level, process-lifetime) ──────────────────────────────────
# Instrument tokens barely ever change — cache for a day. Daily history only
# adds one new bar per session — a few minutes is plenty fresh and keeps us
# well under Kite's historical-data rate limits. Quotes are cheap and the
# thing we most want fresh, so a short TTL.
_TOKEN_CACHE: dict[str, int] = {}
_TOKEN_CACHE_TS = 0.0
_TOKEN_CACHE_TTL = 24 * 3600

_HISTORY_CACHE: dict[str, tuple[float, dict]] = {}
_HISTORY_CACHE_TTL = 300

_QUOTE_CACHE: tuple[float, dict] | None = None
_QUOTE_CACHE_TTL = 15


def _resolve_tokens(kite) -> dict[str, int]:
    global _TOKEN_CACHE_TS
    now = time.time()
    if _TOKEN_CACHE and now - _TOKEN_CACHE_TS < _TOKEN_CACHE_TTL:
        return _TOKEN_CACHE
    resolved: dict[str, int] = {}
    for exch in ("NSE", "BSE"):
        wanted = {sym: ts for sym, (e, ts) in _INDEX_LOOKUP.items() if e == exch}
        if not wanted:
            continue
        try:
            dump = kite.instruments(exch)
        except Exception as e:
            log.warning(f"market.live: instruments({exch}) failed: {e}")
            continue
        by_symbol = {row["tradingsymbol"]: row["instrument_token"] for row in dump}
        for sym, ts in wanted.items():
            if ts in by_symbol:
                resolved[sym] = by_symbol[ts]
    if resolved:
        _TOKEN_CACHE.update(resolved)
        _TOKEN_CACHE_TS = now
    return _TOKEN_CACHE


def fetch_quotes(kite, keys: list[str]) -> dict[str, dict]:
    """Live spot + previous close for the given ticker keys.

    Fetches only the keys not already cached, merging into the shared cache
    (never overwrites it) — safe to call with a different key subset each
    time, e.g. once per index plus once for the ticker-only symbols, within
    the same TTL window without evicting each other.

    Returns {key: {"spot", "prev_close", "chg_pct"}} — only for keys that
    resolved successfully; missing keys mean the caller should fall back.
    """
    global _QUOTE_CACHE
    now = time.time()
    if _QUOTE_CACHE is None or now - _QUOTE_CACHE[0] >= _QUOTE_CACHE_TTL:
        _QUOTE_CACHE = (now, {})
    ts, cached = _QUOTE_CACHE

    missing = [k for k in keys if k in _QUOTE_KEYS and k not in cached]
    if missing:
        q_keys = {k: _QUOTE_KEYS[k] for k in missing}
        try:
            data = kite.quote(list(q_keys.values()))
        except Exception as e:
            log.warning(f"market.live: quote({list(q_keys.values())}) failed: {e}")
            data = {}
        for key, q_key in q_keys.items():
            row = data.get(q_key)
            if not row:
                continue
            spot = row.get("last_price")
            prev_close = (row.get("ohlc") or {}).get("close")
            if spot is None or not prev_close:
                continue
            cached[key] = {
                "spot": spot, "prev_close": prev_close,
                "chg_pct": round((spot - prev_close) / prev_close * 100, 2),
            }
        _QUOTE_CACHE = (ts, cached)

    return {k: cached[k] for k in keys if k in cached}


def fetch_daily_history(kite, key: str, days: int = 260) -> dict | None:
    """Daily OHLCV bars for one index, via Kite historical_data (needs the
    historical-data add-on). Returns {"close","high","low","vol"} lists,
    oldest -> newest, or None on any failure / missing token."""
    now = time.time()
    cached = _HISTORY_CACHE.get(key)
    if cached and now - cached[0] < _HISTORY_CACHE_TTL:
        return cached[1]

    tokens = _resolve_tokens(kite)
    token = tokens.get(key)
    if not token:
        return None

    to_d = datetime.now(IST).date()
    from_d = to_d - timedelta(days=int(days * 1.6))   # pad for weekends/holidays
    try:
        bars = kite.historical_data(token, from_d, to_d, "day")
    except Exception as e:
        log.warning(f"market.live: historical_data({key}) failed: {e}")
        return None
    if not bars or len(bars) < 60:   # sanity floor — too little history to trust
        return None

    bars = bars[-days:]
    result = {
        "close": [b["close"] for b in bars],
        "high":  [b["high"] for b in bars],
        "low":   [b["low"] for b in bars],
        "vol":   [b["volume"] for b in bars],
    }
    _HISTORY_CACHE[key] = (now, result)
    return result
