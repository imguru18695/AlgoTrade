from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from baskets import service
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
    return RedirectResponse(url="/", status_code=302)


@router.post("/{basket_id}/rename")
async def rename_basket(basket_id: int, name: str = Form(...)):
    service.rename_basket(basket_id, name.strip())
    return RedirectResponse(url="/", status_code=302)


@router.post("/{basket_id}/delete")
async def delete_basket(basket_id: int):
    service.delete_basket(basket_id)
    return RedirectResponse(url="/", status_code=302)


@router.post("/{basket_id}/rm/profit-target")
async def save_profit_target(
    basket_id: int,
    active: Optional[str] = Form(default=None),
    inr: Optional[float] = Form(default=None),
    ticks: Optional[int] = Form(default=None),
):
    service.save_rm_profit_target(basket_id, active == "1", inr, ticks)
    reset_basket(basket_id)
    return RedirectResponse(url="/", status_code=302)


@router.post("/{basket_id}/rm/loss-guard")
async def save_loss_guard(
    basket_id: int,
    active: Optional[str] = Form(default=None),
    inr: Optional[float] = Form(default=None),
    ticks: Optional[int] = Form(default=None),
):
    service.save_rm_loss_guard(basket_id, active == "1", inr, ticks)
    reset_basket(basket_id)
    return RedirectResponse(url="/", status_code=302)


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
    return RedirectResponse(url="/", status_code=302)


@router.post("/{basket_id}/rearm")
async def rearm(basket_id: int):
    rearm_basket(basket_id)
    return RedirectResponse(url="/", status_code=302)


@router.post("/{basket_id}/order-type")
async def save_order_type(basket_id: int, order_type: str = Form(...)):
    service.save_order_type(basket_id, order_type)
    return RedirectResponse(url="/", status_code=302)


@router.post("/{basket_id}/rm/eod-exit")
async def save_eod_exit(
    basket_id: int,
    enabled: Optional[str] = Form(default=None),
):
    service.save_eod_exit(basket_id, enabled == "1")
    return RedirectResponse(url="/", status_code=302)


@router.post("/assign")
async def assign(
    basket_id: int = Form(...),
    tradingsymbol: str = Form(...),
    exchange: str = Form(...),
    product: str = Form(...),
    instrument_token: int | None = Form(default=None),
):
    service.assign_position(basket_id, tradingsymbol, exchange, product, instrument_token)
    return RedirectResponse(url="/", status_code=302)


@router.post("/unassign")
async def unassign(
    tradingsymbol: str = Form(...),
    exchange: str = Form(...),
    product: str = Form(...),
):
    service.unassign_position(tradingsymbol, exchange, product)
    return RedirectResponse(url="/", status_code=302)


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
    service.assign_position(basket["id"], tradingsymbol, exchange, product, instrument_token)
    return RedirectResponse(url="/", status_code=302)


@router.post("/assign-bulk")
async def assign_bulk(request: Request):
    form = await request.form()
    basket_id = form.get("basket_id")
    basket_name = (form.get("basket_name") or "").strip()
    symbols = form.getlist("tradingsymbol")
    exchanges = form.getlist("exchange")
    products = form.getlist("product")
    tokens = form.getlist("instrument_token")

    if basket_id:
        bid = int(basket_id)
    else:
        baskets = service.list_baskets()
        name = basket_name or f"Basket {len(baskets) + 1}"
        basket = service.create_basket(name)
        bid = basket["id"]

    for sym, exch, prod, tok in zip(symbols, exchanges, products, tokens):
        service.assign_position(bid, sym, exch, prod, int(tok) if tok else None)

    return RedirectResponse(url="/", status_code=302)


@router.post("/unassign-bulk")
async def unassign_bulk(request: Request):
    form = await request.form()
    symbols = form.getlist("tradingsymbol")
    exchanges = form.getlist("exchange")
    products = form.getlist("product")
    for sym, exch, prod in zip(symbols, exchanges, products):
        service.unassign_position(sym, exch, prod)
    return RedirectResponse(url="/", status_code=302)
