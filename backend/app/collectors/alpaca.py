"""Alpaca market data — snapshot with extended-hours friendly price selection."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from app.collectors.base import has_alpaca, http_client
from app.config import get_settings

DATA_BASE = "https://data.alpaca.markets/v2"
_NY = ZoneInfo("America/New_York")

# Prefer fresher sources when timestamps tie or are missing
_SOURCE_PRIORITY = {
    "latest_trade": 4,
    "minute_bar": 3,
    "quote_mid": 2,
    "daily_close": 1,
}


def _headers() -> dict[str, str]:
    s = get_settings()
    return {
        "APCA-API-KEY-ID": s.alpaca_api_key,
        "APCA-API-SECRET-KEY": s.alpaca_api_secret,
    }


def _parse_alpaca_time(t: Any) -> datetime | None:
    if t is None:
        return None
    if isinstance(t, (int, float)):
        # nanoseconds
        ts = float(t)
        if ts > 1e17:
            ts = ts / 1e9
        elif ts > 1e14:
            ts = ts / 1e6
        elif ts > 1e12:
            ts = ts / 1e3
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except (OSError, ValueError):
            return None
    s = str(t)
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _session_label(ts: datetime | None) -> str:
    if ts is None:
        return "unknown"
    local = ts.astimezone(_NY)
    if local.weekday() >= 5:
        return "weekend"
    mins = local.hour * 60 + local.minute
    if 240 <= mins < 570:
        return "premarket"
    if 570 <= mins < 960:
        return "regular"
    if 960 <= mins < 1200:
        return "afterhours"
    return "overnight_closed"


def _pick_price_and_time(data: dict[str, Any]) -> tuple[float, datetime | None, str]:
    """Use the most recent price among: last trade, minute bar close, NBBO mid, daily bar."""
    candidates: list[tuple[float, datetime | None, str]] = []

    lt = data.get("latestTrade") or {}
    if lt.get("p") is not None:
        try:
            candidates.append((float(lt["p"]), _parse_alpaca_time(lt.get("t")), "latest_trade"))
        except (TypeError, ValueError):
            pass

    mb = data.get("minuteBar") or {}
    if mb.get("c") is not None:
        try:
            candidates.append((float(mb["c"]), _parse_alpaca_time(mb.get("t")), "minute_bar"))
        except (TypeError, ValueError):
            pass

    lq = data.get("latestQuote") or {}
    try:
        bp = lq.get("bp")
        ap = lq.get("ap")
        if bp is not None and ap is not None:
            bpf, apf = float(bp), float(ap)
            if bpf > 0 and apf > 0:
                mid = (bpf + apf) / 2
                candidates.append((mid, _parse_alpaca_time(lq.get("t")), "quote_mid"))
    except (TypeError, ValueError):
        pass

    db = data.get("dailyBar") or {}
    if db.get("c") is not None:
        try:
            candidates.append((float(db["c"]), _parse_alpaca_time(db.get("t")), "daily_close"))
        except (TypeError, ValueError):
            pass

    if not candidates:
        return 0.0, None, "none"

    now = datetime.now(timezone.utc)

    def freshness(item: tuple[float, datetime | None, str]) -> tuple:
        price, ts, src = item
        prio = _SOURCE_PRIORITY.get(src, 0)
        far_past = datetime(1970, 1, 1, tzinfo=timezone.utc)
        age_sec = (now - ts).total_seconds() if ts else 999999
        # Prefer recent latest_trade/minute over stale quote mid
        if src in ("latest_trade", "minute_bar") and ts and age_sec < 900:
            prio += 10
        return (ts or far_past, prio)

    best = max(candidates, key=freshness)
    return best[0], best[1], best[2]


def _build_snapshot_dict(symbol: str, data: dict[str, Any]) -> dict[str, Any]:
    daily = data.get("dailyBar") or {}
    prev = data.get("prevDailyBar") or {}
    minute = data.get("minuteBar") or {}
    quote = data.get("latestQuote") or {}

    price, price_time, price_source = _pick_price_and_time(data)

    prev_close = float(prev.get("c") or 0)
    volume = int(daily.get("v") or 0)
    if not volume and minute.get("v"):
        volume = int(minute.get("v") or 0)

    vwap = float(daily.get("vw") or 0) or None
    bid = float(quote.get("bp") or 0) or None
    ask = float(quote.get("ap") or 0) or None

    spread_pct = None
    if bid and ask and bid > 0:
        spread_pct = round((ask - bid) / ((ask + bid) / 2) * 100, 3)

    pct = 0.0
    if prev_close:
        pct = round((price - prev_close) / prev_close * 100, 2)

    hod = float(daily.get("h") or 0) or None
    lod = float(daily.get("l") or 0) or None
    if minute:
        mh, ml = float(minute.get("h") or 0), float(minute.get("l") or 0)
        if mh > 0:
            hod = max(hod or 0, mh) or mh
        if ml > 0:
            lod = min(lod or ml, ml) if lod and ml else (lod or ml)

    return {
        "ticker": symbol.upper(),
        "price": price,
        "previous_close": prev_close,
        "percent_change": pct,
        "volume": volume,
        "bid": bid,
        "ask": ask,
        "spread_percent": spread_pct,
        "vwap": vwap,
        "above_vwap": (price >= vwap) if vwap and price else None,
        "hod": hod,
        "lod": lod,
        "open": float(daily.get("o") or 0) or None,
        "source": "alpaca",
        "price_as_of": price_time,
        "price_source": price_source,
        "session": _session_label(price_time),
    }


async def fetch_snapshots_batch(symbols: list[str]) -> dict[str, dict[str, Any]]:
    """Batch Alpaca snapshots — much faster than one request per symbol."""
    if not has_alpaca() or not symbols:
        return {}

    feed = (get_settings().alpaca_market_data_feed or "").strip().lower()
    base_params: dict[str, str] = {}
    if feed in ("sip", "iex", "otc"):
        base_params["feed"] = feed

    unique = list(dict.fromkeys(s.upper() for s in symbols if s))
    out: dict[str, dict[str, Any]] = {}
    chunk_size = 100

    async with http_client() as client:
        for i in range(0, len(unique), chunk_size):
            chunk = unique[i : i + chunk_size]
            params = {**base_params, "symbols": ",".join(chunk)}
            r = await client.get(
                f"{DATA_BASE}/stocks/snapshots",
                headers=_headers(),
                params=params,
            )
            if r.status_code != 200:
                continue
            payload = r.json()
            if not isinstance(payload, dict):
                continue
            for sym, snap_data in payload.items():
                if isinstance(snap_data, dict):
                    out[sym.upper()] = _build_snapshot_dict(sym, snap_data)
    return out


async def fetch_snapshot(symbol: str) -> dict[str, Any] | None:
    if not has_alpaca():
        return None

    feed = (get_settings().alpaca_market_data_feed or "").strip().lower()
    params: dict[str, str] = {}
    if feed in ("sip", "iex", "otc"):
        params["feed"] = feed

    async with http_client() as client:
        r = await client.get(
            f"{DATA_BASE}/stocks/{symbol.upper()}/snapshot",
            headers=_headers(),
            params=params or None,
        )
        if r.status_code == 404:
            return None
        r.raise_for_status()
        data = r.json()

    return _build_snapshot_dict(symbol, data)


async def fetch_movers(limit: int = 50) -> list[str]:
    """Return symbols from Alpaca most active if available."""
    if not has_alpaca():
        return []
    async with http_client() as client:
        r = await client.get(
            f"{DATA_BASE}/stocks/movers",
            headers=_headers(),
            params={"top": limit},
        )
        if r.status_code != 200:
            return []
        data = r.json()
    gainers = [g.get("symbol") for g in (data.get("gainers") or []) if g.get("symbol")]
    losers = [l.get("symbol") for l in (data.get("losers") or []) if l.get("symbol")]
    return list(dict.fromkeys(gainers + losers))[:limit]
