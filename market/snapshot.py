"""
Dashboard snapshot builder.

Produces the per-index contract the Convexity dashboard consumes plus the
market-intelligence rail (FII/DII flows, sectors, breadth).

LIVE where connected: pass an authenticated `kite` client to build_dashboard()
and NIFTY/SENSEX/BANKNIFTY/INDIA VIX spot + daily history (feeding every
technical: last5, 52W, EMA/RSI/MACD/OBV/A-D/Stochastic) come from Kite
(market/live.py) — Kite covers both NSE and BSE in one session, so it is the
single source for both indices. Each index falls back to its own simulated
series independently if the live call fails, so a Kite hiccup degrades one
card, never the page. `kite=None` (e.g. demo.py, no active session) is fully
simulated, unchanged from before.

STILL NOT WIRED to any real source: option chain / PCR / max-pain / OI,
FII/DII flows, sectors, and globals — separate connections, not built yet.
Rather than simulate plausible-looking numbers for these, every field in
that category is `None` — the frontend renders that as a blank placeholder,
so nothing on screen is ever a fake number dressed up as real data.
"""
from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta, timezone

from market import indicators as ind

log = logging.getLogger("market.snapshot")

IST = timezone(timedelta(hours=5, minutes=30))

_INDICES = {
    "NIFTY":  {"name": "NIFTY 50", "exchange": "NSE", "base": 23350.0, "step": 50},
    "SENSEX": {"name": "SENSEX",   "exchange": "BSE", "base": 76890.0, "step": 100},
}
_TICKER_EXTRA = {"BANKNIFTY": {"base": 53180.0}, "INDIA VIX": {"base": 14.38}}
_MA_PERIODS = list(range(5, 101, 5))   # 20 SMAs: 5,10,…,100


def _live_or_simulated_series(key: str, cfg: dict, kite) -> tuple[dict, str]:
    """Daily OHLCV series for one index: live via Kite if a session is passed
    and the fetch succeeds, else the deterministic simulated series."""
    if kite is not None:
        try:
            from market import live as mlive
            hist = mlive.fetch_daily_history(kite, key)
        except Exception as e:
            log.warning(f"market.snapshot: live history import/call for {key} failed: {e}")
            hist = None
        if hist:
            return hist, "live"
    return _daily_series(key, cfg["base"]), "simulated"


# ── simulated series & chain ────────────────────────────────────────────────────

def _daily_series(key: str, base: float, days: int = 260) -> dict:
    rng = random.Random(f"{key}-{datetime.now(IST).date().isoformat()}")
    theta, sig = 0.015, 0.008
    frac = [1.0]
    for _ in range(days - 1):
        frac.append(frac[-1] + theta * (1.0 - frac[-1]) + rng.gauss(0, sig))
    closes = [f * base for f in frac]
    shift = base - closes[-1]
    closes = [c + shift for c in closes]
    highs, lows, vols = [], [], []
    for c in closes:
        rp = abs(rng.gauss(0, 0.004)) + 0.002
        highs.append(c * (1 + rp)); lows.append(c * (1 - rp)); vols.append(rng.uniform(0.7, 1.3) * 1e6)
    return {"close": closes, "high": highs, "low": lows, "vol": vols}


# ── formatting & classification ─────────────────────────────────────────────────

def _rsi_label(r):
    if r >= 70: return "Overbought"
    if r >= 60: return "Strong"
    if r >= 55: return "Moderately Strong"
    if r >= 45: return "Balanced"
    if r >= 30: return "Weak"
    return "Oversold"

def _ma_label(above, total):
    r = above / total
    if r >= 0.8: return "Strong Buy"
    if r >= 0.6: return "Buy"
    if r >= 0.4: return "Hold / Neutral"
    if r >= 0.2: return "Sell"
    return "Strong Sell"

def _w52(closes, spot):
    window = closes[-252:] if len(closes) >= 252 else closes
    lo, hi = min(window), max(window)
    pos = (spot - lo) / (hi - lo) * 100 if hi > lo else 50.0
    return {"low": round(lo), "high": round(hi), "pos_pct": round(pos)}


def _sessions_insight(last5):
    """One-line read of the last 5 sessions: character + stats + interpretation."""
    ups = sum(1 for v in last5 if v > 0)
    downs = sum(1 for v in last5 if v < 0)
    net = round(sum(last5), 2)
    volatile = any(abs(v) > 1.5 for v in last5)
    if ups >= 4 and net > 0:
        label, tail = "Steady uptrend", "buyers in control through the week"
    elif downs >= 4 and net < 0:
        label, tail = "Steady downtrend", "sellers pressing through the week"
    elif abs(net) < 0.5:
        label, tail = "Range-bound", "two-way action, no clear direction"
    elif net > 0:
        label, tail = "Upward drift", "mild positive bias, limited follow-through"
    else:
        label, tail = "Downward drift", "mild negative bias, limited follow-through"
    if volatile:
        tail += ", with a sharp swing session"
    tone = "up" if net > 0 else ("down" if net < 0 else "flat")
    sign = "+" if net >= 0 else "−"
    return {"label": label, "tone": tone,
            "detail": f"{ups} up / {downs} down · net {sign}{abs(net):.2f}% — {tail}"}


