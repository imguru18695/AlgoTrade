"""
Demo mode — all features work with in-memory state and simulated live prices.
No Kite credentials needed. Prices drift randomly each tick to show live P&L.

Run: uvicorn demo:app --reload --port 8003
"""
import asyncio
import copy
import json
import logging
import math
import random
from contextlib import asynccontextmanager
from datetime import date, timedelta
from typing import Optional

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader

from rm.engine import run_engine, reset_basket, rearm_basket, get_basket_state
from strategies import templates as strat_templates
from strategies import engine as strat_engine

logging.basicConfig(level=logging.INFO)

_exit_log: list[dict] = []

# ── Simulated India VIX ───────────────────────────────────────────────────────
_VIX: float          = 14.5    # current value (drifts every 3s)
_VIX_PREV_CLOSE: float = 14.2  # simulated previous-day close (fixed)
_VIX_5D_AGO: float   = 13.8    # simulated value 5 trading days ago (fixed)
_VIX_52W_HIGH: float = 24.5    # simulated 52-week high (fixed)
_VIX_52W_LOW: float  = 10.8    # simulated 52-week low (fixed)
_VIX_HISTORY: list[float] = [  # rolling history for EMA/SMA (pre-seeded 50 values)
    13.0,13.1,13.4,13.2,13.5,13.8,14.0,14.2,13.9,13.7,
    13.5,13.8,14.1,14.3,14.0,13.8,13.6,13.9,14.2,14.4,
    14.1,13.9,14.0,14.3,14.5,14.2,14.0,14.3,14.5,14.4,
    14.2,14.0,14.3,14.5,14.7,14.4,14.2,14.4,14.5,14.3,
    14.1,14.3,14.5,14.4,14.2,14.4,14.5,14.3,14.4,14.5,
]
_VIX_EMA9:  float = 14.5
_VIX_EMA21: float = 14.2
_VIX_SMA20: float = 14.3

# ── Token counter for demo positions ─────────────────────────────────────────
_next_token_counter = 500000

def _next_token() -> int:
    global _next_token_counter
    _next_token_counter += 1
    return _next_token_counter

# ── Option chain simulation ───────────────────────────────────────────────────

_UNDERLYINGS = {
    "NIFTY":      {"spot": 24500, "step": 50,  "lot": 25,  "range": 18},
    "BANKNIFTY":  {"spot": 52000, "step": 100, "lot": 15,  "range": 18},
    "FINNIFTY":   {"spot": 23500, "step": 50,  "lot": 40,  "range": 18},
    "MIDCPNIFTY": {"spot": 12800, "step": 25,  "lot": 75,  "range": 18},
}

def _get_expiries() -> list[str]:
    """Return next 4 weekly (Thursday) + 1 monthly expiry dates."""
    today = date.today()
    days_to_thu = (3 - today.weekday()) % 7 or 7
    expiries = []
    thu = today + timedelta(days=days_to_thu)
    for i in range(4):
        expiries.append((thu + timedelta(weeks=i)).isoformat())
    # Monthly: last Thursday of current/next month
    for delta_m in (0, 1):
        m = (today.month + delta_m - 1) % 12 + 1
        y = today.year + (today.month + delta_m - 1) // 12
        last_day = date(y, m % 12 + 1, 1) - timedelta(days=1) if m < 12 else date(y, 12, 31)
        while last_day.weekday() != 3:
            last_day -= timedelta(days=1)
        iso = last_day.isoformat()
        if iso not in expiries:
            expiries.append(iso)
    return sorted(set(expiries))[:5]

def _bs_price(spot: float, strike: float, days: int, iv: float, is_call: bool) -> float:
    """Simplified Black-Scholes for demo pricing."""
    if days <= 0:
        intrinsic = max(0, spot - strike) if is_call else max(0, strike - spot)
        return round(intrinsic, 2)
    t = days / 365
    r = 0.065
    sigma = iv / 100
    from math import log, sqrt, exp
    try:
        d1 = (log(spot / strike) + (r + 0.5 * sigma**2) * t) / (sigma * sqrt(t))
        d2 = d1 - sigma * sqrt(t)
        def N(x):
            return 0.5 * (1 + math.erf(x / math.sqrt(2)))
        if is_call:
            price = spot * N(d1) - strike * exp(-r * t) * N(d2)
        else:
            price = strike * exp(-r * t) * N(-d2) - spot * N(-d1)
        return round(max(0.05, price), 2)
    except Exception:
        return 0.05

