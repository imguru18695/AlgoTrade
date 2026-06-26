from kite.client import get_kite


def fetch_positions() -> list[dict]:
    """
    Returns net positions from Kite. Each dict contains the fields
    we care about for display and risk management.
    """
    kite = get_kite()
    raw = kite.positions()
    positions = []

    for p in raw.get("net", []):
        if p["quantity"] == 0:
            continue  # skip closed positions

        pnl = p.get("pnl", 0) or 0
        last_price = p.get("last_price", 0) or 0
        buy_price = p.get("average_price", 0) or 0
        quantity = p.get("quantity", 0)
        multiplier = p.get("multiplier", 1) or 1

        cost = abs(buy_price) * abs(quantity) * multiplier
        pnl_pct = (pnl / cost * 100) if cost else 0.0

        positions.append({
            "tradingsymbol":    p["tradingsymbol"],
            "exchange":         p["exchange"],
            "instrument_token": p.get("instrument_token"),
            "product":          p["product"],
            "quantity":         quantity,
            "average_price":    buy_price,
            "last_price":       last_price,
            "pnl":              pnl,
            "pnl_pct":          pnl_pct,
            "multiplier":       multiplier,
            "buy_value":        p.get("buy_value", 0),
            "sell_value":       p.get("sell_value", 0),
        })

    return positions
