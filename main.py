import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware

from database import init_db
from sso import make_token, verify_token
from auth.routes import router as auth_router
from auth.token_store import load_token, load_user_id
from auth.local_login import verify_login as verify_local_login
from baskets.routes import router as baskets_router
from logs.routes import router as logs_router
from execution.routes import router as execution_router
from execution import engine as exec_engine
from baskets.service import list_baskets, get_assigned_positions, get_rm, get_order_type, delete_basket, assign_position
from kite.client import get_kite
from kite.positions import fetch_positions
from kite import ticker
from kite.orders import place_exit_orders
from rm.engine import run_engine, reset_basket, get_basket_state

logging.basicConfig(level=logging.INFO)

IST = timezone(timedelta(hours=5, minutes=30))

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

    # Create / update WebSocket subscription (idempotent — no reconnect if already live).
    # Run off the event loop: subscribe() acquires a threading.Lock and makes
    # synchronous WebSocket sends — keeping it on the event loop stalls all
    # coroutines (RM ticks, HTTP responses) for the duration of those sends.
    tokens = [p["instrument_token"] for p in positions if p.get("instrument_token")]
    if tokens:
        await asyncio.to_thread(ticker.subscribe, tokens)

    # Apply live LTP to each position
    for p in positions:
        ltp, pnl, pnl_pct = _compute_pnl(p)
        p["last_price"] = ltp
        p["pnl"]        = pnl
        p["pnl_pct"]    = pnl_pct

    # Build basket → positions mapping from DB.
    # Run SQLite calls off the event loop: each opens a connection with busy_timeout=3s;
    # lock contention could stall the event loop for the full timeout once per minute.
    assigned   = await asyncio.to_thread(get_assigned_positions)
    baskets    = await asyncio.to_thread(list_baskets)
    rm_configs = await asyncio.gather(
        *[asyncio.to_thread(get_rm, b["id"]) for b in baskets]
    )

    basket_positions: dict[int, list[dict]] = {b["id"]: [] for b in baskets}
    unallocated: list[dict] = []

    for p in positions:
        key = _position_key(p)
        bid = assigned.get(key)
        if bid and bid in basket_positions:
            basket_positions[bid].append(p)
        else:
            unallocated.append(p)

    for b, rm in zip(baskets, rm_configs):
        b["order_type"] = b.get("order_type", "LIMIT")
        b["positions"]  = basket_positions[b["id"]]
        b["pnl"]        = sum(p["pnl"] for p in b["positions"])
        basket_cost     = sum(
            abs(p["average_price"]) * abs(p["quantity"]) * p.get("multiplier", 1)
            for p in b["positions"]
        )
        b["pnl_pct"]    = (b["pnl"] / basket_cost * 100) if basket_cost else 0.0
        b["rm"]         = rm
        b["rm_enabled"] = bool(
            rm.get("pt_active") or rm.get("lg_active") or rm.get("ps_active") or
            rm.get("eod_exit") or rm.get("spot_guard_active") or
            rm.get("velocity_guard_active") or rm.get("hard_pt_active") or rm.get("hard_lg_active")
        )
        state           = get_basket_state(b["id"])
        b["fired"]      = state.get("fired", False)
        b["peak_pnl"]   = state.get("peak_pnl")
        b["ps_floor"]   = state.get("floor") if state.get("ps_armed") else None

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

    from market import spot_cache
    _keep(asyncio.create_task(spot_cache.refresh_loop(
        get_kite_fn=lambda: get_kite() if load_token() else None
    )))

    # Auto-assign filled execution orders to their target basket
    async def _exec_assign_fn(basket_id: int, tradingsymbol: str, exchange: str, product: str):
        try:
            await asyncio.to_thread(assign_position, basket_id, tradingsymbol, exchange, product)
            logging.info(f"Execution: auto-assigned {tradingsymbol} → basket {basket_id}")
        except Exception as e:
            logging.error(f"Execution auto-assign failed: {e}")

    _keep(asyncio.create_task(exec_engine.poll_orders(assign_fn=_exec_assign_fn)))

    async def _delete_basket_fn(basket_id: int):
        await asyncio.to_thread(delete_basket, basket_id)
        # Evict from cache immediately so the engine doesn't re-trigger
        # on the stale basket before the next 60-second refresh.
        global _basket_cache
        _basket_cache = [b for b in _basket_cache if b["id"] != basket_id]

    _keep(asyncio.create_task(run_engine(
        get_baskets_fn=_get_baskets_for_engine,
        ltp_fn=ticker.get_ltp,
        exit_fn=_exit_fn,
        delete_basket_fn=_delete_basket_fn,
        no_ltp_fn=lambda: logging.warning("RM engine: no live prices available."),
        spot_fn=spot_cache.get_spot,
        spot_history_fn=spot_cache.get_spot_n_min_ago,
        get_kite_fn=lambda: get_kite() if load_token() else None,
    )))
    yield
    # Cancel background tasks BEFORE stopping the ticker — otherwise _refresh_loop
    # can re-create the WebSocket after ticker.stop() has torn it down.
    for task in list(_background_tasks):
        task.cancel()
    if _background_tasks:
        await asyncio.gather(*list(_background_tasks), return_exceptions=True)
    ticker.stop()