def _generate_chain(symbol: str, expiry_iso: str) -> dict:
    """Generate a realistic simulated option chain."""
    cfg = _UNDERLYINGS.get(symbol, _UNDERLYINGS["NIFTY"])
    spot = cfg["spot"] * random.uniform(0.998, 1.002)  # tiny jitter
    step = cfg["step"]
    atm  = round(spot / step) * step
    exp_date = date.fromisoformat(expiry_iso)
    days = max(1, (exp_date - date.today()).days)

    # Skew: PE IV higher (typical Indian market skew)
    base_iv = 15 + random.uniform(-1, 1)

    strikes = []
    for i in range(-cfg["range"], cfg["range"] + 1):
        strike = atm + i * step
        dist_pct = abs(i) / cfg["range"]

        ce_iv = base_iv + abs(i) * 0.3 + random.uniform(-0.3, 0.3)
        pe_iv = base_iv + abs(i) * 0.4 + (1.5 if i < 0 else 0) + random.uniform(-0.3, 0.3)

        ce_ltp = _bs_price(spot, strike, days, ce_iv, True)
        pe_ltp = _bs_price(spot, strike, days, pe_iv, False)

        oi_base = 800000
        oi_ce = int(oi_base * math.exp(-dist_pct * 3) * random.uniform(0.7, 1.3) / step * 50)
        oi_pe = int(oi_base * math.exp(-dist_pct * 3) * random.uniform(0.7, 1.3) / step * 50)

        strikes.append({
            "strike": strike,
            "atm": strike == atm,
            "ce": {"ltp": ce_ltp, "oi": max(1000, oi_ce), "iv": round(ce_iv, 1)},
            "pe": {"ltp": pe_ltp, "oi": max(1000, oi_pe), "iv": round(pe_iv, 1)},
        })

    return {
        "symbol":   symbol,
        "spot":     round(spot, 2),
        "atm":      atm,
        "lot_size": cfg["lot"],
        "expiry":   expiry_iso,
        "days":     days,
        "strikes":  strikes,
    }

def _make_tradingsymbol(symbol: str, expiry_iso: str, strike: int, opt_type: str) -> str:
    """Generate NSE-style tradingsymbol. e.g. NIFTY25612 24500CE"""
    d = date.fromisoformat(expiry_iso)
    month_codes = {1:"JAN",2:"FEB",3:"MAR",4:"APR",5:"MAY",6:"JUN",
                   7:"JUL",8:"AUG",9:"SEP",10:"OCT",11:"NOV",12:"DEC"}
    # Weekly: NIFTY25612 (YY + DD + M_num) or monthly: NIFTYJUN25
    # Use Kite-style: NIFTY2561224500CE
    return f"{symbol}{str(d.year)[2:]}{d.month}{d.day}{strike}{opt_type}"


async def _demo_exit(basket_id: int, positions: list, reason: str, event_id: int | None = None):
    entry = {"basket_id": basket_id, "reason": reason,
             "symbols": [p["tradingsymbol"] for p in positions]}
    _exit_log.append(entry)
    logging.info(f"[DEMO EXIT] Basket {basket_id}: {reason}")


def _demo_ltp(instrument_token: int) -> float | None:
    p = _PRICES.get(instrument_token)
    return p


def _get_baskets_for_engine() -> list[dict]:
    return _build_context()["baskets"]


# ── Demo execution order book ────────────────────────────────────────────────

_DEMO_ORDERS: dict[str, dict] = {}   # order_id → order record
_demo_order_seq = 0

def _demo_new_order_id() -> str:
    global _demo_order_seq
    _demo_order_seq += 1
    return f"DEMO{_demo_order_seq:06d}"

def _demo_order_record(order_id, basket_id, basket_name, tradingsymbol,
                        exchange, product, side, qty, order_type, price,
                        strategy_name="") -> dict:
    return {
        "order_id":      order_id,
        "basket_id":     basket_id,
        "basket_name":   basket_name,
        "tradingsymbol": tradingsymbol,
        "exchange":      exchange,
        "product":       product,
        "side":          side,
        "qty":           qty,
        "order_type":    order_type,
        "price":         price,
        "status":        "OPEN",
        "filled_qty":    0,
        "avg_price":     None,
        "placed_at":     time.time() if True else 0,
        "strategy_name": strategy_name,
        "reject_reason": None,
    }

import time as _time_mod   # avoid shadowing built-in

async def _simulate_fill(order_id: str, delay: float = 2.5):
    """Simulate fill after a short delay, then auto-assign to basket."""
    await asyncio.sleep(delay)
    rec = _DEMO_ORDERS.get(order_id)
    if not rec or rec["status"] != "OPEN":
        return

    fill_price = rec["price"] or 100.0
    rec["status"]     = "COMPLETE"
    rec["filled_qty"] = rec["qty"]
    rec["avg_price"]  = fill_price

    # Add to live positions and assign to basket
    qty   = rec["qty"] if rec["side"] == "BUY" else -rec["qty"]
    token = _next_token()
    pos   = _make_pos(rec["tradingsymbol"], rec["exchange"], rec["product"],
                      qty, fill_price, fill_price, token,
                      _UNDERLYINGS.get(rec["tradingsymbol"][:len(rec["tradingsymbol"])].split("2")[0],
                                       {"lot": 25}).get("lot", 25))
    _POSITIONS.append(pos)
    _PRICES[token] = fill_price

    if rec.get("basket_id") is not None:
        key = _pos_key(rec["tradingsymbol"], rec["exchange"], rec["product"])
        _assignments[key] = rec["basket_id"]

    logging.info(f"[DEMO FILL] {order_id}: {rec['tradingsymbol']} @ {fill_price}")


