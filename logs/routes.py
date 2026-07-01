from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from auth.token_store import load_token, load_user_id
from logs import service

router = APIRouter(prefix="/logs")
templates = Jinja2Templates(directory="templates")
IST = timezone(timedelta(hours=5, minutes=30))


@router.get("", response_class=HTMLResponse)
async def logs_page(
    request: Request,
    basket_name: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
):
    if not load_token():
        return RedirectResponse(url="/auth/login")

    today = datetime.now(IST).date()
    effective_from = from_date or (today - timedelta(days=6)).isoformat()
    effective_to   = to_date   or today.isoformat()

    events       = service.get_logs(basket_name or None, effective_from, effective_to)
    basket_names = service.get_basket_names()

    return templates.TemplateResponse("logs.html", {
        "request":      request,
        "events":       events,
        "basket_names": basket_names,
        "basket_name":  basket_name or "",
        "from_date":    effective_from,
        "to_date":      effective_to,
        "user_id":      load_user_id(),
    })


@router.post("/clear")
async def clear_logs(request: Request):
    form      = await request.form()
    event_ids = [int(x) for x in form.getlist("event_id") if x]
    basket_name = form.get("basket_name", "")
    from_date   = form.get("from_date", "")
    to_date     = form.get("to_date", "")
    service.clear_logs(event_ids)
    return RedirectResponse(
        url=f"/logs?basket_name={basket_name}&from_date={from_date}&to_date={to_date}",
        status_code=302,
    )
