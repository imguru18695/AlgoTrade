"""
Execution routes — order placement, status, cancel, modify.
"""
import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from auth.token_store import load_token, load_user_id
from baskets.service import list_baskets, create_basket, assign_position
from . import engine

log = logging.getLogger(__name__)
router = APIRouter(prefix="/execution")
templates = Jinja2Templates(directory="templates")


# ── Page ─────────────────────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
async def execution_page(request: Request):
    if not load_token():
        return RedirectResponse(url="/auth/login")
    baskets = await asyncio.to_thread(list_baskets)
    return templates.TemplateResponse("execution.html", {
        "request":     request,
        "active_page": "execution",
        "orders":      engine.get_orders(),
        "baskets":     baskets,
        "user_id":     load_user_id(),
    })


# ── Place ─────────────────────────────────────────────────────────────────────

@router.post("/place")
async def place_orders(request: Request):
    """
    Accepts JSON body:
    {
        "basket_id":     <int | null>,     # null → create new basket
        "basket_name":   "...",            # used when basket_id is null
        "strategy_name": "Short Straddle",
        "legs": [
            {
                "tradingsymbol": "NIFTY25...",
                "exchange": "NFO",
                "product": "NRML",
                "side": "BUY" | "SELL",
                "qty": 25,
                "order_type": "LIMIT" | "MARKET",
                "price": 245.0         # for LIMIT orders
            }, ...
        ]
    }
    Returns:
    {
        "basket_id": <int>,
        "basket_name": "...",
        "placed":  [order records],
        "errors":  [{"leg": ..., "error": "..."}]
    }
    """
    if not load_token():
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    legs          = data.get("legs", [])
    basket_id_raw = data.get("basket_id")
    basket_name   = (data.get("basket_name") or "").strip()
    strategy_name = data.get("strategy_name", "")

    if not legs:
        return JSONResponse({"error": "No legs provided"}, status_code=400)

    # Resolve basket
    if basket_id_raw is None or basket_id_raw == "new":
        # Create a new basket
        name = basket_name or f"{strategy_name or 'Strategy'} {int(asyncio.get_event_loop().time())}"
        basket = await asyncio.to_thread(create_basket, name)
        basket_id   = basket["id"]
        basket_name = basket["name"]
    else:
        basket_id   = int(basket_id_raw)
        # Fetch basket name from DB for logging
        all_baskets = await asyncio.to_thread(list_baskets)
        match       = next((b for b in all_baskets if b["id"] == basket_id), None)
        basket_name = match["name"] if match else basket_name

    placed: list[dict] = []
    errors: list[dict] = []

    for leg in legs:
        tsym       = leg.get("tradingsymbol", "")
        exchange   = leg.get("exchange", "NFO")
        product    = leg.get("product", "NRML")
        side       = leg.get("side", "BUY").upper()
        qty        = int(leg.get("qty", 0))
        order_type = leg.get("order_type", "LIMIT").upper()
        price      = leg.get("price")

        if not tsym or qty <= 0:
            errors.append({"leg": leg, "error": "Missing tradingsymbol or qty"})
            continue

        try:
            rec = await engine.place_leg(
                basket_id     = basket_id,
                basket_name   = basket_name,
                tradingsymbol = tsym,
                exchange      = exchange,
                product       = product,
                side          = side,
                qty           = qty,
                order_type    = order_type,
                price         = price,
                strategy_name = strategy_name,
            )
            placed.append(rec)
        except Exception as e:
            log.error(f"Execution /place leg error: {e}")
            errors.append({"leg": leg, "error": str(e)})

    return JSONResponse({
        "basket_id":   basket_id,
        "basket_name": basket_name,
        "placed":      placed,
        "errors":      errors,
    })


# ── Live order book (polling) ─────────────────────────────────────────────────

@router.get("/orders")
async def orders_json():
    """Lightweight endpoint polled by the UI every 3 seconds."""
    return JSONResponse(engine.get_orders())


# ── Cancel ────────────────────────────────────────────────────────────────────

@router.post("/cancel/{order_id}")
async def cancel(order_id: str):
    if not load_token():
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    try:
        await engine.cancel_order(order_id)
        return JSONResponse({"status": "ok"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


# ── Modify ────────────────────────────────────────────────────────────────────

@router.post("/modify/{order_id}")
async def modify(order_id: str, request: Request):
    if not load_token():
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    try:
        data      = await request.json()
        new_price = float(data["price"])
        await engine.modify_order(order_id, new_price)
        return JSONResponse({"status": "ok", "price": new_price})
    except (KeyError, ValueError) as e:
        return JSONResponse({"error": f"Invalid price: {e}"}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
