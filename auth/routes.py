import asyncio
import logging
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from kiteconnect import KiteConnect
from config import KITE_API_KEY, KITE_API_SECRET, REDIRECT_URL
from auth.token_store import save_token, clear_token
from kite.client import reset_kite

router = APIRouter(prefix="/auth")


def _kite() -> KiteConnect:
    return KiteConnect(api_key=KITE_API_KEY)


@router.get("/login", response_class=HTMLResponse)
async def login():
    kite = _kite()
    login_url = kite.login_url()
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>AlgoPlatform — Login</title>
        <style>
            body {{ font-family: sans-serif; display: flex; flex-direction: column;
                   align-items: center; justify-content: center; min-height: 100vh;
                   margin: 0; background: #0f172a; color: #f1f5f9; }}
            a.btn {{ background: #3b82f6; color: white; padding: 14px 32px;
                    border-radius: 8px; text-decoration: none; font-size: 16px;
                    font-weight: 600; margin-top: 24px; display: inline-block; }}
            p {{ color: #94a3b8; margin-top: 8px; font-size: 14px; }}
        </style>
    </head>
    <body>
        <h2>AlgoPlatform</h2>
        <p>Login with your Zerodha account to start monitoring positions.</p>
        <a class="btn" href="{login_url}">Login with Kite</a>
    </body>
    </html>
    """


@router.get("/callback")
async def callback(request: Request):
    request_token = request.query_params.get("request_token")
    if not request_token:
        return HTMLResponse("Missing request_token. Please try logging in again.", status_code=400)

    try:
        kite = _kite()
        # generate_session is a blocking HTTP call — run off the event loop so we
        # don't freeze WebSocket ticks and RM engine checks during login.
        session = await asyncio.to_thread(
            kite.generate_session, request_token, api_secret=KITE_API_SECRET
        )
        save_token(session["access_token"], user_id=session.get("user_id", ""))
    except Exception as e:
        logging.error(f"Login callback failed: {e}")
        return RedirectResponse(url="/auth/login", status_code=302)

    return RedirectResponse(url="/", status_code=302)


@router.get("/logout")
async def logout():
    clear_token()
    reset_kite()
    return RedirectResponse(url="/auth/login", status_code=302)