# ── Simulated price drift ─────────────────────────────────────────────────────

_PRICES: dict[int, float] = {}   # instrument_token → live price


def _update_vix_indicators(new_vix: float) -> None:
    """Update EMA(9), EMA(21), SMA(20) from latest VIX tick."""
    global _VIX_EMA9, _VIX_EMA21, _VIX_SMA20
    _VIX_HISTORY.append(new_vix)
    if len(_VIX_HISTORY) > 200:
        _VIX_HISTORY.pop(0)
    k9  = 2 / (9  + 1)
    k21 = 2 / (21 + 1)
    _VIX_EMA9  = round(new_vix * k9  + _VIX_EMA9  * (1 - k9),  2)
    _VIX_EMA21 = round(new_vix * k21 + _VIX_EMA21 * (1 - k21), 2)
    _VIX_SMA20 = round(sum(_VIX_HISTORY[-20:]) / min(len(_VIX_HISTORY), 20), 2)


async def _price_drift_loop():
    """Randomly drift prices and VIX every 3 seconds to simulate live ticks."""
    global _VIX
    while True:
        await asyncio.sleep(3)
        for p in _POSITIONS:
            tok = p["instrument_token"]
            base = p["average_price"]
            current = _PRICES.get(tok, p["last_price"])
            drift = current * random.uniform(-0.005, 0.005)
            new_price = max(base * 0.6, min(base * 1.4, current + drift))
            _PRICES[tok] = round(new_price, 2)
        # VIX slow drift ±0.1 per tick, clamped 10–25
        _VIX = round(max(10.0, min(25.0, _VIX + random.uniform(-0.1, 0.1))), 2)
        _update_vix_indicators(_VIX)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Seed prices
    for p in _POSITIONS:
        _PRICES[p["instrument_token"]] = p["last_price"]

    asyncio.create_task(_price_drift_loop())
    asyncio.create_task(run_engine(
        get_baskets_fn=_get_baskets_for_engine,
        ltp_fn=_demo_ltp,
        exit_fn=_demo_exit,
    ))

    # ── Strategy auto-execution engine ────────────────────────────────
    async def _demo_place_orders_fn(tmpl: dict, legs: list) -> int:
        """Demo: schedule simulated fills and return basket_id."""
        global _next_basket_id
        bid = _next_basket_id
        _next_basket_id += 1
        name = tmpl.get("name", f"Auto {bid}")
        _baskets[bid] = {"id": bid, "name": name, "order_type": "LIMIT"}
        _rm[bid] = _empty_rm()

        for leg in legs:
            oid = _demo_new_order_id()
            rec = _demo_order_record(
                oid, bid, name,
                leg["tradingsymbol"], leg["exchange"], leg["product"],
                leg["side"], leg["qty"], leg["order_type"], leg["price"],
                strategy_name=strat_templates.STRATEGY_TYPES.get(
                    tmpl.get("strategy_type", ""), tmpl.get("name", "Auto")),
            )
            rec["placed_at"] = _time_mod.time()
            _DEMO_ORDERS[oid] = rec
            asyncio.create_task(_simulate_fill(oid, delay=random.uniform(1.5, 3.0)))

        return bid

    def _demo_set_rm_fn(basket_id: int, rm: dict):
        _rm[basket_id] = rm

    asyncio.create_task(strat_engine.run_strategy_engine(
        get_templates_fn = strat_templates.list_templates,
        get_vix_fn       = lambda: _VIX,
        get_chain_fn     = _generate_chain,
        place_orders_fn  = _demo_place_orders_fn,
        set_rm_fn        = _demo_set_rm_fn,
        set_status_fn    = strat_templates.set_status,
    ))

    yield


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")

_env = Environment(loader=FileSystemLoader("templates"), cache_size=0, auto_reload=True)


def render(name: str, ctx: dict) -> HTMLResponse:
    return HTMLResponse(_env.get_template(name).render(**ctx))


# ── In-memory state ───────────────────────────────────────────────────────────

def _empty_rm() -> dict:
    return {
        "pt_active": False, "pt_inr": None, "pt_ticks": None,
        "lg_active": False, "lg_inr": None, "lg_ticks": None,
        "ps_active": False, "ps_trigger": None, "ps_lock": None,
        "ps_step_profit": None, "ps_step_lock": None,
        "eod_exit": False,
        "delete_on_fire": 1,
    }


def _make_pos(tradingsymbol, exchange, product, quantity, average_price,
              last_price, instrument_token, multiplier=1):
    pnl = (last_price - average_price) * quantity * multiplier
    cost = abs(average_price) * abs(quantity) * multiplier
    return {
        "tradingsymbol": tradingsymbol,
        "exchange": exchange,
        "product": product,
        "quantity": quantity,
        "average_price": average_price,
        "last_price": last_price,
        "pnl": pnl,
        "pnl_pct": (pnl / cost * 100) if cost else 0.0,
        "instrument_token": instrument_token,
        "multiplier": multiplier,
    }


