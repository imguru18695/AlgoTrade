"""
Black-Scholes option Greeks for pre-trade analytics.
Pure-Python — no scipy dependency.
"""
import math


def _norm_cdf(x: float) -> float:
    return (1.0 + math.erf(x / math.sqrt(2))) / 2.0


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


def bs_price(S: float, K: float, T: float, r: float, sigma: float, is_call: bool) -> float:
    if T <= 0:
        return max(S - K, 0.0) if is_call else max(K - S, 0.0)
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if is_call:
        return S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
    return K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)


def implied_vol(market_price: float, S: float, K: float, T: float,
                r: float, is_call: bool, tol: float = 1e-5, max_iter: int = 100) -> float:
    """Newton-Raphson IV solver. Returns NaN on failure."""
    if T <= 0 or market_price <= 0:
        return float("nan")
    sigma = 0.3
    for _ in range(max_iter):
        price = bs_price(S, K, T, r, sigma, is_call)
        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        vega_raw = S * _norm_pdf(d1) * math.sqrt(T)
        if vega_raw < 1e-10:
            break
        diff = price - market_price
        if abs(diff) < tol:
            return sigma
        sigma -= diff / vega_raw
        if sigma <= 0:
            sigma = 0.001
    return sigma if 0 < sigma < 5 else float("nan")


def bs_greeks(S: float, K: float, T: float, r: float, sigma: float, is_call: bool) -> dict:
    if T <= 0 or sigma <= 0:
        return {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0}
    sqrt_T = math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T
    pdf_d1 = _norm_pdf(d1)
    delta = _norm_cdf(d1) if is_call else _norm_cdf(d1) - 1
    gamma = pdf_d1 / (S * sigma * sqrt_T)
    theta = (-(S * pdf_d1 * sigma) / (2 * sqrt_T)
             - r * K * math.exp(-r * T) * (_norm_cdf(d2) if is_call else _norm_cdf(-d2))) / 365
    vega = S * pdf_d1 * sqrt_T / 100
    return {
        "delta": round(delta, 4),
        "gamma": round(gamma, 6),
        "theta": round(theta, 2),
        "vega":  round(vega, 2),
    }


