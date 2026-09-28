import asyncio
import logging
import os
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from kiteconnect import KiteConnect
from config import KITE_API_KEY, KITE_API_SECRET, REDIRECT_URL
from auth.token_store import save_token, clear_token
from kite.client import reset_kite
from sso import make_token, verify_token

router = APIRouter(prefix="/auth")

SSO_ACCOUNT_NAME = os.environ["SSO_ACCOUNT_NAME"]
SSO_SESSION_COOKIE = "cx_session"
SSO_SESSION_TTL_SECONDS = 12 * 3600


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

    return RedirectResponse(url="/dashboard", status_code=302)


@router.get("/sso")
async def sso_login(token: str = ""):
    """Entry point for a visitor arriving from convexitysystems.com's login.
    Verifies the short-lived handoff token names THIS account specifically
    (a token minted for a different account must not work here), then mints
    a longer-lived session cookie so they don't need Kite OAuth just to view
    the dashboard — Kite login is still separately required to trade."""
    account = verify_token(token)
    if account != SSO_ACCOUNT_NAME:
        logging.warning(f"Rejected SSO token (resolved account: {account!r})")
        return RedirectResponse(url="/auth/login", status_code=303)

    session_token = make_token(account, SSO_SESSION_TTL_SECONDS)
    resp = RedirectResponse(url="/dashboard", status_code=303)
    resp.set_cookie(
        SSO_SESSION_COOKIE, session_token,
        httponly=True, secure=True, samesite="lax", max_age=SSO_SESSION_TTL_SECONDS,
    )
    return resp


@router.get("/logout")
async def logout():
    clear_token()
    reset_kite()
    resp = RedirectResponse(url="/auth/login", status_code=302)
    resp.delete_cookie(SSO_SESSION_COOKIE)
    return resp
