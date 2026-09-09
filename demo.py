"""
Demo mode — all features work with in-memory state and simulated live prices.
No Kite credentials needed. Prices drift randomly each tick to show live P&L.

Run: uvicorn demo:app --reload --port 8003
"""
import asyncio
import copy
import logging
import random
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader

from rm.engine import run_engine, reset_basket, rearm_basket, get_basket_state

logging.basicConfig(level=logging.INFO)

_exit_log: list[dict] = []


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


# ── Simulated price drift ─────────────────────────────────────────────────────

_PRICES: dict[int, float] = {}   # instrument_token → live price


async def _price_drift_loop():
    """Randomly drift prices every 3 seconds to simulate live ticks."""
    while True:
        await asyncio.sleep(3)
        for p in _POSITIONS:
            tok = p["instrument_token"]
            base = p["average_price"]
            current = _PRICES.get(tok, p["last_price"])
            # drift ±0.5% per tick, clamped to ±40% of average
            drift = current * random.uniform(-0.005, 0.005)
            new_price = max(base * 0.6, min(base * 1.4, current + drift))
            _PRICES[tok] = round(new_price, 2)


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
async def index():
    return render("index.html", _build_context())


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
    })


@app.get("/auth/login", response_class=HTMLResponse)
async def login():
    return RedirectResponse(url="/")


@app.get("/auth/logout")
async def logout():
    return RedirectResponse(url="/", status_code=302)


@app.post("/baskets/create")
async def create_basket(name: str = Form(default="")):
    global _next_basket_id
    bid = _next_basket_id
    _next_basket_id += 1
    _baskets[bid] = {"id": bid, "name": name.strip() or f"Basket {bid}", "order_type": "LIMIT"}
    _rm[bid] = _empty_rm()
    return RedirectResponse(url="/", status_code=302)


@app.post("/baskets/{basket_id}/rename")
async def rename_basket(basket_id: int, name: str = Form(...)):
    if basket_id in _baskets:
        _baskets[basket_id]["name"] = name.strip()
    return RedirectResponse(url="/", status_code=302)


@app.post("/baskets/{basket_id}/delete")
async def delete_basket(basket_id: int):
    _baskets.pop(basket_id, None)
    _rm.pop(basket_id, None)
    for k in [k for k, v in _assignments.items() if v == basket_id]:
        del _assignments[k]
    return RedirectResponse(url="/", status_code=302)


@app.post("/baskets/{basket_id}/order-type")
async def save_order_type(basket_id: int, order_type: str = Form(...)):
    if basket_id in _baskets:
        _baskets[basket_id]["order_type"] = order_type if order_type in ("LIMIT", "MARKET") else "LIMIT"
    return RedirectResponse(url="/", status_code=302)


@app.post("/baskets/{basket_id}/rearm")
async def rearm(basket_id: int):
    rearm_basket(basket_id)
    return RedirectResponse(url="/", status_code=302)


@app.post("/baskets/{basket_id}/rm/profit-target")
async def save_pt(basket_id: int, request: Request):
    form = await request.form()
    rm = _rm.setdefault(basket_id, _empty_rm())
    rm["pt_active"] = form.get("active") == "1"
    rm["pt_inr"]    = float(form["inr"])   if form.get("inr")   else None
    rm["pt_ticks"]  = int(form["ticks"])   if form.get("ticks") else None
    reset_basket(basket_id)
    return RedirectResponse(url="/", status_code=302)


@app.post("/baskets/{basket_id}/rm/loss-guard")
async def save_lg(basket_id: int, request: Request):
    form = await request.form()
    rm = _rm.setdefault(basket_id, _empty_rm())
    rm["lg_active"] = form.get("active") == "1"
    rm["lg_inr"]    = float(form["inr"])   if form.get("inr")   else None
    rm["lg_ticks"]  = int(form["ticks"])   if form.get("ticks") else None
    reset_basket(basket_id)
    return RedirectResponse(url="/", status_code=302)


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
    return RedirectResponse(url="/", status_code=302)


@app.post("/baskets/{basket_id}/rm/eod-exit")
async def save_eod_exit(basket_id: int, request: Request):
    form = await request.form()
    rm = _rm.setdefault(basket_id, _empty_rm())
    rm["eod_exit"] = form.get("enabled") == "1"
    return RedirectResponse(url="/", status_code=302)


@app.post("/baskets/{basket_id}/rm/delete-on-fire")
async def save_delete_on_fire(basket_id: int, request: Request):
    form = await request.form()
    rm = _rm.setdefault(basket_id, _empty_rm())
    rm["delete_on_fire"] = 1 if form.get("enabled") == "1" else 0
    return RedirectResponse(url="/", status_code=302)


@app.post("/baskets/assign")
async def assign(
    basket_id: int = Form(...),
    tradingsymbol: str = Form(...),
    exchange: str = Form(...),
    product: str = Form(...),
    instrument_token: Optional[int] = Form(default=None),
):
    _assignments[_pos_key(tradingsymbol, exchange, product)] = basket_id
    return RedirectResponse(url="/", status_code=302)


@app.post("/baskets/unassign")
async def unassign(tradingsymbol: str = Form(...), exchange: str = Form(...), product: str = Form(...)):
    _assignments.pop(_pos_key(tradingsymbol, exchange, product), None)
    return RedirectResponse(url="/", status_code=302)


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
    return RedirectResponse(url="/", status_code=302)


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
    return RedirectResponse(url="/", status_code=302)


@app.post("/baskets/unassign-bulk")
async def unassign_bulk(request: Request):
    form = await request.form()
    for sym, exch, prod in zip(form.getlist("tradingsymbol"), form.getlist("exchange"), form.getlist("product")):
        _assignments.pop(_pos_key(sym, exch, prod), None)
    return RedirectResponse(url="/", status_code=302)