_POSITIONS = [
    _make_pos("NIFTY2562524000CE", "NFO", "NRML",  2, 210.50, 245.00, 123001, 50),
    _make_pos("NIFTY2562524000PE", "NFO", "NRML", -2, 195.00, 180.00, 123002, 50),
    _make_pos("BANKNIFTY2562552000CE", "NFO", "NRML", -1, 490.00, 430.00, 123003, 15),
    _make_pos("BANKNIFTY2562552000PE", "NFO", "NRML", -1, 460.00, 410.00, 123004, 15),
    _make_pos("FINNIFTY2562523000CE", "NFO", "NRML",  1, 120.00,  98.00, 123005, 40),
]

_baskets: dict[int, dict] = {
    1: {"id": 1, "name": "BNF Short Straddle", "order_type": "LIMIT"},
    2: {"id": 2, "name": "Nifty Hedge",         "order_type": "LIMIT"},
}

_assignments: dict[str, int] = {
    "BANKNIFTY2562552000CE|NFO|NRML": 1,
    "BANKNIFTY2562552000PE|NFO|NRML": 1,
    "NIFTY2562524000CE|NFO|NRML":     2,
    "NIFTY2562524000PE|NFO|NRML":     2,
}

_rm: dict[int, dict] = {
    1: {
        "pt_active": True,  "pt_inr": 15000, "pt_ticks": 3,
        "lg_active": True,  "lg_inr": 10000, "lg_ticks": 5,
        "ps_active": False, "ps_trigger": None, "ps_lock": None,
        "ps_step_profit": None, "ps_step_lock": None,
        "eod_exit": True,
        "delete_on_fire": 1,
    },
    2: {**_empty_rm(),
        "ps_active": True, "ps_trigger": 8000, "ps_lock": 5000,
        "ps_step_profit": 2000, "ps_step_lock": 1000,
        "eod_exit": True,
    },
}

_next_basket_id = 3


def _pos_key(tradingsymbol, exchange, product):
    return f"{tradingsymbol}|{exchange}|{product}"


def _live_pnl(p: dict) -> tuple[float, float, float]:
    ltp = _PRICES.get(p["instrument_token"], p["last_price"])
    qty  = p["quantity"]
    avg  = p["average_price"]
    mult = p.get("multiplier", 1)
    pnl  = (ltp - avg) * qty * mult
    cost = abs(avg) * abs(qty) * mult
    pnl_pct = (pnl / cost * 100) if cost else 0.0
    return ltp, pnl, pnl_pct


# ── View helpers ──────────────────────────────────────────────────────────────

