"""
Dashboard snapshot builder.

Produces the exact per-index contract the Convexity dashboard consumes. Data is
REAL-SHAPED but SIMULATED for now: a deterministic daily OHLCV series (seeded by
index + date, so it is stable within a trading day) feeds market.indicators, and
a simulated option chain feeds the derivatives block.

Swapping to live data later means replacing `_daily_series` (→ Kite historical /
jugaad daily bars) and `_chain` (→ NSELive index_option_chain) — the returned
shape, and therefore the frontend, does not change.
"""
from __future__ import annotations

import math
import random
from datetime import date, datetime, timedelta, timezone

from market import indicators as ind

IST = timezone(timedelta(hours=5, minutes=30))

# base level, exchange, per-strike step, lot size
_INDICES = {
    "NIFTY":  {"name": "NIFTY 50", "exchange": "NSE", "base": 23350.0, "step": 50,  "lot": 75},
    "SENSEX": {"name": "SENSEX",   "exchange": "BSE", "base": 76890.0, "step": 100, "lot": 20},
}
_VIX = {"value": 14.38, "chg_pct": -2.42}


def _daily_series(key: str, cfg: dict, days: int = 260) -> dict:
    """Deterministic simulated daily OHLCV ending at ~cfg['base'].

    Mean-reverting (Ornstein-Uhlenbeck) around the base level, so the 52-week
    range stays realistic (~±10%) instead of drifting like a pure random walk.
    """
    rng = random.Random(f"{key}-{date.today().isoformat()}")
    base = cfg["base"]
    theta, sig = 0.015, 0.008          # pull strength, daily fractional vol
    frac = [1.0]
    for _ in range(days - 1):
        frac.append(frac[-1] + theta * (1.0 - frac[-1]) + rng.gauss(0, sig))
    closes = [f * base for f in frac]
    # small parallel-shift so the final close lands exactly on base
    shift = base - closes[-1]
    closes = [c + shift for c in closes]
    highs, lows, vols = [], [], []
    for c in closes:
        rngpct = abs(rng.gauss(0, 0.004)) + 0.002
        hi = c * (1 + rngpct)
        lo = c * (1 - rngpct)
        highs.append(hi)
        lows.append(lo)
        vols.append(rng.uniform(0.7, 1.3) * 1_000_000)
    return {"close": closes, "high": highs, "low": lows, "vol": vols}


def _chain(key: str, cfg: dict, spot: float) -> list[dict]:
    """Simulated option chain around spot for PCR / max-pain / OI."""
    rng = random.Random(f"{key}-chain-{date.today().isoformat()}")
    step = cfg["step"]
    atm = round(spot / step) * step
    strikes = []
    for i in range(-10, 11):
        k = atm + i * step
        dist = abs(i) / 10.0
        base_oi = 4_000_000 * math.exp(-dist * 2.2)
        oi_ce = int(base_oi * rng.uniform(0.7, 1.3))
        oi_pe = int(base_oi * rng.uniform(0.8, 1.4))   # slight put skew → PCR > 1
        strikes.append({
            "strike": k, "oi_ce": oi_ce, "oi_pe": oi_pe,
            "chg_ce": int(oi_ce * rng.uniform(-0.05, 0.15)),
            "chg_pe": int(oi_pe * rng.uniform(-0.03, 0.20)),
        })
    return strikes


def _fmt_cr(v: float) -> str:
    return f"{v / 1e7:.2f} Cr"


def _next_expiry(weekly: bool) -> str:
    """Next Tue (weekly) / last Tue of month (monthly), as 'DD Mon YY'."""
    d = date.today()
    if weekly:
        while d.weekday() != 1:        # Tuesday
            d += timedelta(days=1)
    else:
        d = (d.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        while d.weekday() != 1:
            d -= timedelta(days=1)
    return d.strftime("%d %b %y")


def _index_block(key: str, cfg: dict) -> dict:
    s = _daily_series(key, cfg)
    closes, highs, lows, vols = s["close"], s["high"], s["low"], s["vol"]
    spot = closes[-1]
    chg_pct = (closes[-1] - closes[-2]) / closes[-2] * 100

    last5 = [round((closes[-i] - closes[-i - 1]) / closes[-i - 1] * 100, 2) for i in range(1, 6)]

    w52 = closes[-252:] if len(closes) >= 252 else closes
    lo52, hi52 = min(w52), max(w52)
    pos = (spot - lo52) / (hi52 - lo52) * 100 if hi52 > lo52 else 50.0

    strikes = _chain(key, cfg, spot)
    call_tot = sum(x["oi_ce"] for x in strikes)
    put_tot = sum(x["oi_pe"] for x in strikes)
    call_chg = sum(x["chg_ce"] for x in strikes)
    put_chg = sum(x["chg_pe"] for x in strikes)

    return {
        "key": key,
        "name": cfg["name"],
        "exchange": cfg["exchange"],
        "value": round(spot, 2),
        "chg_pct": round(chg_pct, 2),
        "last5": last5,                                   # T-1 … T-5, most recent first
        "w52": {"low": round(lo52), "high": round(hi52), "pos_pct": round(pos)},
        "ema": {p: round(ind.ema(closes, p)) for p in (20, 50, 100, 200)},
        "rsi": round(ind.rsi(closes), 1),
        "macd": ind.macd(closes),
        "obv": ind.obv(closes, vols),
        "ad": ind.adl(highs, lows, closes, vols),
        "stoch": ind.stochastic(highs, lows, closes),
        "futures": {"expiry": _next_expiry(False),
                    "value": round(spot * 1.0009, 2),
                    "chg_pct": round(chg_pct + 0.05, 2)},
        "options": {"expiry": _next_expiry(True),
                    "pcr": ind.pcr(strikes),
                    "max_pain": ind.max_pain(strikes)},
        "oi": {"call_total": _fmt_cr(call_tot), "put_total": _fmt_cr(put_tot),
               "call_chg_pct": round(call_chg / call_tot * 100, 1) if call_tot else 0.0,
               "put_chg_pct": round(put_chg / put_tot * 100, 1) if put_tot else 0.0},
    }


def build_dashboard() -> dict:
    indices = [_index_block(k, c) for k, c in _INDICES.items()]
    ticker = [{"sym": b["name"] if b["key"] != "NIFTY" else "NIFTY",
               "value": b["value"], "chg_pct": b["chg_pct"]} for b in indices]
    ticker.append({"sym": "INDIA VIX", "value": _VIX["value"], "chg_pct": _VIX["chg_pct"]})
    return {
        "as_of": datetime.now(IST).isoformat(timespec="seconds"),
        "indices": indices,
        "ticker": ticker,
        "iv_percentile": {"value": 28, "label": "Low"},
    }
