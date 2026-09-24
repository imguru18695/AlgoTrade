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

STILL SIMULATED regardless of `kite`: option chain / PCR / max-pain / OI
(`_chain`), FII/DII flows, sectors, and globals — separate connections, not
yet wired. The response shape does not change either way, so the frontend
never needs to know which parts are live.
"""
from __future__ import annotations

import logging
import math
import random
from datetime import date, datetime, timedelta, timezone

from market import indicators as ind

log = logging.getLogger("market.snapshot")

IST = timezone(timedelta(hours=5, minutes=30))

_INDICES = {
    "NIFTY":  {"name": "NIFTY 50", "exchange": "NSE", "base": 23350.0, "step": 50,  "constituents": 50},
    "SENSEX": {"name": "SENSEX",   "exchange": "BSE", "base": 76890.0, "step": 100, "constituents": 30},
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
    rng = random.Random(f"{key}-{date.today().isoformat()}")
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


def _chain(key: str, step: int, spot: float) -> list[dict]:
    rng = random.Random(f"{key}-chain-{date.today().isoformat()}")
    atm = round(spot / step) * step
    strikes = []
    for i in range(-10, 11):
        k = atm + i * step
        dist = abs(i) / 10.0
        base_oi = 4_000_000 * math.exp(-dist * 2.2)
        strikes.append({
            "strike": k,
            "oi_ce": int(base_oi * rng.uniform(0.7, 1.3)),
            "oi_pe": int(base_oi * rng.uniform(0.8, 1.4)),
            "chg_ce": rng.uniform(-4, 12), "chg_pe": rng.uniform(-3, 16),
            "iv": 14 + dist * 4 + rng.uniform(-0.5, 0.5),
        })
    return strikes


# ── formatting & classification ─────────────────────────────────────────────────

def _cr(v): return f"{v / 1e7:.2f} Cr"
def _lakh(v): return f"{v / 1e5:.1f}L"
def _pct(v): return round(v, 2)

def _rsi_label(r):
    if r >= 70: return "Overbought"
    if r >= 60: return "Strong"
    if r >= 55: return "Moderately Strong"
    if r >= 45: return "Balanced"
    if r >= 30: return "Weak"
    return "Oversold"

def _pcr_label(p):
    if p >= 1.2: return "Bullish"
    if p >= 1.05: return "Bullish Range"
    if p >= 0.95: return "Neutral"
    if p >= 0.85: return "Neutral-Bearish"
    return "Bearish"

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
    d = date.today()
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

    # Series-derived spot/change (always available); a pre-fetched live quote
    # — when a session is active — overrides both with the real-time figure,
    # since it reflects intraday movement the last daily bar alone would not.
    spot = closes[-1]
    chg = (closes[-1] - closes[-2]) / closes[-2] * 100
    if live_quote:
        spot, chg = live_quote["spot"], live_quote["chg_pct"]

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

    n = cfg["constituents"]
    adv = max(0, min(n, round(n * (0.5 + chg / 4))))
    dec = n - adv
    breadth_note = "Balanced" if abs(adv - dec) <= n * 0.2 else ("Bullish" if adv > dec else "Bearish")

    above = ind.ma_above_count(closes, _MA_PERIODS)
    ma_sig = {"label": _ma_label(above, len(_MA_PERIODS)), "above": above, "total": len(_MA_PERIODS)}

    strikes = _chain(key, step, spot)
    call_tot = sum(x["oi_ce"] for x in strikes); put_tot = sum(x["oi_pe"] for x in strikes)
    oi_chg = sum(x["oi_ce"] * x["chg_ce"] + x["oi_pe"] * x["chg_pe"] for x in strikes) / (call_tot + put_tot)
    pcr = round(put_tot / call_tot, 2) if call_tot else None
    cc = max(strikes, key=lambda x: x["oi_ce"]); pc = max(strikes, key=lambda x: x["oi_pe"])
    atm_iv = round(sum(x["iv"] for x in strikes) / len(strikes), 1)

    return {
        "key": key, "name": cfg["name"], "exchange": cfg["exchange"],
        "data_source": source,
        "value": round(spot, 2), "chg_pct": round(chg, 2), "last5": last5,
        "hist_insight": _sessions_insight(last5),
        "w52": _w52(closes, spot),
        "trend": trend,
        "rsi": {"value": rsi_v, "label": _rsi_label(rsi_v)},
        "macd": {"value": macd["macd"], "state": macd["state"],
                 "label": ("Bullish Cross" if macd["state"] == "Bullish" else "Bearish Cross")},
        "sr": {"support": sup, "resistance": res, "note": sr_note},
        "breadth": {"adv": adv, "dec": dec, "note": breadth_note},
        "ma_signal": ma_sig,
        "ema": {p: round(ind.ema(closes, p)) for p in (20, 50, 100, 200)},
        "obv": ind.obv(closes, vols),
        "ad": ind.adl(highs, lows, closes, vols),
        "stoch": ind.stochastic(highs, lows, closes),
        "deriv": {
            "oi_total": _cr(call_tot + put_tot), "oi_chg_pct": round(oi_chg, 2),
            "pcr": pcr, "pcr_label": _pcr_label(pcr) if pcr else "—",
            "max_pain": ind.max_pain(strikes), "expiry": _next_expiry(True),
            "iv": atm_iv, "vix": _TICKER_EXTRA["INDIA VIX"]["base"],
            "fut_basis": round(spot * 0.0009, 2),
            "call_cluster": {"strike": cc["strike"], "contracts": _lakh(cc["oi_ce"])},
            "put_cluster": {"strike": pc["strike"], "contracts": _lakh(pc["oi_pe"])},
        },
    }


# ── market-intelligence rail (simulated) ────────────────────────────────────────

def _flows():
    rng = random.Random(f"flows-{date.today().isoformat()}")
    fii = round(rng.uniform(-2500, 3000), 2)
    dii = round(rng.uniform(-1500, 2000), 2)
    adv = rng.randint(900, 1500); dec = rng.randint(600, 1200)
    return {"fii": fii, "dii": dii, "combined": round(fii + dii, 2),
            "breadth": {"adv": adv, "dec": dec}}


def _globals():
    rng = random.Random(f"globals-{date.today().isoformat()}")
    defs = [("Gold", "$/oz", 2650.0), ("Silver", "$/oz", 30.80),
            ("Crude (Brent)", "$/bbl", 78.00), ("US 10Y", "%", 4.28)]
    out = []
    for name, unit, base in defs:
        chg = round(rng.uniform(-1.2, 1.2), 2)
        out.append({"name": name, "unit": unit, "value": round(base * (1 + chg / 100), 2), "chg_pct": chg})
    return out


def _sectors():
    rng = random.Random(f"sectors-{date.today().isoformat()}")
    names = ["Nifty IT", "Nifty Bank", "Nifty Auto", "Nifty FMCG", "Nifty Pharma", "Nifty Energy"]
    out = [{"name": nm, "chg": round(rng.uniform(-1.5, 2.0), 2)} for nm in names]
    return sorted(out, key=lambda x: -x["chg"])


def _market_status():
    now = datetime.now(IST)
    mins = now.hour * 60 + now.minute
    is_open = now.weekday() < 5 and 555 <= mins <= 930   # 09:15–15:30
    return {"state": "open" if is_open else "closed",
            "note": "Live" if is_open else "Delayed 15m",
            "as_of": now.strftime("%d %b %H:%M IST")}


def build_dashboard(kite=None) -> dict:
    """Build the dashboard snapshot. Pass an authenticated Kite client to
    fetch NIFTY/SENSEX/BANKNIFTY/INDIA VIX live; omit (or pass None, e.g. no
    active session) for the fully simulated snapshot — same response shape
    either way. Every Kite call in here is BLOCKING; callers on an event loop
    (main.py) MUST invoke this via asyncio.to_thread()."""
    # One batched quote call covers every ticker (index cards + ticker-only
    # symbols) — cheaper and avoids the cache-thrashing of N separate calls.
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
        "iv_percentile": {"value": 28, "label": "Low"},
    }
