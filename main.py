import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from database import init_db
from auth.routes import router as auth_router
from auth.token_store import load_token, load_user_id
from baskets.routes import router as baskets_router
from logs.routes import router as logs_router
from baskets.service import list_baskets, get_assigned_positions, get_rm, get_order_type
from kite.client import get_kite
from kite.positions import fetch_positions
from kite import ticker
from kite.orders import place_exit_orders
from rm.engine import run_engine, reset_basket, get_basket_state

logging.basicConfig(level=logging.INFO)

# In-memory caches updated on each page load
_basket_cache: list[dict] = []
_all_positions_cache: list[dict] = []   # all positions with LTP applied, used by /pnl


def _get_baskets_for_engine() -> list[dict]:
    return _basket_cache


def _compute_pnl(p: dict) -> tuple[float, float]:
    """Return (pnl, pnl_pct) for a position using live LTP or Kite last_price fallback."""
    ltp  = ticker.get_ltp(p.get("instrument_token", 0)) or p.get("last_price", 0)
    qty  = p["quantity"]
    avg  = p["average_price"]
    mult = p.get("multiplier", 1)
    pnl  = (ltp - avg) * qty * mult
    cost = abs(avg) * abs(qty) * mult
    pnl_pct = (pnl / cost * 100) if cost else 0.0
    return ltp, pnl, pnl_pct


async def _exit_fn(basket_id: int, positions: list, reason: str, event_id: int | None = None):
    order_type = await asyncio.to_thread(get_order_type, basket_id)
    await place_exit_orders(basket_id, positions, reason, order_type, event_id)


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
app.include_router(logs_router)

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

    # Seed ltp_store with fresh quote prices before computing P&L.
    # Prevents overnight positions from showing prev-day settlement price
    # when the WebSocket ticker hasn't yet received its first tick.
    ticker.seed_ltp(positions, get_kite())

    # Refresh ticker subscriptions whenever the page loads
    tokens = [p["instrument_token"] for p in positions if p.get("instrument_token")]
    if tokens:
        ticker.subscribe(tokens)

    # Always recompute P&L from entry price — fixes overnight positions and ticker race.
    # Prefers live LTP from WebSocket ticker; falls back to Kite's last_price field.
    for p in positions:
        ltp, pnl, pnl_pct = _compute_pnl(p)
        p["last_price"] = ltp
        p["pnl"]        = pnl
        p["pnl_pct"]    = pnl_pct

    assigned = get_assigned_positions()
    baskets = list_baskets()
    global _basket_cache, _all_positions_cache

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
        b["fired"] = get_basket_state(b["id"]).get("fired", False)

    # Update caches
    _basket_cache = baskets
    _all_positions_cache = positions

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


@app.get("/pnl")
async def get_pnl():
    """Lightweight P&L endpoint — recomputes from ticker/last_price without a Kite API call."""
    positions_data: dict[str, dict] = {}
    total_pnl = 0.0

    for p in _all_positions_cache:
        ltp, pnl, pnl_pct = _compute_pnl(p)
        key = f"{p['tradingsymbol']}|{p['exchange']}|{p['product']}"
        positions_data[key] = {"ltp": ltp, "pnl": pnl, "pnl_pct": pnl_pct}
        total_pnl += pnl

    baskets_data: dict[str, dict] = {}
    for b in _basket_cache:
        basket_pnl = sum(
            positions_data.get(
                f"{p['tradingsymbol']}|{p['exchange']}|{p['product']}", {}
            ).get("pnl", 0)
            for p in b.get("positions", [])
        )
        basket_cost = sum(
            abs(p["average_price"]) * abs(p["quantity"]) * p.get("multiplier", 1)
            for p in b.get("positions", [])
        )
        basket_pnl_pct = (basket_pnl / basket_cost * 100) if basket_cost else 0.0
        baskets_data[str(b["id"])] = {"pnl": basket_pnl, "pnl_pct": basket_pnl_pct}

    return JSONResponse({"total_pnl": total_pnl, "positions": positions_data, "baskets": baskets_data})
