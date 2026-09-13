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
