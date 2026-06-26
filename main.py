import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from database import init_db
from auth.routes import router as auth_router
from auth.token_store import load_token, load_user_id
from baskets.routes import router as baskets_router
from baskets.service import list_baskets, get_assigned_positions, get_rm
from kite.positions import fetch_positions
from kite import ticker
from kite.orders import place_exit_orders
from rm.engine import run_engine, reset_basket

logging.basicConfig(level=logging.INFO)

# Cache of basket context for the engine (updated on each page load)
_basket_cache: list[dict] = []


def _get_baskets_for_engine() -> list[dict]:
    return _basket_cache


def _exit_fn(basket_id: int, positions: list, reason: str):
    # Find order_type for this basket
    order_type = next(
        (b.get("order_type", "LIMIT") for b in _basket_cache if b["id"] == basket_id),
        "LIMIT"
    )
    asyncio.create_task(place_exit_orders(basket_id, positions, reason, order_type))


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    asyncio.create_task(run_engine(
        get_baskets_fn=_get_baskets_for_engine,
        ltp_fn=ticker.get_ltp,
        exit_fn=_exit_fn,
        no_ltp_fn=lambda: logging.warning("RM engine: no live prices available."),
    ))
    yield
    ticker.stop()


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(auth_router)
app.include_router(baskets_router)

templates = Jinja2Templates(directory="templates")


def _position_key(p: dict) -> str:
    return f"{p['tradingsymbol']}|{p['exchange']}|{p['product']}"


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    if not load_token():
        return RedirectResponse(url="/auth/login")

    try:
        positions = fetch_positions()
    except Exception as e:
        logging.error(f"Failed to fetch positions: {e}")
        return RedirectResponse(url="/auth/login")

    # Refresh ticker subscriptions whenever the page loads
    tokens = [p["instrument_token"] for p in positions if p.get("instrument_token")]
    if tokens:
        ticker.subscribe(tokens)

    # Merge live LTP into positions
    for p in positions:
        live = ticker.get_ltp(p.get("instrument_token", 0))
        if live:
            p["last_price"] = live
            qty = p["quantity"]
            avg = p["average_price"]
            mult = p["multiplier"]
            # Recalculate P&L: (ltp - avg) * qty * multiplier for longs, reversed for shorts
            p["pnl"] = (live - avg) * qty * mult

    assigned = get_assigned_positions()
    baskets = list_baskets()
    global _basket_cache

    # Build basket_id → positions map
    basket_positions: dict[int, list[dict]] = {b["id"]: [] for b in baskets}
    unallocated: list[dict] = []

    for p in positions:
        key = _position_key(p)
        bid = assigned.get(key)
        if bid and bid in basket_positions:
            basket_positions[bid].append(p)
        else:
            unallocated.append(p)

    # Compute basket MTM P&L
    for b in baskets:
        b["order_type"] = b.get("order_type", "LIMIT")
        b["positions"] = basket_positions[b["id"]]
        b["pnl"] = sum(p["pnl"] for p in b["positions"])
        basket_cost = sum(
            abs(p["average_price"]) * abs(p["quantity"]) * p.get("multiplier", 1)
            for p in b["positions"]
        )
        b["pnl_pct"] = (b["pnl"] / basket_cost * 100) if basket_cost else 0.0
        b["rm"] = get_rm(b["id"])
        b["rm_enabled"] = bool(
            b["rm"].get("pt_active") or b["rm"].get("lg_active") or
            b["rm"].get("ps_active") or b["rm"].get("eod_exit")
        )

    # Update engine cache with fully-built basket context
    _basket_cache = baskets

    # KPI counts
    active_baskets = [b for b in baskets if len(b["positions"]) > 0]
    baskets_without_rm = [b for b in active_baskets if not b["rm_enabled"]]

    return templates.TemplateResponse("index.html", {
        "request": request,
        "positions": positions,
        "unallocated": unallocated,
        "baskets": baskets,
        "active_baskets_count": len(active_baskets),
        "baskets_without_rm_count": len(baskets_without_rm),
        "total_pnl": sum(p["pnl"] for p in positions),
        "user_id": load_user_id(),
    })