def _build_context() -> dict:
    positions = copy.deepcopy(_POSITIONS)
    for p in positions:
        ltp, pnl, pnl_pct = _live_pnl(p)
        p["last_price"] = ltp
        p["pnl"]        = pnl
        p["pnl_pct"]    = pnl_pct

    basket_positions: dict[int, list] = {bid: [] for bid in _baskets}
    unallocated = []
    for p in positions:
        key = _pos_key(p["tradingsymbol"], p["exchange"], p["product"])
        bid = _assignments.get(key)
        if bid and bid in basket_positions:
            basket_positions[bid].append(p)
        else:
            unallocated.append(p)

    baskets = []
    for bid, b in _baskets.items():
        rm = _rm.get(bid, _empty_rm())
        rm_enabled = bool(rm.get("pt_active") or rm.get("lg_active") or
                          rm.get("ps_active") or rm.get("eod_exit"))
        pos = basket_positions[bid]
        pnl = sum(p["pnl"] for p in pos)
        cost = sum(abs(p["average_price"]) * abs(p["quantity"]) * p.get("multiplier", 1) for p in pos)
        state = get_basket_state(bid)
        baskets.append({
            "id":          bid,
            "name":        b["name"],
            "order_type":  b.get("order_type", "LIMIT"),
            "positions":   pos,
            "pnl":         pnl,
            "pnl_pct":     (pnl / cost * 100) if cost else 0.0,
            "rm":          rm,
            "rm_enabled":  rm_enabled,
            "fired":       state.get("fired", False),
            "peak_pnl":    state.get("peak_pnl"),
            "ps_floor":    state.get("floor") if state.get("ps_armed") else None,
        })

    active_baskets     = [b for b in baskets if b["positions"]]
    baskets_without_rm = [b for b in active_baskets if not b["rm_enabled"]]

    return {
        "positions":                positions,
        "unallocated":              unallocated,
        "baskets":                  baskets,
        "active_baskets_count":     len(active_baskets),
        "baskets_without_rm_count": len(baskets_without_rm),
        "total_pnl":                sum(p["pnl"] for p in positions),
        "demo_mode":                False,   # enable live polling in demo
        "user_id":                  "DEMO",
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    ctx = _build_context()
    ctx["active_page"] = "dashboard"
    return render("dashboard.html", ctx)


@app.get("/management", response_class=HTMLResponse)
async def management():
    ctx = _build_context()
    ctx["active_page"] = "management"
    return render("management.html", ctx)


@app.get("/api/expiries")
async def api_expiries():
    return JSONResponse({"expiries": _get_expiries()})


@app.get("/api/chain/{symbol}")
async def api_chain(symbol: str, expiry: Optional[str] = None):
    symbol = symbol.upper()
    if symbol not in _UNDERLYINGS:
        return JSONResponse({"error": "Unknown symbol"}, status_code=404)
    expiries = _get_expiries()
    exp = expiry if expiry in expiries else expiries[0]
    chain = _generate_chain(symbol, exp)
    return JSONResponse(chain)


@app.post("/strategies/execute")
async def execute_strategy(request: Request):
    global _next_basket_id
    form = await request.form()

    symbol   = form.get("symbol", "NIFTY").upper()
    expiry   = form.get("expiry", "")
    lots     = int(form.get("lots", 1))
    order_type = form.get("order_type", "LIMIT")
    basket_id_raw = form.get("basket_id", "")
    new_basket_name = (form.get("new_basket_name") or "").strip()

    # Parse legs: JSON array of {strike, opt_type, side, ltp}
    legs_json = form.get("legs", "[]")
    try:
        legs = json.loads(legs_json)
    except Exception:
        return JSONResponse({"error": "Invalid legs JSON"}, status_code=400)

    if not legs:
        return JSONResponse({"error": "No legs provided"}, status_code=400)

    cfg = _UNDERLYINGS.get(symbol, _UNDERLYINGS["NIFTY"])
    lot_size = cfg["lot"]
    qty_per_lot = lots * lot_size

    # Determine basket
    if basket_id_raw == "new" or not basket_id_raw:
        bid = _next_basket_id
        _next_basket_id += 1
        name = new_basket_name or f"{symbol} Strategy {bid}"
        _baskets[bid] = {"id": bid, "name": name, "order_type": order_type}
        _rm[bid] = _empty_rm()
    else:
        bid = int(basket_id_raw)
        if bid not in _baskets:
            return JSONResponse({"error": "Basket not found"}, status_code=404)

    # Create positions from legs
    for leg in legs:
        strike   = int(leg["strike"])
        opt_type = leg["opt_type"].upper()   # CE or PE
        side     = leg["side"].upper()        # BUY or SELL
        ltp      = float(leg.get("ltp", 100))

        qty = qty_per_lot if side == "BUY" else -qty_per_lot
        token = _next_token()
        tsym  = _make_tradingsymbol(symbol, expiry, strike, opt_type)

        pos = _make_pos(tsym, "NFO", "NRML", qty, ltp, ltp, token, lot_size)
        _POSITIONS.append(pos)
        _PRICES[token] = ltp
        key = _pos_key(tsym, "NFO", "NRML")
        _assignments[key] = bid

    return JSONResponse({"status": "ok", "basket_id": bid, "basket_name": _baskets[bid]["name"]})


@app.get("/pnl")
async def get_pnl():
    ctx = _build_context()
    positions_data = {}
    total_pnl = 0.0
    for p in ctx["positions"]:
        key = _pos_key(p["tradingsymbol"], p["exchange"], p["product"])
        positions_data[key] = {"ltp": p["last_price"], "pnl": p["pnl"], "pnl_pct": p["pnl_pct"]}
        total_pnl += p["pnl"]

    baskets_data = {}
    for b in ctx["baskets"]:
        state = get_basket_state(b["id"])
        baskets_data[str(b["id"])] = {
            "pnl":      b["pnl"],
            "pnl_pct":  b["pnl_pct"],
            "peak_pnl": state.get("peak_pnl"),
            "ps_floor": state.get("floor") if state.get("ps_armed") else None,
        }

    return JSONResponse({"total_pnl": total_pnl, "positions": positions_data, "baskets": baskets_data})


@app.get("/logs", response_class=HTMLResponse)
async def logs_page():
    # Stub — shows empty logs page in demo
    return render("logs.html", {
        "events": [], "basket_names": [], "basket_name": "",
        "from_date": "", "to_date": "", "request": None,
        "active_page": "logs", "user_id": "DEMO", "demo_mode": False,
    })


@app.get("/auth/login", response_class=HTMLResponse)
async def login():
    return RedirectResponse(url="/")


@app.get("/auth/logout")
async def logout():
    return RedirectResponse(url="/management", status_code=302)


@app.post("/baskets/create")
async def create_basket(name: str = Form(default="")):
    global _next_basket_id
    bid = _next_basket_id
    _next_basket_id += 1
    _baskets[bid] = {"id": bid, "name": name.strip() or f"Basket {bid}", "order_type": "LIMIT"}
    _rm[bid] = _empty_rm()
    return RedirectResponse(url="/management", status_code=302)


@app.post("/baskets/{basket_id}/rename")
async def rename_basket(basket_id: int, name: str = Form(...)):
    if basket_id in _baskets:
        _baskets[basket_id]["name"] = name.strip()
    return RedirectResponse(url="/management", status_code=302)


@app.post("/baskets/{basket_id}/delete")
async def delete_basket(basket_id: int):
    _baskets.pop(basket_id, None)
    _rm.pop(basket_id, None)
    for k in [k for k, v in _assignments.items() if v == basket_id]:
        del _assignments[k]
    return RedirectResponse(url="/management", status_code=302)


@app.post("/baskets/{basket_id}/order-type")
async def save_order_type(basket_id: int, order_type: str = Form(...)):
    if basket_id in _baskets:
        _baskets[basket_id]["order_type"] = order_type if order_type in ("LIMIT", "MARKET") else "LIMIT"
    return RedirectResponse(url="/management", status_code=302)


@app.post("/baskets/{basket_id}/rearm")
async def rearm(basket_id: int):
    rearm_basket(basket_id)
    return RedirectResponse(url="/management", status_code=302)


@app.post("/baskets/{basket_id}/rm/profit-target")
async def save_pt(basket_id: int, request: Request):
    form = await request.form()
    rm = _rm.setdefault(basket_id, _empty_rm())
    rm["pt_active"] = form.get("active") == "1"
    rm["pt_inr"]    = float(form["inr"])   if form.get("inr")   else None
    rm["pt_ticks"]  = int(form["ticks"])   if form.get("ticks") else None
    reset_basket(basket_id)
    return RedirectResponse(url="/management", status_code=302)


@app.post("/baskets/{basket_id}/rm/loss-guard")
async def save_lg(basket_id: int, request: Request):
    form = await request.form()
    rm = _rm.setdefault(basket_id, _empty_rm())
    rm["lg_active"] = form.get("active") == "1"
    rm["lg_inr"]    = float(form["inr"])   if form.get("inr")   else None
    rm["lg_ticks"]  = int(form["ticks"])   if form.get("ticks") else None
    reset_basket(basket_id)
    return RedirectResponse(url="/management", status_code=302)


@app.post("/baskets/{basket_id}/rm/profit-shield")
async def save_ps(basket_id: int, request: Request):
    form = await request.form()
    rm = _rm.setdefault(basket_id, _empty_rm())
    rm["ps_active"]      = form.get("active") == "1"
    rm["ps_trigger"]     = float(form["trigger"])     if form.get("trigger")     else None
    rm["ps_lock"]        = float(form["lock"])        if form.get("lock")        else None
    rm["ps_step_profit"] = float(form["step_profit"]) if form.get("step_profit") else None
    rm["ps_step_lock"]   = float(form["step_lock"])   if form.get("step_lock")   else None
    reset_basket(basket_id)
    return RedirectResponse(url="/management", status_code=302)


@app.post("/baskets/{basket_id}/rm/eod-exit")
async def save_eod_exit(basket_id: int, request: Request):
    form = await request.form()
    rm = _rm.setdefault(basket_id, _empty_rm())
    rm["eod_exit"] = form.get("enabled") == "1"
    return RedirectResponse(url="/management", status_code=302)


@app.post("/baskets/{basket_id}/rm/delete-on-fire")
async def save_delete_on_fire(basket_id: int, request: Request):
    form = await request.form()
    rm = _rm.setdefault(basket_id, _empty_rm())
    rm["delete_on_fire"] = 1 if form.get("enabled") == "1" else 0
    return RedirectResponse(url="/management", status_code=302)


@app.post("/baskets/assign")
async def assign(
    basket_id: int = Form(...),
    tradingsymbol: str = Form(...),
    exchange: str = Form(...),
    product: str = Form(...),
    instrument_token: Optional[int] = Form(default=None),
):
    _assignments[_pos_key(tradingsymbol, exchange, product)] = basket_id
    return RedirectResponse(url="/management", status_code=302)


@app.post("/baskets/unassign")
async def unassign(tradingsymbol: str = Form(...), exchange: str = Form(...), product: str = Form(...)):
    _assignments.pop(_pos_key(tradingsymbol, exchange, product), None)
    return RedirectResponse(url="/management", status_code=302)


@app.post("/baskets/new-and-assign")
async def new_and_assign(
    basket_name: str = Form(default=""),
    tradingsymbol: str = Form(...),
    exchange: str = Form(...),
    product: str = Form(...),
    instrument_token: Optional[int] = Form(default=None),
):
    global _next_basket_id
    bid = _next_basket_id
    _next_basket_id += 1
    _baskets[bid] = {"id": bid, "name": basket_name.strip() or f"Basket {bid}", "order_type": "LIMIT"}
    _rm[bid] = _empty_rm()
    _assignments[_pos_key(tradingsymbol, exchange, product)] = bid
    return RedirectResponse(url="/management", status_code=302)


@app.post("/baskets/assign-bulk")
async def assign_bulk(request: Request):
    global _next_basket_id
    form = await request.form()
    basket_id   = form.get("basket_id")
    basket_name = (form.get("basket_name") or "").strip()
    symbols     = form.getlist("tradingsymbol")
    exchanges   = form.getlist("exchange")
    products    = form.getlist("product")

    if basket_id:
        bid = int(basket_id)
    else:
        bid = _next_basket_id
        _next_basket_id += 1
        _baskets[bid] = {"id": bid, "name": basket_name or f"Basket {bid}", "order_type": "LIMIT"}
        _rm[bid] = _empty_rm()

    for sym, exch, prod in zip(symbols, exchanges, products):
        _assignments[_pos_key(sym, exch, prod)] = bid
    return RedirectResponse(url="/management", status_code=302)


@app.post("/baskets/unassign-bulk")
async def unassign_bulk(request: Request):
    form = await request.form()
    for sym, exch, prod in zip(form.getlist("tradingsymbol"), form.getlist("exchange"), form.getlist("product")):
        _assignments.pop(_pos_key(sym, exch, prod), None)
    return RedirectResponse(url="/management", status_code=302)


# ── Execution routes (demo) ───────────────────────────────────────────────────

@app.get("/execution", response_class=HTMLResponse)
async def execution_page():
    baskets_list = [{"id": bid, "name": b["name"]} for bid, b in _baskets.items()]
    orders = sorted(_DEMO_ORDERS.values(), key=lambda o: o["placed_at"], reverse=True)
    return render("execution.html", {
        "request":     None,
        "active_page": "execution",
        "orders":      list(orders),
        "baskets":     baskets_list,
        "demo_mode":   False,
        "user_id":     "DEMO",
    })


@app.post("/execution/place")
async def demo_place_orders(request: Request):
    global _next_basket_id
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    legs          = data.get("legs", [])
    basket_id_raw = data.get("basket_id")
    basket_name   = (data.get("basket_name") or "").strip()
    strategy_name = data.get("strategy_name", "")

    if not legs:
        return JSONResponse({"error": "No legs"}, status_code=400)

    # Resolve basket
    if basket_id_raw is None or basket_id_raw == "new":
        bid = _next_basket_id
        _next_basket_id += 1
        name = basket_name or f"{strategy_name or 'Strategy'} {bid}"
        _baskets[bid] = {"id": bid, "name": name, "order_type": "LIMIT"}
        _rm[bid] = _empty_rm()
        basket_name = name
    else:
        bid = int(basket_id_raw)
        basket_name = _baskets.get(bid, {}).get("name", basket_name)

    placed = []
    errors = []
    for leg in legs:
        tsym       = leg.get("tradingsymbol", "")
        exchange   = leg.get("exchange", "NFO")
        product    = leg.get("product", "NRML")
        side       = leg.get("side", "BUY").upper()
        qty        = int(leg.get("qty", 0))
        order_type = leg.get("order_type", "LIMIT").upper()
        price      = leg.get("price")

        if not tsym or qty <= 0:
            errors.append({"leg": leg, "error": "Bad leg"})
            continue

        oid = _demo_new_order_id()
        rec = _demo_order_record(oid, bid, basket_name, tsym, exchange, product,
                                  side, qty, order_type, price, strategy_name)
        rec["placed_at"] = _time_mod.time()
        _DEMO_ORDERS[oid] = rec
        placed.append(rec)

        # Schedule simulated fill
        asyncio.create_task(_simulate_fill(oid, delay=random.uniform(1.5, 3.5)))

    return JSONResponse({
        "basket_id":   bid,
        "basket_name": basket_name,
        "placed":      placed,
        "errors":      errors,
    })


@app.get("/execution/orders")
async def demo_execution_orders():
    orders = sorted(_DEMO_ORDERS.values(), key=lambda o: o["placed_at"], reverse=True)
    return JSONResponse(list(orders))


@app.post("/execution/cancel/{order_id}")
async def demo_cancel(order_id: str):
    rec = _DEMO_ORDERS.get(order_id)
    if rec and rec["status"] == "OPEN":
        rec["status"] = "CANCELLED"
    return JSONResponse({"status": "ok"})


@app.post("/execution/modify/{order_id}")
async def demo_modify(order_id: str, request: Request):
    data = await request.json()
    rec = _DEMO_ORDERS.get(order_id)
    if rec and rec["status"] == "OPEN":
        rec["price"] = float(data.get("price", rec["price"] or 0))
    return JSONResponse({"status": "ok"})


# ── Strategy template routes (demo) ──────────────────────────────────────────

@app.get("/api/vix")
async def api_vix():
    chg_1d   = round(_VIX - _VIX_PREV_CLOSE, 2)
    chg_1d_p = round(chg_1d / _VIX_PREV_CLOSE * 100, 2)
    chg_5d   = round(_VIX - _VIX_5D_AGO, 2)
    chg_5d_p = round(chg_5d / _VIX_5D_AGO * 100, 2)
    return JSONResponse({
        "vix":          _VIX,
        "prev_close":   _VIX_PREV_CLOSE,
        "chg_1d":       chg_1d,
        "chg_1d_pct":   chg_1d_p,
        "chg_5d":       round(_VIX - _VIX_5D_AGO, 2),
        "chg_5d_pct":   chg_5d_p,
        "w52_high":     _VIX_52W_HIGH,
        "w52_low":      _VIX_52W_LOW,
        "ema9":         _VIX_EMA9,
        "ema21":        _VIX_EMA21,
        "sma20":        _VIX_SMA20,
    })


@app.get("/strategies", response_class=HTMLResponse)
async def strategies_page():
    expiries     = _get_expiries()
    baskets_list = [{"id": bid, "name": b["name"]} for bid, b in _baskets.items()]
    templates    = strat_templates.list_templates()
    return render("strategies.html", {
        "request":      None,
        "active_page":  "strategies",
        "underlyings":  list(_UNDERLYINGS.keys()),
        "expiries":     expiries,
        "baskets":      baskets_list,
        "templates":    templates,
        "strategy_types": strat_templates.STRATEGY_TYPES,
        "expiry_rules": strat_templates.EXPIRY_RULES,
        "vix":          _VIX,
        "vix_chg_1d":   round(_VIX - _VIX_PREV_CLOSE, 2),
        "vix_chg_1d_pct": round((_VIX - _VIX_PREV_CLOSE) / _VIX_PREV_CLOSE * 100, 2),
        "vix_chg_5d":   round(_VIX - _VIX_5D_AGO, 2),
        "vix_chg_5d_pct": round((_VIX - _VIX_5D_AGO) / _VIX_5D_AGO * 100, 2),
        "vix_52w_high": _VIX_52W_HIGH,
        "vix_52w_low":  _VIX_52W_LOW,
        "vix_ema9":     _VIX_EMA9,
        "vix_ema21":    _VIX_EMA21,
        "vix_sma20":    _VIX_SMA20,
        "demo_mode":    False,
        "user_id":      "DEMO",
    })


@app.post("/strategies/templates/create")
async def create_template(request: Request):
    data = await request.json()
    t = strat_templates.create_template(data)
    return JSONResponse({"status": "ok", "template": t})


@app.post("/strategies/templates/{tid}/update")
async def update_template(tid: int, request: Request):
    data = await request.json()
    t = strat_templates.update_template(tid, data)
    if not t:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return JSONResponse({"status": "ok", "template": t})


@app.post("/strategies/templates/{tid}/toggle")
async def toggle_template(tid: int):
    t = strat_templates.toggle_enabled(tid)
    if not t:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return JSONResponse({"status": "ok", "template": t})


@app.post("/strategies/templates/{tid}/delete")
async def delete_template_route(tid: int):
    strat_templates.delete_template(tid)
    return JSONResponse({"status": "ok"})


@app.post("/strategies/templates/{tid}/execute-now")
async def execute_now(tid: int):
    """Manually trigger a template immediately, bypassing time/VIX checks."""
    global _next_basket_id
    t = strat_templates.get_template(tid)
    if not t:
        return JSONResponse({"error": "Template not found"}, status_code=404)

    from strategies.engine import execute_template
    import time as _t

    today_str = strat_engine.ist_now().strftime("%Y-%m-%d")

    async def _place(tmpl, legs):
        global _next_basket_id
        bid = _next_basket_id
        _next_basket_id += 1
        name = tmpl.get("name", f"Auto {bid}")
        _baskets[bid] = {"id": bid, "name": name, "order_type": "LIMIT"}
        _rm[bid] = _empty_rm()
        for leg in legs:
            oid = _demo_new_order_id()
            rec = _demo_order_record(
                oid, bid, name,
                leg["tradingsymbol"], leg["exchange"], leg["product"],
                leg["side"], leg["qty"], leg["order_type"], leg["price"],
                strategy_name=strat_templates.STRATEGY_TYPES.get(
                    tmpl.get("strategy_type", ""), tmpl.get("name", "")),
            )
            rec["placed_at"] = _time_mod.time()
            _DEMO_ORDERS[oid] = rec
            asyncio.create_task(_simulate_fill(oid, delay=random.uniform(1.5, 3.0)))
        return bid

    def _set_rm(basket_id, rm):
        _rm[basket_id] = rm

    try:
        strat_templates.set_status(tid, "triggering", today_str, None)
        bid = await execute_template(t, _generate_chain, _place, _set_rm)
        strat_templates.set_status(tid, "active", today_str, bid)
        basket_name = _baskets[bid]["name"]
        return JSONResponse({"status": "ok", "basket_id": bid, "basket_name": basket_name})
    except Exception as e:
        strat_templates.set_status(tid, "error", today_str, None)
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/strategies/templates")
async def list_templates_api():
    return JSONResponse(strat_templates.list_templates())
