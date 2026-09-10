"""
Strategy template store.
In-memory for demo; swap with SQLite persistence for live.
"""
import time
from typing import Optional

# ── Constants ─────────────────────────────────────────────────────────────────

STRATEGY_TYPES = {
    "short_straddle": "Short Straddle",
    "short_strangle": "Short Strangle",
    "iron_condor":    "Iron Condor",
    "bull_spread":    "Bull Call Spread",
    "bear_spread":    "Bear Put Spread",
}

EXPIRY_RULES = {
    "nearest_weekly":  "Nearest Weekly (Thu)",
    "next_weekly":     "Next Weekly (Thu)",
    "nearest_monthly": "Nearest Monthly (Last Thu)",
}

STATUSES = ("scheduled", "triggering", "active", "error", "paused", "done")

# ── In-memory store ───────────────────────────────────────────────────────────

_templates: dict[int, dict] = {}
_next_id   = 1


def _coerce(data: dict, key: str, typ, default=None):
    v = data.get(key)
    if v is None or v == "":
        return default
    try:
        return typ(v)
    except (ValueError, TypeError):
        return default


# ── CRUD ──────────────────────────────────────────────────────────────────────

def create_template(data: dict) -> dict:
    global _next_id
    t = {
        "id":                  _next_id,
        "name":                data.get("name") or f"Strategy {_next_id}",
        "strategy_type":       data.get("strategy_type", "short_straddle"),
        "underlying":          data.get("underlying", "NIFTY"),
        "expiry_rule":         data.get("expiry_rule", "nearest_weekly"),
        "lots":                _coerce(data, "lots",           int,   1),
        "entry_time":          data.get("entry_time", "09:20"),   # HH:MM IST
        "vix_min":             _coerce(data, "vix_min",        float, None),
        "vix_max":             _coerce(data, "vix_max",        float, None),
        "pt_pct":              _coerce(data, "pt_pct",         float, 50.0),
        "lg_pct":              _coerce(data, "lg_pct",         float, 100.0),
        "ps_active":           bool(data.get("ps_active", False)),
        "ps_trigger_pct":      _coerce(data, "ps_trigger_pct", float, None),
        "ps_lock_pct":         _coerce(data, "ps_lock_pct",    float, None),
        "eod_exit":            bool(data.get("eod_exit", True)),
        "enabled":             True,
        "status":              "scheduled",
        "last_triggered_date": None,
        "last_basket_id":      None,
        "created_at":          time.time(),
    }
    _templates[_next_id] = t
    _next_id += 1
    return t


def list_templates() -> list[dict]:
    return sorted(_templates.values(), key=lambda t: t["created_at"])


def get_template(tid: int) -> Optional[dict]:
    return _templates.get(tid)


def update_template(tid: int, data: dict) -> Optional[dict]:
    t = _templates.get(tid)
    if not t:
        return None
    updatable = (
        "name", "lots", "entry_time", "vix_min", "vix_max",
        "pt_pct", "lg_pct", "ps_active", "ps_trigger_pct", "ps_lock_pct",
        "eod_exit", "enabled", "strategy_type", "underlying", "expiry_rule",
    )
    for key in updatable:
        if key in data:
            t[key] = data[key]
    return t


def toggle_enabled(tid: int) -> Optional[dict]:
    t = _templates.get(tid)
    if t:
        t["enabled"] = not t["enabled"]
        t["status"]  = "scheduled" if t["enabled"] else "paused"
    return t


def delete_template(tid: int):
    _templates.pop(tid, None)


def set_status(tid: int, status: str, date_str: Optional[str] = None,
               basket_id: Optional[int] = None):
    t = _templates.get(tid)
    if t:
        t["status"] = status
        if date_str:
            t["last_triggered_date"] = date_str
        if basket_id is not None:
            t["last_basket_id"] = basket_id
