"""
Fully functional demo — all features work with in-memory state.
No Kite credentials needed. Run: uvicorn demo:app --reload --port 8001
"""
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
from typing import Optional
import copy

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

_env = Environment(loader=FileSystemLoader("templates"), cache_size=0, auto_reload=True)


def render(template_name: str, context: dict) -> HTMLResponse:
    tmpl = _env.get_template(template_name)
    return HTMLResponse(tmpl.render(**context))


# ── In-memory state ───────────────────────────────────────────────────────────

def _with_pct(p: dict) -> dict:
    cost = abs(p["average_price"]) * abs(p["quantity"]) * p.get("multiplier", 1)
    p["pnl_pct"] = (p["pnl"] / cost * 100) if cost else 0.0
    return p

_POSITIONS = [_with_pct(p) for p in [
    {"tradingsymbol": "NIFTY2562524000CE", "exchange": "NFO", "product": "NRML",
     "quantity": 2, "average_price": 210.50, "last_price": 245.00,
     "pnl": 4100.0, "instrument_token": 123001, "multiplier": 50},
    {"tradingsymbol": "NIFTY2562524000PE", "exchange": "NFO", "product": "NRML",
     "quantity": -2, "average_price": 195.00, "last_price": 180.00,
     "pnl": 1500.0, "instrument_token": 123002, "multiplier": 50},
    {"tradingsymbol": "BANKNIFTY2562552000CE", "exchange": "NFO", "product": "NRML",
     "quantity": -1, "average_price": 490.00, "last_price": 430.00,
     "pnl": 1500.0, "instrument_token": 123003, "multiplier": 15},
    {"tradingsymbol": "BANKNIFTY2562552000PE", "exchange": "NFO", "product": "NRML",
     "quantity": -1, "average_price": 460.00, "last_price": 410.00,
     "pnl": 1250.0, "instrument_token": 123004, "multiplier": 15},
    {"tradingsymbol": "FINNIFTY2562523000CE", "exchange": "NFO", "product": "NRML",
     "quantity": 1, "average_price": 120.00, "last_price": 98.00,
     "pnl": -1100.0, "instrument_token": 123005, "multiplier": 40},
]]

# basket_id → {id, name}
_baskets: dict[int, dict] = {
    1: {"id": 1, "name": "BNF Short Straddle"},
    2: {"id": 2, "name": "Nifty Hedge"},
}

# position_key → basket_id
_assignments: dict[str, int] = {
    "BANKNIFTY2562552000CE|NFO|NRML": 1,
    "BANKNIFTY2562552000PE|NFO|NRML": 1,
}

def _empty_rm() -> dict:
    return {
        "pt_active": False, "pt_inr": None, "pt_ticks": None,
        "lg_active": False, "lg_inr": None, "lg_ticks": None,
        "ps_active": False, "ps_trigger": None, "ps_lock": None,
        "ps_step_profit": None, "ps_step_lock": None,
    }

# basket_id → rm config dict
_rm: dict[int, dict] = {
    1: {
        "pt_active": True,  "pt_inr": 15000, "pt_ticks": 3,
        "lg_active": True,  "lg_inr": 10000, "lg_ticks": 5,
        "ps_active": False, "ps_trigger": None, "ps_lock": None,
        "ps_step_profit": None, "ps_step_lock": None,
    },
    2: _empty_rm(),
}

_next_basket_id = 3


def _pos_key(tradingsymbol: str, exchange: str, product: str) -> str:
    return f"{tradingsymbol}|{exchange}|{product}"


# ── View helpers ──────────────────────────────────────────────────────────────

