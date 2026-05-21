"""News — Finnhub primary (MVP), Benzinga optional."""

from datetime import datetime, timezone
from typing import Any

from app.collectors import finnhub
from app.collectors.base import has_benzinga, has_finnhub, http_client
from app.config import get_settings

BENZINGA = "https://api.benzinga.com/api/v2"


async def fetch_headlines(symbol: str, limit: int = 10) -> list[dict[str, Any]]:
    if has_finnhub() and get_settings().finnhub_fetch_company_news:
        news = await finnhub.fetch_company_news(symbol, limit=limit)
        if news:
            return news
    if has_benzinga():
        return await _benzinga(symbol, limit)
    return []


async def _benzinga(symbol: str, limit: int) -> list[dict[str, Any]]:
    settings = get_settings()
    async with http_client() as client:
        r = await client.get(
            f"{BENZINGA}/news",
            params={
                "token": settings.benzinga_api_key,
                "tickers": symbol.upper(),
                "pageSize": limit,
                "displayOutput": "full",
            },
        )
        if r.status_code != 200:
            return []
        data = r.json()

    items = data if isinstance(data, list) else data.get("news", data.get("articles", []))
    out: list[dict[str, Any]] = []
    for item in (items or [])[:limit]:
        title = item.get("title") or item.get("headline") or ""
        created = item.get("created") or item.get("updated")
        out.append(
            {
                "type": _classify_headline(title),
                "summary": title,
                "quality": _headline_quality(title),
                "source": "benzinga",
                "timestamp": _parse_ts(created),
                "url": item.get("url", ""),
            }
        )
    return out


def _classify_headline(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ("earnings", "eps", "revenue", "guidance")):
        return "earnings"
    if any(w in t for w in ("offering", "shelf", "atm", "prospectus")):
        return "offering"
    if any(w in t for w in ("upgrade", "downgrade", "price target", "analyst")):
        return "analyst"
    if any(w in t for w in ("fda", "approval", "trial")):
        return "fda"
    if any(w in t for w in ("contract", "partnership", "mou", "agreement")):
        return "partnership"
    if any(w in t for w in ("ai ", "artificial intelligence", "quantum", "crypto")):
        return "theme_hype"
    return "headline"


def _headline_quality(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ("beats", "raises guidance", "fda approval", "signed contract")):
        return "high"
    if any(w in t for w in ("miss", "cut guidance", "offering", "shelf", "atm")):
        return "low"
    if any(w in t for w in ("mou", "explores", "strategy", "partnership")):
        return "medium"
    if any(w in t for w in ("ai", "crypto", "quantum", "meme")):
        return "low"
    return "medium"


def _parse_ts(val: Any) -> datetime | None:
    if not val:
        return None
    if isinstance(val, (int, float)):
        return datetime.fromtimestamp(val, tz=timezone.utc)
    s = str(val)
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s[:19], fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None