SSO_ACCOUNT_NAME = os.environ["SSO_ACCOUNT_NAME"]


def _has_valid_session(request: Request) -> bool:
    """True if this visitor either has an active Kite session (the existing
    gate) or arrived via convexitysystems.com's login and holds a valid
    session cookie for THIS account specifically — a cookie minted for a
    different account must not pass here."""
    if load_token():
        return True
    return verify_token(request.cookies.get("cx_session", "")) == SSO_ACCOUNT_NAME


class _DashboardGuard(BaseHTTPMiddleware):
    """The React dashboard is a StaticFiles mount, so it can't carry a
    per-route auth dependency the way the Jinja pages do — this is the
    equivalent gate, checked before the static files are ever served."""
    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/dashboard") and not _has_valid_session(request):
            return RedirectResponse(url="/auth/login")
        return await call_next(request)


app = FastAPI(lifespan=lifespan)
app.add_middleware(_DashboardGuard)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/api/session")
async def api_session():
    """Whether a Kite session is currently active — lets the public React
    dashboard show Login/Logout correctly without guessing from data shape."""
    token = load_token()
    return JSONResponse({"logged_in": bool(token), "user_id": load_user_id() if token else None})


@app.get("/api/dashboard")
async def api_dashboard(request: Request):
    """Market dashboard snapshot — NIFTY/SENSEX/BANKNIFTY/INDIA VIX are live
    via Kite when a session is active, simulated otherwise (same shape either
    way). build_dashboard() makes blocking Kite HTTP calls, so it runs off the
    event loop — same convention as _refresh_cache — to avoid stalling the RM
    engine and other requests for the duration of those calls."""
    if not _has_valid_session(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    from market import snapshot
    kite = get_kite() if load_token() else None
    data = await asyncio.to_thread(snapshot.build_dashboard, kite)
    return JSONResponse(data)


@app.get("/api/management")
async def api_management(request: Request):
    """Basket/position/RM control-panel snapshot — the JSON twin of the
    /management Jinja page, for the React version. Reuses _page_context()
    (the same cache-gathering the Jinja page and the RM engine already
    depend on) so this can never fork or drift from that logic — it only
    reads the already-existing caches. Explicit field whitelist rather than
    JSONResponse(ctx) directly: ctx also carries the raw Request object,
    which isn't JSON-serializable."""
    ctx = await _page_context(request)
    if ctx is None:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return JSONResponse({
        "positions":                ctx["positions"],
        "unallocated":              ctx["unallocated"],
        "baskets":                  ctx["baskets"],
        "active_baskets_count":     ctx["active_baskets_count"],
        "baskets_without_rm_count": ctx["baskets_without_rm_count"],
        "total_pnl":                ctx["total_pnl"],
        "user_id":                  ctx["user_id"],
        "demo_mode":                False,
    })


@app.get("/api/logs")
async def api_logs(request: Request, basket_name: str = "", from_date: str = "", to_date: str = ""):
    """Exit-log snapshot — the JSON twin of the /logs Jinja page, for the
    React version. Reuses logs.service (the exact queries the Jinja page
    already runs), so this can never drift from that logic. Gated on
    _has_valid_session rather than the Jinja page's plain load_token() check
    — the same, more-current convention as /api/dashboard and
    /api/management, not a change to the old page's own route."""
    if not _has_valid_session(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    from logs import service as logs_service
    today = datetime.now(IST).date()
    effective_from = from_date or (today - timedelta(days=6)).isoformat()
    effective_to = to_date or today.isoformat()
    events = await asyncio.to_thread(logs_service.get_logs, basket_name or None, effective_from, effective_to)
    basket_names = await asyncio.to_thread(logs_service.get_basket_names)
    return JSONResponse({
        "events":       events,
        "basket_names": basket_names,
        "basket_name":  basket_name,
        "from_date":    effective_from,
        "to_date":      effective_to,
    })


app.include_router(auth_router)
app.include_router(baskets_router)
app.include_router(logs_router)
app.include_router(execution_router)

templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("home.html", {"request": request})


@app.get("/login", response_class=HTMLResponse)
async def login_form(request: Request, error: str = ""):
    return templates.TemplateResponse("login.html", {"request": request, "error": bool(error)})


@app.post("/login")
async def login_submit(username: str = Form(...), password: str = Form(...)):
    if not verify_local_login(username, password):
        logging.warning(f"Failed local login attempt for user {username!r}")
        return RedirectResponse(url="/login?error=1", status_code=303)

    session_token = make_token(SSO_ACCOUNT_NAME, 12 * 3600)
    resp = RedirectResponse(url="/dashboard", status_code=303)
    resp.set_cookie(
        "cx_session", session_token,
        httponly=True, secure=True, samesite="lax", max_age=12 * 3600,
    )
    return resp


@app.get("/exit")
async def exit_terminal():
    """Ends the page-level terminal session (the /login cookie) and returns
    to the public landing page. Deliberately independent of the Kite broker
    session (auth/routes.py's /auth/logout) — exiting the terminal does not
    disconnect the broker, which keeps running server-side regardless."""
    resp = RedirectResponse(url="/", status_code=303)
    resp.delete_cookie("cx_session")
    return resp


async def _page_context(request: Request) -> dict | None:
    """Shared context builder for dashboard and management pages.
    Returns None and sets a redirect if auth fails."""
    if not _has_valid_session(request):
        return None
    try:
        await _refresh_cache()
    except Exception as e:
        logging.error(f"Page load cache refresh failed: {e}")
        if not _all_positions_cache and not _basket_cache:
            return None

    positions   = _all_positions_cache
    baskets     = _basket_cache
    unallocated = _unallocated_cache

    active_baskets     = [b for b in baskets if len(b["positions"]) > 0]
    baskets_without_rm = [b for b in active_baskets if not b["rm_enabled"]]

    return {
        "request":                  request,
        "positions":                positions,
        "unallocated":              unallocated,
        "baskets":                  baskets,
        "active_baskets_count":     len(active_baskets),
        "baskets_without_rm_count": len(baskets_without_rm),
        "total_pnl":                sum(p["pnl"] for p in positions),
        "user_id":                  load_user_id(),
    }


@app.get("/live", response_class=HTMLResponse)
async def dashboard(request: Request):
    ctx = await _page_context(request)
    if ctx is None:
        return RedirectResponse(url="/auth/login")
    ctx["active_page"] = "dashboard"
    return templates.TemplateResponse("dashboard.html", ctx)


@app.get("/management", response_class=HTMLResponse)
async def management(request: Request):
    ctx = await _page_context(request)
    if ctx is None:
        return RedirectResponse(url="/auth/login")
    ctx["active_page"] = "management"
    return templates.TemplateResponse("management.html", ctx)


@app.get("/debug/positions")
async def debug_positions(request: Request):
    """Compare our computed P&L against Kite's own field — helps diagnose MTM discrepancies."""
    if not _has_valid_session(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    from kite.client import get_kite
    raw = await asyncio.to_thread(get_kite().positions)
    rows = []
    for p in raw.get("net", []):
        if p["quantity"] == 0:
            continue
        sym      = p["tradingsymbol"]
        qty      = p["quantity"]
        avg      = p.get("average_price", 0)
        lp       = p.get("last_price", 0)
        mult     = p.get("multiplier", 1) or 1
        kite_pnl = p.get("pnl", 0)
        our_pnl  = (lp - avg) * qty * mult
        token    = p.get("instrument_token")
        ws_ltp   = ticker.get_ltp(token) if token else None
        ws_pnl   = (ws_ltp - avg) * qty * mult if ws_ltp is not None else None
        rows.append({
            "symbol":       sym,
            "qty":          qty,
            "avg_price":    avg,
            "last_price":   lp,
            "multiplier":   mult,
            "kite_pnl":     kite_pnl,
            "our_pnl_rest": round(our_pnl, 2),
            "ws_ltp":       ws_ltp,
            "ws_pnl":       round(ws_pnl, 2) if ws_pnl is not None else None,
            "diff":         round(our_pnl - kite_pnl, 2),
        })
    return JSONResponse(rows)


@app.get("/pnl")
async def get_pnl(request: Request):
    """Lightweight P&L endpoint — recomputes from ticker/last_price without a Kite API call.
    Also recomputes each basket's Greeks/PCR/payoff on this same cheap cycle (baskets/analytics.py) -
    no new Kite calls either: spot comes from spot_cache (already polled independently) and the
    strike/expiry lookups hit instruments.py's already-warm instrument-master cache."""
    if not _has_valid_session(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    from market import spot_cache
    from instruments import detect_underlying
    from baskets.analytics import compute_basket_analytics

    positions_data: dict[str, dict] = {}
    total_pnl = 0.0

    for p in _all_positions_cache:
        ltp, pnl, pnl_pct = _compute_pnl(p)
        key = _position_key(p)
        positions_data[key] = {"ltp": ltp, "pnl": pnl, "pnl_pct": pnl_pct}
        total_pnl += pnl

    kite = get_kite() if load_token() else None
    baskets_data: dict[str, dict] = {}
    for b in _basket_cache:
        basket_positions = b.get("positions", [])
        basket_pnl = sum(
            positions_data.get(_position_key(p), {}).get("pnl", 0)
            for p in basket_positions
        )
        basket_cost = sum(
            abs(p["average_price"]) * abs(p["quantity"]) * p.get("multiplier", 1)
            for p in basket_positions
        )
        basket_pnl_pct = (basket_pnl / basket_cost * 100) if basket_cost else 0.0
        state = get_basket_state(b["id"])

        # Greeks need the freshest LTP for IV-solving — the cached position's
        # own last_price is only as fresh as the last 60s _refresh_cache(),
        # but positions_data above was just recomputed from the live ticker.
        fresh_positions = [
            {**p, "last_price": positions_data.get(_position_key(p), {}).get("ltp", p["last_price"])}
            for p in basket_positions
        ]
        underlying = detect_underlying(fresh_positions)
        spot = spot_cache.get_spot(underlying) if underlying else None
        analytics = compute_basket_analytics(fresh_positions, spot, kite)

        baskets_data[str(b["id"])] = {
            "pnl":       basket_pnl,
            "pnl_pct":   basket_pnl_pct,
            "peak_pnl":  state.get("peak_pnl"),
            "ps_floor":  state.get("floor") if state.get("ps_armed") else None,
            "analytics": analytics,
        }

    return JSONResponse({"total_pnl": total_pnl, "positions": positions_data, "baskets": baskets_data})


# ── Convexity React dashboard (Vite build) — served at "/dashboard" ─────────
# "/" is now the marketing landing page (see home() above); the React app
# lives at /dashboard instead. Its own asset paths are relative (vite base:
# "./") and its fetch calls are domain-absolute (/api/*), so it works
# correctly mounted here without any rebuild. Guarded + directory check so a
# missing build can never affect the live app's startup.
import os as _os
_APP_DIST = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "frontend", "dist")
if _os.path.isdir(_APP_DIST):
    app.mount("/dashboard", StaticFiles(directory=_APP_DIST, html=True), name="app")
