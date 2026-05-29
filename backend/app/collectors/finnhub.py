"""Finnhub — quotes, candles, company news, metrics (free tier friendly)."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.collectors.base import has_finnhub, http_client
from app.config import get_settings

BASE = "https://finnhub.io/api/v1"
logger = logging.getLogger(__name__)

# After 403 from an endpoint class, stop calling it for this process (premium / blocked).
_skip_candles = False
_skip_metrics = False
_skip_company_news = False
_warned_candles = False
_warned_metrics = False
_warned_news = False
_us_symbols_cache: list[str] | None = None

_rl_lock = asyncio.Lock()
_last_fin_call = 0.0


async def _rate_limit() -> None:
    interval = float(get_settings().finnhub_min_request_interval_sec or 0)
    if interval <= 0:
        return
    global _last_fin_call
    async with _rl_lock:
        now = time.monotonic()
        gap = now - _last_fin_call
        if gap < interval:
            await asyncio.sleep(interval - gap)
        _last_fin_call = time.monotonic()


async def _get(path: str, params: dict | None = None) -> Any | None:
    """Return JSON or None on 4xx/5xx (no exception). Respects rate limit."""
    global _skip_candles, _skip_metrics, _skip_company_news
    global _warned_candles, _warned_metrics, _warned_news

    if not has_finnhub():
        return None

    if path == "/stock/candle" and _skip_candles:
        return None
    if path == "/stock/metric" and _skip_metrics:
        return None
    if path == "/company-news" and _skip_company_news:
        return None

    await _rate_limit()

    q = dict(params or {})
    q["token"] = get_settings().finnhub_api_key
    async with http_client() as client:
        r = await client.get(f"{BASE}{path}", params=q)

    if r.status_code == 200:
        return r.json()

    if r.status_code == 429:
        if path == "/stock/candle" and not _warned_candles:
            logger.warning(
                "Finnhub rate limit (429) — slow down with FINNHUB_MIN_REQUEST_INTERVAL_SEC=1.05 "
                "or rely on Alpaca for VWAP/volume."
            )
            _warned_candles = True  # reuse flag to spam once
        elif path == "/company-news" and not _warned_news:
            logger.warning(
                "Finnhub rate limit (429) on company-news — set FINNHUB_MIN_REQUEST_INTERVAL_SEC "
                "or temporarily disable headlines."
            )
            _warned_news = True
        return None

    if r.status_code in (401, 403):
        if path == "/stock/candle" and not _warned_candles:
            logger.warning(
                "Finnhub %s on /stock/candle — skipping candles for this session. "
                "Free tier: tight limits; use Alpaca for VWAP/volume when possible.",
                r.status_code,
            )
            _warned_candles = True
            _skip_candles = True
        elif path == "/stock/metric" and not _warned_metrics:
            logger.warning(
                "Finnhub %s on /stock/metric — skipping metrics (often premium-only on free plans).",
                r.status_code,
            )
            _warned_metrics = True
            _skip_metrics = True
        elif path == "/company-news" and not _warned_news:
            logger.warning(
                "Finnhub %s on /company-news — blocking company-news for this process (upgrade plan or reduce calls).",
                r.status_code,
            )
            _warned_news = True
            if r.status_code == 403:
                _skip_company_news = True
        elif path == "/quote":
            logger.warning("Finnhub %s on /quote for params=%s", r.status_code, q.get("symbol"))

    return None


def reset_finnhub_guard_for_tests() -> None:
    global _skip_candles, _skip_metrics, _skip_company_news
    global _warned_candles, _warned_metrics, _warned_news
    _skip_candles = _skip_metrics = _skip_company_news = False
    _warned_candles = _warned_metrics = _warned_news = False


async def fetch_quote(symbol: str) -> dict[str, Any] | None:
    if not has_finnhub():
        return None
    data = await _get("/quote", {"symbol": symbol.upper()})
    if not data or data.get("c", 0) == 0:
        return None
    current = float(data["c"])
    prev = float(data.get("pc") or data.get("previousClose") or 0)
    pct = round((current - prev) / prev * 100, 2) if prev else 0.0
    price_as_of = None
    t_raw = data.get("t")
    if t_raw is not None:
        try:
            ts = int(t_raw)
            if ts > 1e12:
                ts //= 1000
            price_as_of = datetime.fromtimestamp(ts, tz=timezone.utc)
        except (ValueError, OSError, TypeError):
            pass
    from app.collectors.session_util import current_session_label

    session = current_session_label()
    return {
        "ticker": symbol.upper(),
        "price": current,
        "previous_close": prev,
        "percent_change": pct,
        "open": float(data.get("o") or 0) or None,
        "hod": float(data.get("h") or 0) or None,
        "lod": float(data.get("l") or 0) or None,
        "volume": None,
        "source": "finnhub",
        "price_as_of": price_as_of,
        "price_source": "finnhub_quote",
        "session": session,
    }


async def fetch_candles(symbol: str, resolution: str = "5") -> list[dict[str, Any]]:
    """Intraday candles for VWAP / volume estimates."""
    if not has_finnhub():
        return []
    end = int(datetime.now(timezone.utc).timestamp())
    start = end - 86400 * 2
    data = await _get(
        "/stock/candle",
        {"symbol": symbol.upper(), "resolution": resolution, "from": start, "to": end},
    )
    if not data:
        return []
    if data.get("s") != "ok":
        return []
    times = data.get("t") or []
    closes = data.get("c") or []
    highs = data.get("h") or []
    lows = data.get("l") or []
    vols = data.get("v") or []
    vwaps = data.get("vwap") or []
    bars = []
    for i in range(len(times)):
        bars.append(
            {
                "time": times[i],
                "close": closes[i] if i < len(closes) else 0,
                "high": highs[i] if i < len(highs) else 0,
                "low": lows[i] if i < len(lows) else 0,
                "volume": vols[i] if i < len(vols) else 0,
                "vwap": vwaps[i] if i < len(vwaps) else None,
            }
        )
    return bars


def enrich_from_candles(raw: dict[str, Any], bars: list[dict[str, Any]]) -> None:
    if not bars:
        return
    total_vol = sum(b.get("volume") or 0 for b in bars)
    raw["volume"] = int(total_vol) if total_vol else raw.get("volume")
    last = bars[-1]
    vwap = last.get("vwap")
    if vwap:
        raw["vwap"] = float(vwap)
        price = float(raw.get("price") or last.get("close") or 0)
        raw["above_vwap"] = price >= vwap if price else None
    if not raw.get("hod"):
        raw["hod"] = max((b.get("high") or 0) for b in bars)
    if not raw.get("lod"):
        raw["lod"] = min((b.get("low") or 0) for b in bars if b.get("low"))


async def fetch_company_profile(symbol: str) -> dict[str, Any]:
    """Company profile (free tier) — market cap, float, sector."""
    if not has_finnhub():
        return {}
    data = await _get("/stock/profile2", {"symbol": symbol.upper()})
    return data if isinstance(data, dict) else {}


async def fetch_metrics(symbol: str) -> dict[str, Any]:
    if not has_finnhub() or not get_settings().finnhub_fetch_metrics:
        return {}
    data = await _get("/stock/metric", {"symbol": symbol.upper(), "metric": "all"})
    if not data:
        return {}
    return data.get("metric") or {}


async def fetch_company_news(symbol: str, limit: int = 15) -> list[dict[str, Any]]:
    if not has_finnhub():
        return []
    end = date.today()
    start = end - timedelta(days=7)
    items = await _get(
        "/company-news",
        {
            "symbol": symbol.upper(),
            "from": start.isoformat(),
            "to": end.isoformat(),
        },
    )
    if not items:
        return []
    if not isinstance(items, list):
        return []
    out = []
    for item in items[:limit]:
        headline = item.get("headline") or ""
        ts = item.get("datetime")
        out.append(
            {
                "type": _classify(headline),
                "summary": headline,
                "quality": _quality(headline),
                "source": "finnhub",
                "timestamp": datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None,
                "url": item.get("url", ""),
            }
        )
    return out


async def fetch_us_symbols(limit: int = 5000) -> list[str]:
    """One Finnhub call — full US symbol list (cached in memory for the process)."""
    global _us_symbols_cache
    if not has_finnhub():
        return []
    if _us_symbols_cache is None:
        data = await _get("/stock/symbol", {"exchange": "US"})
        if not isinstance(data, list):
            _us_symbols_cache = []
        else:
            _us_symbols_cache = [
                str(x.get("symbol", "")).upper()
                for x in data
                if x.get("symbol")
                and x.get("type") == "Common Stock"
                and "." not in str(x.get("symbol", ""))
            ]
    return _us_symbols_cache[:limit]


async def fetch_market_news(limit: int = 20) -> list[dict[str, Any]]:
    if not has_finnhub():
        return []
    items = await _get("/news", {"category": "general"})
    if not items:
        return []
    return (items or [])[:limit]


def _classify(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ("earnings", "eps", "revenue", "guidance")):
        return "earnings"
    if any(w in t for w in ("offering", "shelf", "atm")):
        return "offering"
    if any(w in t for w in ("upgrade", "downgrade", "price target", "analyst")):
        return "analyst"
    if any(w in t for w in ("fda", "approval")):
        return "fda"
    if any(w in t for w in ("contract", "partnership", "mou")):
        return "partnership"
    if any(w in t for w in ("ai", "quantum", "crypto")):
        return "theme_hype"
    return "headline"


def _quality(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ("beats", "raises", "approval", "signed")):
        return "high"
    if any(w in t for w in ("miss", "cut", "offering", "shelf")):
        return "low"
    if any(w in t for w in ("mou", "partnership", "ai", "crypto")):
        return "medium"
    return "medium"
