from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from baskets import service
from instruments import underlying_of
from rm.engine import reset_basket, rearm_basket
from typing import Optional

router = APIRouter(prefix="/baskets")
templates = Jinja2Templates(directory="templates")


@router.post("/create")
async def create_basket(name: str = Form(default="")):
    name = name.strip() or None
    baskets = service.list_baskets()
    auto_name = name or f"Basket {len(baskets) + 1}"
    service.create_basket(auto_name)
    return RedirectResponse(url="/management", status_code=302)


@router.post("/{basket_id}/rename")
async def rename_basket(basket_id: int, name: str = Form(...)):
    service.rename_basket(basket_id, name.strip())
    return RedirectResponse(url="/management", status_code=302)


@router.post("/{basket_id}/delete")
async def delete_basket(basket_id: int):
    service.delete_basket(basket_id)
    return RedirectResponse(url="/management", status_code=302)


@router.post("/{basket_id}/rm/profit-target")
async def save_profit_target(
    basket_id: int,
    active: Optional[str] = Form(default=None),
    inr: Optional[float] = Form(default=None),
    ticks: Optional[str] = Form(default=None),
):
    ticks_int = int(ticks) if ticks and ticks.strip() else None
    service.save_rm_profit_target(basket_id, active == "1", inr, ticks_int)
    reset_basket(basket_id)
    return RedirectResponse(url="/management", status_code=302)


@router.post("/{basket_id}/rm/loss-guard")
async def save_loss_guard(
    basket_id: int,
    active: Optional[str] = Form(default=None),
    inr: Optional[float] = Form(default=None),
    ticks: Optional[str] = Form(default=None),
):
    ticks_int = int(ticks) if ticks and ticks.strip() else None
    service.save_rm_loss_guard(basket_id, active == "1", inr, ticks_int)
    reset_basket(basket_id)
    return RedirectResponse(url="/management", status_code=302)


@router.post("/{basket_id}/rm/profit-shield")
async def save_profit_shield(
    basket_id: int,
    active: Optional[str] = Form(default=None),
    trigger: Optional[float] = Form(default=None),
    lock: Optional[float] = Form(default=None),
    step_profit: Optional[float] = Form(default=None),
    step_lock: Optional[float] = Form(default=None),
):
    service.save_rm_profit_shield(basket_id, active == "1", trigger, lock, step_profit, step_lock)
    reset_basket(basket_id)
    return RedirectResponse(url="/management", status_code=302)


@router.post("/{basket_id}/rm/spot-guard")
async def save_spot_guard(
    basket_id: int,
    active: Optional[str] = Form(default=None),
    lower: Optional[float] = Form(default=None),
    upper: Optional[float] = Form(default=None),
    ticks: Optional[str] = Form(default=None),
):
    ticks_int = int(ticks) if ticks and ticks.strip() else None
    service.save_rm_spot_guard(basket_id, active == "1", lower, upper, ticks_int)
    reset_basket(basket_id)
    return RedirectResponse(url="/management", status_code=302)


@router.post("/{basket_id}/rm/velocity-guard")
async def save_velocity_guard(
    basket_id: int,
    active: Optional[str] = Form(default=None),
    pct: Optional[float] = Form(default=None),
    minutes: Optional[str] = Form(default=None),
):
    minutes_int = int(minutes) if minutes and minutes.strip() else None
    service.save_rm_velocity_guard(basket_id, active == "1", pct, minutes_int)
    reset_basket(basket_id)
    return RedirectResponse(url="/management", status_code=302)


@router.post("/{basket_id}/rearm")
async def rearm(basket_id: int):
    rearm_basket(basket_id)
    return RedirectResponse(url="/management", status_code=302)


@router.post("/{basket_id}/order-type")
async def save_order_type(basket_id: int, order_type: str = Form(...)):
    service.save_order_type(basket_id, order_type)
    return RedirectResponse(url="/management", status_code=302)


