"""
Technical indicators for the market dashboard — pure Python, no numpy/pandas.

Every function takes plain lists (oldest → newest) and returns either the latest
value or a small dict with a human-readable state. Mirrors the dependency-free
style of strategies/greeks.py so it can run anywhere the app runs.
"""
from __future__ import annotations


# ── Moving averages ────────────────────────────────────────────────────────────

def ema_series(values: list[float], period: int) -> list[float]:
    """Full EMA series, seeded with the SMA of the first `period` points."""
    if not values:
        return []
    if len(values) < period:
        period = len(values)
    k = 2.0 / (period + 1)
    seed = sum(values[:period]) / period
    out = [seed]
    for v in values[period:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def ema(values: list[float], period: int) -> float | None:
    s = ema_series(values, period)
    return s[-1] if s else None


def sma(values: list[float], period: int) -> float | None:
    if len(values) < 1:
        return None
    window = values[-period:]
    return sum(window) / len(window)


# ── RSI (Wilder) ────────────────────────────────────────────────────────────────

def rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    seed = deltas[:period]
    avg_gain = sum(d for d in seed if d > 0) / period
    avg_loss = sum(-d for d in seed if d < 0) / period
    for d in deltas[period:]:
        gain = d if d > 0 else 0.0
        loss = -d if d < 0 else 0.0
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


# ── MACD ────────────────────────────────────────────────────────────────────────

def macd(closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
    if len(closes) < slow + signal:
        return {"macd": None, "signal": None, "hist": None, "state": "—"}
    ef = ema_series(closes, fast)
    es = ema_series(closes, slow)
    n = min(len(ef), len(es))
    macd_line = [ef[-n + i] - es[-n + i] for i in range(n)]
    sig = ema_series(macd_line, signal)
    m, s = macd_line[-1], sig[-1]
    hist = m - s
    state = "Bullish" if m >= s else "Bearish"
    return {"macd": round(m, 2), "signal": round(s, 2), "hist": round(hist, 2), "state": state}


# ── Stochastic oscillator ───────────────────────────────────────────────────────

def stochastic(highs: list[float], lows: list[float], closes: list[float],
               k_period: int = 14, d_period: int = 3) -> dict:
    if len(closes) < k_period + d_period:
        return {"k": None, "d": None, "state": "—"}
    k_series: list[float] = []
    for i in range(k_period - 1, len(closes)):
        hh = max(highs[i - k_period + 1:i + 1])
        ll = min(lows[i - k_period + 1:i + 1])
        k_series.append(0.0 if hh == ll else (closes[i] - ll) / (hh - ll) * 100.0)
    k = k_series[-1]
    d = sum(k_series[-d_period:]) / d_period
    state = "Overbought" if k >= 80 else ("Oversold" if k <= 20 else "Neutral")
    return {"k": round(k, 1), "d": round(d, 1), "state": state}


# ── Volume-based (need volume; for an index feed the futures series) ─────────────

def _trend_state(series: list[float], lookback: int, up: str, down: str, flat: str = "Flat") -> str:
    if len(series) < lookback + 1:
        return flat
    a, b = series[-lookback - 1], series[-1]
    scale = max(abs(a), abs(b), 1.0)
    delta = (b - a) / scale
    if delta > 0.01:
        return up
    if delta < -0.01:
        return down
    return flat


def obv(closes: list[float], volumes: list[float], lookback: int = 10) -> dict:
    if len(closes) < 2:
        return {"value": None, "state": "—"}
    o = 0.0
    series = [0.0]
    for i in range(1, len(closes)):
        if closes[i] > closes[i - 1]:
            o += volumes[i]
        elif closes[i] < closes[i - 1]:
            o -= volumes[i]
        series.append(o)
    return {"value": round(series[-1], 0), "state": _trend_state(series, lookback, "Rising", "Falling")}


def adl(highs: list[float], lows: list[float], closes: list[float], volumes: list[float],
        lookback: int = 10) -> dict:
    """Accumulation/Distribution line."""
    if len(closes) < 2:
        return {"value": None, "state": "—"}
    a = 0.0
    series = []
    for i in range(len(closes)):
        rng = highs[i] - lows[i]
        mfm = 0.0 if rng == 0 else ((closes[i] - lows[i]) - (highs[i] - closes[i])) / rng
        a += mfm * volumes[i]
        series.append(a)
    return {"value": round(series[-1], 0),
            "state": _trend_state(series, lookback, "Accumulation", "Distribution")}


# ── Derivatives from an option chain ────────────────────────────────────────────

def pcr(chain_strikes: list[dict]) -> float | None:
    """Put-call ratio by open interest. `chain_strikes`: [{oi_ce, oi_pe, ...}]."""
    ce = sum(s.get("oi_ce", 0) for s in chain_strikes)
    pe = sum(s.get("oi_pe", 0) for s in chain_strikes)
    return round(pe / ce, 2) if ce else None


def ma_above_count(closes: list[float], periods: list[int]) -> int:
    """How many of the given SMAs the latest price sits above."""
    spot = closes[-1]
    return sum(1 for p in periods if (sma(closes, p) or 0) <= spot)


def support_resistance(highs: list[float], lows: list[float], window: int = 20) -> tuple[float, float]:
    """Nearest support/resistance from recent swing low/high."""
    lo = min(lows[-window:]) if lows else 0.0
    hi = max(highs[-window:]) if highs else 0.0
    return lo, hi


def max_pain(chain_strikes: list[dict]) -> float | None:
    """Strike that minimises total option-writer payout at expiry."""
    if not chain_strikes:
        return None
    strikes = [s["strike"] for s in chain_strikes]
    best_k, best_pay = None, None
    for k in strikes:
        pay = 0.0
        for s in chain_strikes:
            pay += s.get("oi_ce", 0) * max(0, k - s["strike"])   # call writers pay above strike
            pay += s.get("oi_pe", 0) * max(0, s["strike"] - k)   # put writers pay below strike
        if best_pay is None or pay < best_pay:
            best_pay, best_k = pay, k
    return best_k
