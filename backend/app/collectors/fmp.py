"""Financial Modeling Prep — universe, fundamentals, analyst targets."""

from typing import Any

from app.collectors.base import has_fmp, http_client
from app.config import get_settings

BASE = "https://financialmodelingprep.com/stable"


async def _get(path: str, params: dict | None = None) -> Any:
    settings = get_settings()
    q = dict(params or {})
    q["apikey"] = settings.fmp_api_key
    async with http_client() as client:
        r = await client.get(f"{BASE}{path}", params=q)
        r.raise_for_status()
        return r.json()


async def fetch_stock_list(limit: int = 500) -> list[dict[str, Any]]:
    if not has_fmp():
        return []
    data = await _get("/stock-list")
    if not isinstance(data, list):
        return []
    us = [
        x
        for x in data
        if x.get("symbol")
        and not str(x.get("symbol", "")).endswith((".WS", ".W"))
        and x.get("exchangeShortName") in ("NASDAQ", "NYSE", "AMEX", None)
    ]
    return us[:limit]


async def fetch_profile(symbol: str) -> dict[str, Any] | None:
    if not has_fmp():
        return None
    data = await _get("/profile", {"symbol": symbol.upper()})
    if isinstance(data, list) and data:
        return data[0]
    return None


async def fetch_analyst_targets(symbol: str) -> list[dict[str, Any]]:
    if not has_fmp():
        return []
    data = await _get("/price-target-summary", {"symbol": symbol.upper()})
    if isinstance(data, list):
        return data
    return []


async def fetch_quote(symbol: str) -> dict[str, Any] | None:
    if not has_fmp():
        return None
    data = await _get("/quote", {"symbol": symbol.upper()})
    if isinstance(data, list) and data:
        return data[0]
    return None
