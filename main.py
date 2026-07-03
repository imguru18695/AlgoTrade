import asyncio
import logging
import time
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

# In-memory caches — updated only by _refresh_cache(), never by page loads directly
_basket_cache: list[dict] = []
_all_positions_cache: list[dict] = []
_unallocated_cache: list[dict] = []
_last_refresh_ts: float = 0.0   # monotonic time of last successful _refresh_cache

CACHE_REFRESH_INTERVAL = 60   # seconds between background cache refreshes
MAX_CACHE_AGE          = 180  # seconds; engine pauses if cache is older than this

# Strong references to background tasks prevent GC (Python only keeps weak refs via event loop)
_background_tasks: set[asyncio.Task] = set()


def _get_baskets_for_engine() -> list[dict]:
    age = time.monotonic() - _last_refresh_ts
    if age > MAX_CACHE_AGE:
        logging.warning(
            f"RM engine: basket cache is {age:.0f}s old (>{MAX_CACHE_AGE}s) — "
            "pausing all RM checks until cache is refreshed."
        )
        return []
    return _basket_cache


def _compute_pnl(p: dict) -> tuple[float, float, float]:
    """Return (ltp, pnl, pnl_pct) using live ticker LTP or quote fallback."""
    ltp = ticker.get_ltp(p.get("instrument_token", 0))
    if ltp is None:  # explicit None check — 0.0 is a valid circuit-halt price
        ltp = p.get("last_price", 0)
    qty  = p["quantity"]
    avg  = p["average_price"]
    mult = p.get("multiplier", 1)
    pnl  = (ltp - avg) * qty * mult
    cost = abs(avg) * abs(qty) * mult
    pnl_pct = (pnl / cost * 100) if cost else 0.0
    return ltp, pnl, pnl_pct


def _position_key(p: dict) -> str:
    return f"{p['tradingsymbol']}|{p['exchange']}|{p['product']}"


async def _exit_fn(basket_id: int, positions: list, reason: str, event_id: int | None = None):
    order_type = await asyncio.to_thread(get_order_type, basket_id)
    await place_exit_orders(basket_id, positions, reason, order_type, event_id)


async def _refresh_cache():
    """Fetch positions from Kite, seed LTP, rebuild basket + position caches.

    This is the ONLY place that writes to _basket_cache / _all_positions_cache.
    Called at startup, every CACHE_REFRESH_INTERVAL seconds by the background
    loop, and on each page load (so browser-active sessions get instant updates).
    The RM engine reads from these caches — it never depends on a page load.
    """
    global _basket_cache, _all_positions_cache, _unallocated_cache, _last_refresh_ts

    try:
        positions = await asyncio.to_thread(fetch_positions)
    except Exception as e:
        logging.error(f"Cache refresh: fetch_positions failed: {e}")
        return  # Keep existing cache — better stale than empty

    # Seed ltp_store for tokens the WebSocket hasn't seen yet (overnight positions,
    # fresh startup before first tick). seed_ltp skips tokens already priced by
    # the ticker so it never overwrites fresher data.
    try:
        await asyncio.to_thread(ticker.seed_ltp, positions, get_kite())
    except Exception as e:
        logging.warning(f"Cache refresh: LTP seeding failed: {e}")
        # Continue — ticker WebSocket may already have live data

    # Create / update WebSocket subscription (idempotent — no reconnect if already live)
    tokens = [p["instrument_token"] for p in positions if p.get("instrument_token")]
    if tokens:
        ticker.subscribe(tokens)

    # Apply live LTP to each position
    for p in positions:
        ltp, pnl, pnl_pct = _compute_pnl(p)
        p["last_price"] = ltp
        p["pnl"]        = pnl
        p["pnl_pct"]    = pnl_pct

    # Build basket → positions mapping from DB
    assigned = get_assigned_positions()
    baskets  = list_baskets()

    basket_positions: dict[int, list[dict]] = {b["id"]: [] for b in baskets}
    unallocated: list[dict] = []

    for p in positions:
        key = _position_key(p)
        bid = assigned.get(key)
        if bid and bid in basket_positions:
            basket_positions[bid].append(p)
        else:
            unallocated.append(p)

    for b in baskets:
        b["order_type"] = b.get("order_type", "LIMIT")
        b["positions"]  = basket_positions[b["id"]]
        b["pnl"]        = sum(p["pnl"] for p in b["positions"])
        basket_cost     = sum(
            abs(p["average_price"]) * abs(p["quantity"]) * p.get("multiplier", 1)
            for p in b["positions"]
        )
        b["pnl_pct"]    = (b["pnl"] / basket_cost * 100) if basket_cost else 0.0
        b["rm"]         = get_rm(b["id"])
        b["rm_enabled"] = bool(
            b["rm"].get("pt_active") or b["rm"].get("lg_active") or
            b["rm"].get("ps_active") or b["rm"].get("eod_exit")
        )
        b["fired"]      = get_basket_state(b["id"]).get("fired", False)

    _basket_cache        = baskets
    _all_positions_cache = positions
    _unallocated_cache   = unallocated
    _last_refresh_ts     = time.monotonic()


