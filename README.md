# AlgoTrade — F&O Risk Management Platform

A real-time risk management platform for Zerodha F&O traders. Set your exit rules once — the engine watches your positions 24/7 and fires orders automatically when your thresholds are hit.

Live on two accounts at:
- [neerajaalgotrading.duckdns.org](http://neerajaalgotrading.duckdns.org)
- [nirmalaalgotrading.duckdns.org](http://nirmalaalgotrading.duckdns.org)

---

## What it does

- **Live P&L monitoring** — WebSocket LTP feed from Kite, refreshed every second during market hours
- **Basket-based position grouping** — assign related legs (e.g. a strangle) to a basket and monitor them together
- **Automated exit rules per basket:**
  - **Profit Target** — exit when basket P&L crosses a target (with optional tick confirmation)
  - **Loss Guard** — exit when basket P&L breaches a loss limit
  - **Profit Shield** — lock in profits with a trailing floor; steps up as P&L improves
  - **EOD auto-exit** — exit all positions at 3:25 PM automatically
- **LIMIT or MARKET exit orders** — configurable per basket; LIMIT orders retry up to 6 times with cancel-and-replace
- **Exit logs** — full per-event history: which rule fired, MTM at trigger time, every order attempt with fill status
- **Multi-account support** — run separate instances on one EC2 server, one per Zerodha account

---

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python 3.14 · FastAPI · uvicorn |
| Frontend | Jinja2 templates · HTMX · vanilla JS |
| Database | SQLite (WAL mode) |
| Broker API | Zerodha KiteConnect v5 (REST + WebSocket) |
| Infrastructure | AWS EC2 · nginx reverse proxy · systemd |

---

## Architecture

```
Browser (HTMX polling)
       │
       ▼
FastAPI (main.py)
  ├── _refresh_loop()        ← background task, runs every 60s
  │     ├── fetch_positions() via asyncio.to_thread
  │     ├── seed_ltp()       ← REST fallback when WebSocket is down
  │     └── ticker.subscribe()
  │
  ├── run_engine()           ← background task, ticks every 1s in market hours
  │     └── _check_basket()  ← per-basket: PT / LG / PS / EOD checks
  │           └── _fire()    ← spawned as independent asyncio.Task
  │                 └── place_exit_orders() → Kite REST API
  │
  └── KiteTicker (WebSocket) ← runs in its own thread, pushes to ltp_store{}
```

Key design decisions:
- **Single KiteConnect singleton** — reuses the underlying `requests.Session` to avoid fd leaks on rapid refreshes
- **ltp_store is the source of truth** for live prices; REST quote API is the fallback when WebSocket is down
- **Each basket exit fires as an independent asyncio.Task** — a slow LIMIT retry on basket A never blocks RM evaluation for baskets B, C, D
- **All blocking I/O off the event loop** — Kite REST calls, SQLite queries, and WebSocket sends all run via `asyncio.to_thread`

---

## Project structure

```
AlgoTrade/
├── main.py              # FastAPI app, cache refresh loop, P&L endpoints
├── config.py            # Env vars (KITE_API_KEY, KITE_API_SECRET, APP_BASE_URL)
├── database.py          # SQLite context manager with WAL + busy_timeout
├── auth/
│   ├── routes.py        # /auth/login · /auth/callback · /auth/logout
│   └── token_store.py   # Atomic token file read/write
├── kite/
│   ├── client.py        # KiteConnect singleton with session expiry hook
│   ├── ticker.py        # KiteTicker WebSocket manager + ltp_store
│   ├── orders.py        # Exit order placement (LIMIT retry + MARKET)
│   └── positions.py     # fetch_positions() wrapper
├── baskets/
│   ├── routes.py        # Basket CRUD, position assignment, RM config endpoints
│   └── service.py       # DB queries for baskets, positions, RM config
├── rm/
│   └── engine.py        # RM rules engine (PT / LG / PS / EOD)
├── logs/
│   ├── routes.py        # /logs page with filters
│   └── service.py       # Exit event + order log DB queries
├── templates/           # Jinja2 HTML templates
├── static/              # CSS, JS assets
└── requirements.txt
```

---

## Setup

### Prerequisites
- Python 3.12+
- A Zerodha Kite Connect app ([create one here](https://developers.kite.trade/))
- AWS EC2 instance (or any Linux server)

### Local development

```bash
git clone https://github.com/imguru18695/AlgoTrade.git
cd AlgoTrade

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Create .env file
cat > .env <<EOF
KITE_API_KEY=your_api_key
KITE_API_SECRET=your_api_secret
APP_BASE_URL=http://localhost:8000
EOF

uvicorn main:app --reload --port 8000
```

Then open `http://localhost:8000` and log in with your Zerodha account.

### EC2 production deployment

```bash
# Clone and set up venv
git clone https://github.com/imguru18695/AlgoTrade.git ~/algoplatform
cd ~/algoplatform
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Create .env with your credentials
nano .env

# Set up systemd service (runs on port 8001)
sudo nano /etc/systemd/system/algoplatform.service
sudo systemctl enable algoplatform
sudo systemctl start algoplatform
```

For a second account, clone to `~/algoplatform2` and run on port 8002 with a separate `.env` and nginx vhost.

---

## Daily workflow

1. Log in each morning via the Zerodha OAuth flow (`/auth/login`)
2. Assign open F&O positions to baskets on the dashboard
3. Configure RM rules per basket (PT / LG / PS / EOD)
4. The engine monitors positions and fires exits automatically during market hours (9:15 AM – 3:29 PM IST)
5. Review exit history on the `/logs` page — rule that fired, MTM at trigger, every order attempt

---

## Security

- API key and secret are stored only in `~/algoplatform/.env` on the server — never committed to Git
- Access token is written atomically to `access_token.txt` and cleared on logout
- The app runs on `localhost` only; nginx handles TLS termination and public access

---

## License

MIT