@router.post("/{basket_id}/rm/delete-on-fire")
async def save_delete_on_fire(
    basket_id: int,
    enabled: Optional[str] = Form(default=None),
):
    service.save_delete_on_fire(basket_id, enabled == "1")
    return RedirectResponse(url="/management", status_code=302)


@router.post("/{basket_id}/rm/eod-exit")
async def save_eod_exit(
    basket_id: int,
    enabled: Optional[str] = Form(default=None),
):
    service.save_eod_exit(basket_id, enabled == "1")
    return RedirectResponse(url="/management", status_code=302)


@router.post("/assign")
async def assign(
    basket_id: int = Form(...),
    tradingsymbol: str = Form(...),
    exchange: str = Form(...),
    product: str = Form(...),
    instrument_token: int | None = Form(default=None),
):
    try:
        service.assign_position(basket_id, tradingsymbol, exchange, product, instrument_token)
    except service.MixedUnderlyingError as e:
        return JSONResponse({"error": "mixed_underlying", "message": str(e)}, status_code=400)
    return RedirectResponse(url="/management", status_code=302)


@router.post("/unassign")
async def unassign(
    tradingsymbol: str = Form(...),
    exchange: str = Form(...),
    product: str = Form(...),
):
    service.unassign_position(tradingsymbol, exchange, product)
    return RedirectResponse(url="/management", status_code=302)


@router.post("/new-and-assign")
async def new_and_assign(
    basket_name: str = Form(default=""),
    tradingsymbol: str = Form(...),
    exchange: str = Form(...),
    product: str = Form(...),
    instrument_token: int | None = Form(default=None),
):
    baskets = service.list_baskets()
    name = basket_name.strip() or f"Basket {len(baskets) + 1}"
    basket = service.create_basket(name)
    try:
        service.assign_position(basket["id"], tradingsymbol, exchange, product, instrument_token)
    except service.MixedUnderlyingError as e:
        # Can't actually happen for a brand-new empty basket's first leg —
        # guarded anyway so this route can never surface a raw 500.
        return JSONResponse({"error": "mixed_underlying", "message": str(e)}, status_code=400)
    return RedirectResponse(url="/management", status_code=302)


@router.post("/assign-bulk")
async def assign_bulk(request: Request):
    form = await request.form()
    basket_id = form.get("basket_id")
    basket_name = (form.get("basket_name") or "").strip()
    symbols = form.getlist("tradingsymbol")
    exchanges = form.getlist("exchange")
    products = form.getlist("product")
    tokens = form.getlist("instrument_token")

    # Validate the WHOLE batch upfront, against whatever the target basket
    # already holds — all-or-nothing, so a conflict on symbol 3 of 5 never
    # leaves the first 2 assigned and the rest not.
    existing = service.get_basket_underlyings(int(basket_id)) if basket_id else set()
    incoming = {u for sym in symbols if (u := underlying_of(sym))}
    combined = existing | incoming
    if len(combined) > 1:
        return JSONResponse({
            "error": "mixed_underlying",
            "message": f"These positions span more than one underlying ({', '.join(sorted(combined))}) — a basket can only hold one.",
        }, status_code=400)

    if basket_id:
        bid = int(basket_id)
    else:
        baskets = service.list_baskets()
        name = basket_name or f"Basket {len(baskets) + 1}"
        basket = service.create_basket(name)
        bid = basket["id"]

    for sym, exch, prod, tok in zip(symbols, exchanges, products, tokens):
        service.assign_position(bid, sym, exch, prod, int(tok) if tok else None)

    return RedirectResponse(url="/management", status_code=302)


@router.post("/unassign-bulk")
async def unassign_bulk(request: Request):
    form = await request.form()
    symbols = form.getlist("tradingsymbol")
    exchanges = form.getlist("exchange")
    products = form.getlist("product")
    for sym, exch, prod in zip(symbols, exchanges, products):
        service.unassign_position(sym, exch, prod)
    return RedirectResponse(url="/management", status_code=302)