async def _refresh_loop():
    """Background task — keeps caches and ticker fresh without any page loads.
    Runs every CACHE_REFRESH_INTERVAL seconds so the RM engine has current data
    even when no browser session is active.
    """
    while True:
        await asyncio.sleep(CACHE_REFRESH_INTERVAL)
        try:
            await _refresh_cache()
            logging.debug("Background cache refresh complete.")
        except Exception as e:
            logging.error(f"Background cache refresh failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Pre-populate caches before starting the engine so it has data immediately
    # rather than waiting for a page load or the first 60-second timer.
    try:
        await _refresh_cache()
        logging.info("Startup cache loaded.")
    except Exception as e:
        logging.error(f"Startup cache load failed: {e}")

    def _keep(task: asyncio.Task):
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)

    _keep(asyncio.create_task(_refresh_loop()))
    _keep(asyncio.create_task(run_engine(
        get_baskets_fn=_get_baskets_for_engine,
        ltp_fn=ticker.get_ltp,
        exit_fn=_exit_fn,
        no_ltp_fn=lambda: logging.warning("RM engine: no live prices available."),
    )))
    yield
    ticker.stop()


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(auth_router)
app.include_router(baskets_router)
app.include_router(logs_router)

templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    if not load_token():
        return RedirectResponse(url="/auth/login")

    # Refresh cache on page load — gives the browser a fully-current view and
    # keeps engine data fresh while a user is actively monitoring.
    try:
        await _refresh_cache()
    except Exception as e:
        logging.error(f"Page load cache refresh failed: {e}")
        if not _all_positions_cache and not _basket_cache:
            return RedirectResponse(url="/auth/login")

    positions   = _all_positions_cache
    baskets     = _basket_cache
    unallocated = _unallocated_cache

    active_baskets      = [b for b in baskets if len(b["positions"]) > 0]
    baskets_without_rm  = [b for b in active_baskets if not b["rm_enabled"]]

    return templates.TemplateResponse("index.html", {
        "request":                  request,
        "positions":                positions,
        "unallocated":              unallocated,
        "baskets":                  baskets,
        "active_baskets_count":     len(active_baskets),
        "baskets_without_rm_count": len(baskets_without_rm),
        "total_pnl":                sum(p["pnl"] for p in positions),
        "user_id":                  load_user_id(),
    })


@app.get("/pnl")
async def get_pnl():
    """Lightweight P&L endpoint — recomputes from ticker/last_price without a Kite API call."""
    positions_data: dict[str, dict] = {}
    total_pnl = 0.0

    for p in _all_positions_cache:
        ltp, pnl, pnl_pct = _compute_pnl(p)
        key = _position_key(p)
        positions_data[key] = {"ltp": ltp, "pnl": pnl, "pnl_pct": pnl_pct}
        total_pnl += pnl

    baskets_data: dict[str, dict] = {}
    for b in _basket_cache:
        basket_pnl = sum(
            positions_data.get(_position_key(p), {}).get("pnl", 0)
            for p in b.get("positions", [])
        )
        basket_cost = sum(
            abs(p["average_price"]) * abs(p["quantity"]) * p.get("multiplier", 1)
            for p in b.get("positions", [])
        )
        basket_pnl_pct = (basket_pnl / basket_cost * 100) if basket_cost else 0.0
        baskets_data[str(b["id"])] = {"pnl": basket_pnl, "pnl_pct": basket_pnl_pct}

    return JSONResponse({"total_pnl": total_pnl, "positions": positions_data, "baskets": baskets_data})
