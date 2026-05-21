"""Polygon.io / Massive market data."""

from datetime import date, timedelta
from typing import Any

from app.collectors.base import has_polygon, http_client
from app.config import get_settings

BASE = "https://api.polygon.io"


async def _get(path: str, params: dict | None = None) -> dict[str, Any]:
    settings = get_settings()
    q = dict(params or {})
    q["apiKey"] = settings.polygon_api_key
    async with http_client() as client:
        r = await client.get(f"{BASE}{path}", params=q)
        r.raise_for_status()
        return r.json()


async def fetch_snapshot(symbol: str) -> dict[str, Any] | None:
    if not has_polygon():
        return None
    data = await _get(f"/v2/snapshot/locale/us/markets/stocks/tickers/{symbol.upper()}")
    return data.get("ticker")


async def fetch_gainers(limit: int = 50) -> list[dict[str, Any]]:
    if not has_polygon():
        return []
    data = await _get("/v2/snapshot/locale/us/markets/stocks/gainers")
    tickers = data.get("tickers") or []
    return tickers[:limit]


async def fetch_losers(limit: int = 50) -> list[dict[str, Any]]:
    if not has_polygon():
        return []
    data = await _get("/v2/snapshot/locale/us/markets/stocks/losers")
    tickers = data.get("tickers") or []
    return tickers[:limit]


async def fetch_minute_bars(symbol: str, limit: int = 390) -> list[dict[str, Any]]:
    if not has_polygon():
        return []
    end = date.today()
    start = end - timedelta(days=5)
    path = (
        f"/v2/aggs/ticker/{symbol.upper()}/range/1/minute/"
        f"{start.isoformat()}/{end.isoformat()}"
    )
    data = await _get(path, {"adjusted": "true", "sort": "asc", "limit": limit})
    return data.get("results") or []


async def fetch_previous_close(symbol: str) -> float | None:
    if not has_polygon():
        return None
    data = await _get(f"/v2/aggs/ticker/{symbol.upper()}/prev")
    results = data.get("results") or []
    if results:
        return float(results[0].get("c", 0))
    return None


def parse_snapshot(ticker: dict[str, Any]) -> dict[str, Any]:
    day = ticker.get("day") or {}
    prev = ticker.get("prevDay") or {}
    last_trade = ticker.get("lastTrade") or {}
    last_quote = ticker.get("lastQuote") or {}
    min_bar = ticker.get("min") or {}

    price = float(last_trade.get("p") or day.get("c") or 0)
    prev_close = float(prev.get("c") or 0)
    volume = int(day.get("v") or ticker.get("volume") or 0)
    vwap = float(day.get("vw") or min_bar.get("vw") or 0) or None
    bid = float(last_quote.get("p") or last_quote.get("bp") or 0) or None
    ask = float(last_quote.get("P") or last_quote.get("ap") or 0) or None

    spread_pct = None
    if bid and ask and bid > 0:
        spread_pct = round((ask - bid) / ((ask + bid) / 2) * 100, 3)

    pct = 0.0
    if prev_close:
        pct = round((price - prev_close) / prev_close * 100, 2)

    return {
        "ticker": ticker.get("ticker", ""),
        "price": price,
        "previous_close": prev_close,
        "percent_change": pct,
        "volume": volume,
        "bid": bid,
        "ask": ask,
        "spread_percent": spread_pct,
        "vwap": vwap,
        "above_vwap": (price >= vwap) if vwap else None,
        "hod": float(day.get("h") or 0) or None,
        "lod": float(day.get("l") or 0) or None,
        "open": float(day.get("o") or 0) or None,
        "premarket_high": None,
        "premarket_low": None,
        "source": "polygon",
    }