def _breakeven_analysis(spots: list, pnl_vals: list) -> dict:
    """
    Zero-crossings of a P&L curve plus the profit zones they bound.

    levels : spot levels where P&L crosses zero, ascending
    zones  : profit intervals as {lo, hi}; None on an open end
    mode   : between | outside | above | below | always | never
    """
    levels: list[float] = []
    for i in range(len(spots) - 1):
        a, b = pnl_vals[i], pnl_vals[i + 1]
        if (a < 0) != (b < 0):
            t = -a / (b - a)
            levels.append(round(spots[i] + t * (spots[i + 1] - spots[i]), 2))

    def _interp(x: float) -> float:
        if x <= spots[0]:
            return pnl_vals[0]
        if x >= spots[-1]:
            return pnl_vals[-1]
        for i in range(len(spots) - 1):
            if spots[i] <= x <= spots[i + 1]:
                t = (x - spots[i]) / (spots[i + 1] - spots[i])
                return pnl_vals[i] + t * (pnl_vals[i + 1] - pnl_vals[i])
        return 0.0

    bounds = [None] + levels + [None]
    zones = []
    for i in range(len(bounds) - 1):
        lo, hi = bounds[i], bounds[i + 1]
        if lo is None and hi is None:
            probe = spots[len(spots) // 2]
        elif lo is None:
            probe = spots[0]
        elif hi is None:
            probe = spots[-1]
        else:
            probe = (lo + hi) / 2
        if _interp(probe) > 0:
            zones.append({"lo": lo, "hi": hi})

    open_ends = sum(1 for z in zones if z["lo"] is None or z["hi"] is None)
    if not zones:
        mode = "never"
    elif not levels:
        mode = "always"
    elif len(zones) == 1 and open_ends == 0:
        mode = "between"
    elif len(zones) == 1 and zones[0]["lo"] is None:
        mode = "below"
    elif len(zones) == 1:
        mode = "above"
    elif len(zones) == 2 and open_ends == 2:
        mode = "outside"
    else:
        mode = "multi"

    return {"levels": levels, "zones": zones, "mode": mode}


def position_payoff(legs: list, spot: float, dte_days: int, r: float = 0.065,
                    target_days: int = 0, steps: int = 61, spread_pct: float = 0.12) -> dict:
    """
    Payoff analysis across a spot range for a multi-leg position.

    target_days : calendar days ahead for the "target date" curve (0 = today).

    Returns:
        scenarios    : list of {spot, pnl_target, pnl_expiry}
        breakevens   : {"expiry": {levels, zones, mode}, "target": {...}}
        max_profit   : float or None (unlimited)
        max_loss     : float or None (unlimited)
        pop          : float 0-100, probability of profit at expiry
        net_premium  : float, net premium collected (+) or paid (-)
        atm_iv_pct   : float, average IV used (%)
        target_days  : echo of the input after clamping to [0, dte]
    """
    dte_days    = max(dte_days, 0)
    target_days = min(max(int(target_days), 0), dte_days)
    T_exp = dte_days / 365.0
    T_tgt = (dte_days - target_days) / 365.0

    # Solve IV per leg at current spot (full time to expiry)
    leg_ivs: list[float] = []
    for l in legs:
        is_call = l["opt_type"].upper() == "CE"
        iv = implied_vol(l["price"], spot, l["strike"], T_exp, r, is_call)
        leg_ivs.append(iv if (iv and not math.isnan(iv) and iv > 0) else 0.20)

    atm_iv = sum(leg_ivs) / len(leg_ivs) if leg_ivs else 0.20

    lo = spot * (1 - spread_pct)
    hi = spot * (1 + spread_pct)
    spots = [lo + (hi - lo) * i / (steps - 1) for i in range(steps)]

    scenarios = []
    for s in spots:
        pnl_e = pnl_t = 0.0
        for l, iv in zip(legs, leg_ivs):
            is_call = l["opt_type"].upper() == "CE"
            intrinsic    = max(0.0, s - l["strike"]) if is_call else max(0.0, l["strike"] - s)
            target_price = bs_price(s, l["strike"], T_tgt, r, iv, is_call) if T_tgt > 0 else intrinsic
            sign = 1.0 if l["side"] == "BUY" else -1.0
            pnl_e += sign * (intrinsic    - l["price"]) * l["qty"]
            pnl_t += sign * (target_price - l["price"]) * l["qty"]
        scenarios.append({"spot": round(s, 2),
                          "pnl_target": round(pnl_t, 0),
                          "pnl_expiry": round(pnl_e, 0)})

    exp_vals = [s["pnl_expiry"] for s in scenarios]
    tgt_vals = [s["pnl_target"] for s in scenarios]
    be_expiry = _breakeven_analysis(spots, exp_vals)
    be_target = _breakeven_analysis(spots, tgt_vals)

    # Max profit / max loss (None = unlimited, detected by diverging edges)
    mx, mn = max(exp_vals), min(exp_vals)
    max_profit = None if (exp_vals[-1] > exp_vals[-2] or exp_vals[0] > exp_vals[1]) else round(mx, 0)
    max_loss   = None if (exp_vals[-1] < exp_vals[-2] or exp_vals[0] < exp_vals[1]) else round(mn, 0)

    pop = _payoff_pop(spot, be_expiry["levels"], spots, exp_vals, atm_iv, T_exp, r)

    net_premium = sum(
        (l["price"] if l["side"] == "SELL" else -l["price"]) * l["qty"]
        for l in legs
    )

    return {
        "scenarios":   scenarios,
        "breakevens":  {"expiry": be_expiry, "target": be_target},
        "max_profit":  max_profit,
        "max_loss":    max_loss,
        "pop":         pop,
        "net_premium": round(net_premium, 0),
        "atm_iv_pct":  round(atm_iv * 100, 1),
        "target_days": target_days,
    }


def position_pcr(legs: list) -> dict:
    """Put–call ratio of the position's own legs, by premium and by quantity."""
    put_prem = sum(l["price"] * l["qty"] for l in legs if l["opt_type"].upper() == "PE")
    call_prem = sum(l["price"] * l["qty"] for l in legs if l["opt_type"].upper() == "CE")
    put_qty = sum(l["qty"] for l in legs if l["opt_type"].upper() == "PE")
    call_qty = sum(l["qty"] for l in legs if l["opt_type"].upper() == "CE")

    by_premium = round(put_prem / call_prem, 2) if call_prem else None
    by_quantity = round(put_qty / call_qty, 2) if call_qty else None

    if by_premium is None:
        skew = "Puts only" if put_prem else "Calls only"
    elif by_premium > 1.10:
        skew = "Put-heavy"
    elif by_premium < 0.90:
        skew = "Call-heavy"
    else:
        skew = "Balanced"

    return {"by_premium": by_premium, "by_quantity": by_quantity, "skew": skew}


def greeks_profile(agg: dict) -> dict:
    """One-line read of the position from its aggregate per-unit Greeks."""
    d, v, t, g = agg.get("delta", 0.0), agg.get("vega", 0.0), agg.get("theta", 0.0), agg.get("gamma", 0.0)

    if abs(d) <= 0.10:
        direction = "Delta-neutral"
    elif abs(d) <= 0.30:
        direction = "Mild bullish lean" if d > 0 else "Mild bearish lean"
    else:
        direction = "Bullish" if d > 0 else "Bearish"

    if v < -5:
        volatility = "short vol"
    elif v > 5:
        volatility = "long vol"
    else:
        volatility = "vol-neutral"

    if t > 1:
        time = "decay in favour"
    elif t < -1:
        time = "decay against"
    else:
        time = "time-neutral"

    gamma_risk = abs(g) > 0.001
    parts = [direction, volatility, time] + (["gamma risk"] if gamma_risk else [])
    return {
        "direction":  direction,
        "volatility": volatility,
        "time":       time,
        "gamma_risk": gamma_risk,
        "label":      " | ".join(parts),
    }


def _payoff_pop(spot: float, breakevens: list, spots: list, pnl_vals: list,
                sigma: float, T: float, r: float) -> float:
    """Probability of profit using the log-normal terminal distribution."""
    if not breakevens or T <= 0 or sigma <= 0:
        profitable = sum(1 for p in pnl_vals if p > 0)
        return round(100 * profitable / max(len(pnl_vals), 1), 1)

    def _cdf_below(K: float) -> float:
        if K <= 0:
            return 0.0
        d2 = (math.log(spot / K) + (r - 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        return _norm_cdf(-d2)

    def _interp(s_target: float) -> float:
        if s_target <= spots[0]:
            return pnl_vals[0]
        if s_target >= spots[-1]:
            return pnl_vals[-1]
        for i in range(len(spots) - 1):
            if spots[i] <= s_target <= spots[i + 1]:
                t = (s_target - spots[i]) / (spots[i + 1] - spots[i])
                return pnl_vals[i] + t * (pnl_vals[i + 1] - pnl_vals[i])
        return 0.0

    bounds = [0.0] + sorted(breakevens) + [float("inf")]
    pop = 0.0
    for i in range(len(bounds) - 1):
        lo_b, hi_b = bounds[i], bounds[i + 1]
        mid = spots[0] if lo_b == 0 else (spots[-1] if hi_b == float("inf") else (lo_b + hi_b) / 2)
        if _interp(mid) > 0:
            p_lo = _cdf_below(lo_b) if lo_b > 0 else 0.0
            p_hi = _cdf_below(hi_b) if hi_b < float("inf") else 1.0
            pop += p_hi - p_lo
    return round(pop * 100, 1)


def greeks_for_leg(spot: float, strike: float, dte_days: int, r: float,
                   ltp: float, opt_type: str, side: str) -> dict:
    """IV + Greeks for one leg, signed by BUY (+1) or SELL (-1)."""
    T = max(dte_days, 0) / 365.0
    is_call = opt_type.upper() == "CE"
    iv = implied_vol(ltp, spot, strike, T, r, is_call)
    sigma = iv if (iv and not math.isnan(iv)) else 0.20
    g = bs_greeks(spot, strike, T, r, sigma, is_call)
    sign = 1.0 if side == "BUY" else -1.0
    return {
        "iv":    round(iv * 100, 2) if (iv and not math.isnan(iv)) else None,
        "delta": round(g["delta"] * sign, 4),
        "gamma": round(g["gamma"] * sign, 6),
        "theta": round(g["theta"] * sign, 2),
        "vega":  round(g["vega"]  * sign, 2),
    }