def _build_context():
    positions = copy.deepcopy(_POSITIONS)
    baskets = []

    for bid, b in _baskets.items():
        rm = _rm.get(bid, {})
        rm_enabled = rm.get("pt_active") or rm.get("lg_active") or rm.get("ps_active")
        basket_positions = [
            p for p in positions
            if _assignments.get(_pos_key(p["tradingsymbol"], p["exchange"], p["product"])) == bid
        ]
        basket_pnl = sum(p["pnl"] for p in basket_positions)
        basket_cost = sum(
            abs(p["average_price"]) * abs(p["quantity"]) * p.get("multiplier", 1)
            for p in basket_positions
        )
        baskets.append({
            "id": bid,
            "name": b["name"],
            "positions": basket_positions,
            "pnl": basket_pnl,
            "pnl_pct": (basket_pnl / basket_cost * 100) if basket_cost else 0.0,
            "rm": rm,
            "rm_enabled": rm_enabled,
        })

    assigned_keys = set(_assignments.keys())
    unallocated = [
        p for p in positions
        if _pos_key(p["tradingsymbol"], p["exchange"], p["product"]) not in assigned_keys
    ]

    active_baskets = [b for b in baskets if b["positions"]]
    baskets_without_rm = [b for b in active_baskets if not b["rm_enabled"]]

    return {
        "positions": positions,
        "unallocated": unallocated,
        "baskets": baskets,
        "active_baskets_count": len(active_baskets),
        "baskets_without_rm_count": len(baskets_without_rm),
        "total_pnl": sum(p["pnl"] for p in positions),
        "demo_mode": True,
        "user_id": "AB1234",
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
async def index():
    return render("index.html", _build_context())


# Basket CRUD

@app.post("/baskets/create")
async def create_basket(name: str = Form(default="")):
    global _next_basket_id
    bid = _next_basket_id
    _next_basket_id += 1
    auto_name = name.strip() or f"Basket {bid}"
    _baskets[bid] = {"id": bid, "name": auto_name}
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
    # Unassign all positions from this basket
    to_remove = [k for k, v in _assignments.items() if v == basket_id]
    for k in to_remove:
        del _assignments[k]
    return RedirectResponse(url="/", status_code=302)


@app.post("/baskets/{basket_id}/rm")
async def save_rm(
    basket_id: int,
    max_loss: Optional[float] = Form(default=None),
    target_profit: Optional[float] = Form(default=None),
    trail_profit: Optional[float] = Form(default=None),
    trail_trigger: Optional[float] = Form(default=None),
):
    _rm[basket_id] = {
        "max_loss": max_loss,
        "target_profit": target_profit,
        "trail_profit": trail_profit,
        "trail_trigger": trail_trigger,
    }
    return RedirectResponse(url="/", status_code=302)


# Position assignment

@app.post("/baskets/assign")
async def assign(
    basket_id: int = Form(...),
    tradingsymbol: str = Form(...),
    exchange: str = Form(...),
    product: str = Form(...),
    instrument_token: Optional[int] = Form(default=None),
):
    key = _pos_key(tradingsymbol, exchange, product)
    _assignments[key] = basket_id
    return RedirectResponse(url="/", status_code=302)


@app.post("/baskets/unassign")
async def unassign(
    tradingsymbol: str = Form(...),
    exchange: str = Form(...),
    product: str = Form(...),
):
    key = _pos_key(tradingsymbol, exchange, product)
    _assignments.pop(key, None)
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
    name = basket_name.strip() or f"Basket {bid}"
    _baskets[bid] = {"id": bid, "name": name}
    _rm[bid] = {"max_loss": None, "target_profit": None, "trail_profit": None, "trail_trigger": None}
    key = _pos_key(tradingsymbol, exchange, product)
    _assignments[key] = bid
    return RedirectResponse(url="/", status_code=302)


@app.post("/baskets/{basket_id}/rm/profit-target")
async def save_pt(basket_id: int, request: Request):
    form = await request.form()
    rm = _rm.setdefault(basket_id, _empty_rm())
    rm["pt_active"] = form.get("active") == "1"
    rm["pt_inr"] = float(form["inr"]) if form.get("inr") else None
    rm["pt_ticks"] = int(form["ticks"]) if form.get("ticks") else None
    return RedirectResponse(url="/", status_code=302)


@app.post("/baskets/{basket_id}/rm/loss-guard")
async def save_lg(basket_id: int, request: Request):
    form = await request.form()
    rm = _rm.setdefault(basket_id, _empty_rm())
    rm["lg_active"] = form.get("active") == "1"
    rm["lg_inr"] = float(form["inr"]) if form.get("inr") else None
    rm["lg_ticks"] = int(form["ticks"]) if form.get("ticks") else None
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
    return RedirectResponse(url="/", status_code=302)


@app.post("/baskets/assign-bulk")
async def assign_bulk(request: Request):
    form = await request.form()
    basket_id = form.get("basket_id")
    basket_name = form.get("basket_name", "").strip()
    symbols = form.getlist("tradingsymbol")
    exchanges = form.getlist("exchange")
    products = form.getlist("product")
    tokens = form.getlist("instrument_token")

    # Resolve or create basket
    if basket_id:
        bid = int(basket_id)
    else:
        global _next_basket_id
        bid = _next_basket_id
        _next_basket_id += 1
        name = basket_name or f"Basket {bid}"
        _baskets[bid] = {"id": bid, "name": name}
        _rm[bid] = _empty_rm()

    for sym, exch, prod in zip(symbols, exchanges, products):
        _assignments[_pos_key(sym, exch, prod)] = bid

    return RedirectResponse(url="/", status_code=302)


@app.post("/baskets/unassign-bulk")
async def unassign_bulk(request: Request):
    form = await request.form()
    symbols = form.getlist("tradingsymbol")
    exchanges = form.getlist("exchange")
    products = form.getlist("product")
    for sym, exch, prod in zip(symbols, exchanges, products):
        _assignments.pop(_pos_key(sym, exch, prod), None)
    return RedirectResponse(url="/", status_code=302)


# Stub auth routes so logout link doesn't 404
@app.get("/auth/logout")
async def logout():
    return RedirectResponse(url="/", status_code=302)