def _next_expiry(weekly):
    d = datetime.now(IST).date()
    if weekly:
        while d.weekday() != 1: d += timedelta(days=1)
    else:
        d = (d.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        while d.weekday() != 1: d -= timedelta(days=1)
    return d.strftime("%d %b %y")


# ── per-index block ─────────────────────────────────────────────────────────────

def _index_block(key, cfg, kite=None, live_quote=None):
    s, source = _live_or_simulated_series(key, cfg, kite)
    closes, highs, lows, vols = s["close"], s["high"], s["low"], s["vol"]
    step = cfg["step"]

    # Series-derived spot/change (always available); a live quote — when one
    # resolves — overrides both with the real-time figure, since it reflects
    # intraday movement the last daily bar alone would not. NIFTY's spot is
    # NSE data, sourced from jugaad (nseindia.com) independent of Kite, so it
    # never touches the Kite session's rate-limit budget; SENSEX (BSE, not
    # covered by jugaad) uses the pre-fetched Kite quote as before. Either
    # way, `closes[-2]` (yesterday's close) — from whichever series `source`
    # resolved to above — is what the change percentage is measured against.
    spot = closes[-1]
    chg = (closes[-1] - closes[-2]) / closes[-2] * 100
    spot_source = "simulated" if source == "simulated" else "kite-series"

    if key == "NIFTY" and kite is not None:
        # kite's presence signals "live mode" (main.py, a session is active) —
        # jugaad itself needs no credentials, but gating on it keeps demo.py
        # (kite=None) fully offline/simulated, unchanged from before.
        # Jugaad is PRIMARY (keeps Kite's budget light) but if it fails for
        # any reason, fall back to Kite's live quote — NOT silently down to
        # `closes[-1]` (the daily historical bar, cached up to 5 min and not
        # a live tick at all). That silent fallback was the actual bug behind
        # NIFTY showing a stale, non-real-time value: jugaad-data was never
        # in requirements.txt, so every call failed on the server, 100% of
        # the time, and NIFTY had no live fallback to catch it.
        from market import live_nse as mnse
        nse_spot = mnse.fetch_nifty_spot()
        if nse_spot:
            spot = nse_spot
            chg = (spot - closes[-2]) / closes[-2] * 100
            spot_source = "jugaad"
        elif live_quote:
            spot, chg = live_quote["spot"], live_quote["chg_pct"]
            spot_source = "kite"
    elif live_quote:
        spot, chg = live_quote["spot"], live_quote["chg_pct"]
        spot_source = "kite"

    last5 = [round((closes[-i] - closes[-i - 1]) / closes[-i - 1] * 100, 2) for i in range(1, 6)]

    ema20, ema50 = ind.ema(closes, 20), ind.ema(closes, 50)
    if spot >= ema20:
        trend = {"bias": "Bullish", "note": "Above 20-EMA"}
    elif spot >= ema50:
        trend = {"bias": "Neutral", "note": "Near 50-EMA"}
    else:
        trend = {"bias": "Bearish", "note": "Below 50-EMA"}

    rsi_v = round(ind.rsi(closes), 2)
    macd = ind.macd(closes)
    sup, res = ind.support_resistance(highs, lows, 20)
    sup, res = round(sup / step) * step, round(res / step) * step
    if spot - sup <= (res - sup) * 0.2:
        sr_note = "At Support"
    elif res - spot <= (res - sup) * 0.2:
        sr_note = "Near Resistance"
    else:
        sr_note = "Consolidating"

    above = ind.ma_above_count(closes, _MA_PERIODS)
    ma_sig = {"label": _ma_label(above, len(_MA_PERIODS)), "above": above, "total": len(_MA_PERIODS)}

    return {
        "key": key, "name": cfg["name"], "exchange": cfg["exchange"],
        "data_source": source, "spot_source": spot_source,
        "value": round(spot, 2), "chg_pct": round(chg, 2), "last5": last5,
        "hist_insight": _sessions_insight(last5),
        "w52": _w52(closes, spot),
        "trend": trend,
        "rsi": {"value": rsi_v, "label": _rsi_label(rsi_v)},
        "macd": {"value": macd["macd"], "state": macd["state"],
                 "label": ("Bullish Cross" if macd["state"] == "Bullish" else "Bearish Cross")},
        "sr": {"support": sup, "resistance": res, "note": sr_note},
        "ma_signal": ma_sig,
        "ema": {p: round(ind.ema(closes, p)) for p in (20, 50, 100, 200)},
        "obv": ind.obv(closes, vols),
        "ad": ind.adl(highs, lows, closes, vols),
        "stoch": ind.stochastic(highs, lows, closes),
        # Option chain / OI / PCR / max-pain / IV are not wired to any real
        # source yet (see module docstring) — None throughout rather than a
        # plausible-looking simulated number. expiry is real (pure calendar
        # math, not data), so it stays populated either way.
        "deriv": {
            "oi_total": None, "oi_chg_pct": None,
            "pcr": None, "pcr_label": None,
            "max_pain": None, "expiry": _next_expiry(True),
            "iv": None, "vix": None,
            "fut_basis": None,
            "call_cluster": None,
            "put_cluster": None,
        },
    }


# ── market-intelligence rail (not wired — None values, real category labels) ────

def _flows():
    return {"fii": None, "dii": None, "combined": None,
            "breadth": {"adv": None, "dec": None}}


def _globals():
    defs = [("Gold", "$/oz"), ("Silver", "$/oz"),
            ("Crude (Brent)", "$/bbl"), ("US 10Y", "%")]
    return [{"name": name, "unit": unit, "value": None, "chg_pct": None} for name, unit in defs]


def _sectors():
    names = ["Nifty IT", "Nifty Bank", "Nifty Auto", "Nifty FMCG", "Nifty Pharma", "Nifty Energy"]
    return [{"name": nm, "chg": None} for nm in names]


def _market_status():
    now = datetime.now(IST)
    mins = now.hour * 60 + now.minute
    is_open = now.weekday() < 5 and 555 <= mins <= 930   # 09:15–15:30
    return {"state": "open" if is_open else "closed",
            "as_of": now.strftime("%d %b %H:%M IST")}


def build_dashboard(kite=None) -> dict:
    """Build the dashboard snapshot. Pass an authenticated Kite client to
    fetch NIFTY/SENSEX/BANKNIFTY/INDIA VIX live; omit (or pass None, e.g. no
    active session) for the fully simulated snapshot — same response shape
    either way. Every Kite call in here is BLOCKING; callers on an event loop
    (main.py) MUST invoke this via asyncio.to_thread()."""
    # One batched Kite quote call covers every ticker, NIFTY included. NIFTY's
    # spot still prefers jugaad (NSE data off the Kite budget) — this Kite
    # quote is its fallback for when jugaad fails, not its primary source —
    # and including it costs nothing extra: Kite batches multiple symbols
    # into one request either way.
    live_quotes = {}
    if kite is not None:
        from market import live as mlive
        live_quotes = mlive.fetch_quotes(kite, ["NIFTY", "SENSEX", "BANKNIFTY", "INDIA VIX"])

    indices = [_index_block(k, c, kite, live_quotes.get(k)) for k, c in _INDICES.items()]
    ticker = []
    for b in indices:
        ticker.append({"sym": "NIFTY" if b["key"] == "NIFTY" else b["name"],
                       "value": b["value"], "chg_pct": b["chg_pct"]})

    # BANKNIFTY + INDIA VIX are ticker-only (no technicals card) — live quote
    # when available, simulated fallback otherwise.
    if "BANKNIFTY" in live_quotes:
        bnf_val, bnf_chg = live_quotes["BANKNIFTY"]["spot"], live_quotes["BANKNIFTY"]["chg_pct"]
    else:
        bnf_series = _daily_series("BANKNIFTY", _TICKER_EXTRA["BANKNIFTY"]["base"])["close"]
        bnf_val = round(bnf_series[-1], 2)
        bnf_chg = round((bnf_series[-1] - bnf_series[-2]) / bnf_series[-2] * 100, 2)
    if "INDIA VIX" in live_quotes:
        vix_val, vix_chg = live_quotes["INDIA VIX"]["spot"], live_quotes["INDIA VIX"]["chg_pct"]
    else:
        vix_val, vix_chg = _TICKER_EXTRA["INDIA VIX"]["base"], 2.1

    ticker.insert(2, {"sym": "BANKNIFTY", "value": bnf_val, "chg_pct": bnf_chg})
    ticker.append({"sym": "INDIA VIX", "value": vix_val, "chg_pct": vix_chg})
    return {
        "as_of": datetime.now(IST).isoformat(timespec="seconds"),
        "market_status": _market_status(),
        "ticker": ticker,
        "indices": indices,
        "globals": _globals(),
        "flows": _flows(),
        "sectors": _sectors(),
    }
