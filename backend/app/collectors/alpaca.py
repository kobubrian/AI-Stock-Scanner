"""Alpaca market data — snapshot with extended-hours friendly price selection."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from app.collectors.base import has_alpaca, http_client
from app.collectors.session_util import current_session_label
from app.config import get_settings

_VALID_FEEDS = frozenset({"sip", "iex", "otc", "overnight", "boats"})

DATA_BASE = "https://data.alpaca.markets/v2"
_NY = ZoneInfo("America/New_York")

# Prefer fresher sources when timestamps tie or are missing
_SOURCE_PRIORITY = {
    "latest_trade": 4,
    "minute_bar": 3,
    "quote_mid": 2,
    "daily_close": 1,
}


def snapshot_feed_params() -> dict[str, str]:
    """
    Choose Alpaca data feed for snapshots.
    During 8pm-4am ET, use overnight/boats when enabled (requires Alpaca overnight data plan).
    See docs/OVERNIGHT_QUOTES.md
    """
    settings = get_settings()
    explicit = (settings.alpaca_market_data_feed or "").strip().lower()
    if explicit in _VALID_FEEDS:
        return {"feed": explicit}
    if settings.alpaca_use_overnight_session_feed:
        if current_session_label() == "overnight_closed":
            overnight = (settings.alpaca_overnight_feed or "overnight").strip().lower()
            if overnight in ("overnight", "boats"):
                return {"feed": overnight}
    return {}


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
            # Reject broken NBBO (e.g. ap=0) that produces nonsense mids.
            if bpf > 0 and apf > 0 and apf >= bpf * 0.5:
                mid = (bpf + apf) / 2
                if mid <= bpf * 5:
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
        age_sec = (now - ts).total_seconds() if ts else 999999
        prio = _SOURCE_PRIORITY.get(src, 0)
        # Newest timestamp wins; never use daily close if a fresher quote/trade exists.
        return (age_sec, -prio)

    best = min(candidates, key=freshness)
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

    base_params: dict[str, str] = snapshot_feed_params()

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


async def fetch_snapshot_data(symbol: str, *, feed: str | None = None) -> dict[str, Any] | None:
    """Raw Alpaca snapshot JSON for a specific feed (sip, overnight, boats, iex)."""
    if not has_alpaca():
        return None
    params: dict[str, str] = {}
    if feed and feed.lower() in _VALID_FEEDS:
        params["feed"] = feed.lower()
    async with http_client() as client:
        r = await client.get(
            f"{DATA_BASE}/stocks/{symbol.upper()}/snapshot",
            headers=_headers(),
            params=params or None,
        )
        if r.status_code in (404, 403, 422):
            return None
        if r.status_code != 200:
            return None
        data = r.json()
    return data if isinstance(data, dict) else None


def build_snapshot_from_data(symbol: str, data: dict[str, Any]) -> dict[str, Any]:
    return _build_snapshot_dict(symbol, data)


async def fetch_snapshot(symbol: str) -> dict[str, Any] | None:
    if not has_alpaca():
        return None
    params: dict[str, str] = snapshot_feed_params()
    feed = params.get("feed")
    data = await fetch_snapshot_data(symbol, feed=feed)
    if not data:
        return None
    return _build_snapshot_dict(symbol, data)


async def fetch_afterhours_from_trades(symbol: str) -> dict[str, Any] | None:
    """Last after-hours print from recent weekday 4–8 PM ET sessions (SIP preferred)."""
    from app.collectors.session_util import afterhours_utc_windows, trade_session_key

    if not has_alpaca():
        return None

    symbol = symbol.upper()
    best: tuple[float, datetime | None, str] | None = None

    for win_start, win_end in afterhours_utc_windows(lookback_days=10):
        for feed in ("sip", "iex"):
            page_token: str | None = None
            for _ in range(10):
                params: dict[str, str | int] = {
                    "feed": feed,
                    "start": win_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "end": win_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "limit": 10000,
                }
                if page_token:
                    params["page_token"] = page_token
                async with http_client() as client:
                    r = await client.get(
                        f"{DATA_BASE}/stocks/{symbol}/trades",
                        headers=_headers(),
                        params=params,
                    )
                if r.status_code == 403 and feed == "sip":
                    break
                if r.status_code != 200:
                    break
                data = r.json()
                trades = data.get("trades") or []
                if not isinstance(trades, list):
                    break
                for t in trades:
                    try:
                        price = float(t.get("p") or 0)
                        ts = _parse_alpaca_time(t.get("t"))
                    except (TypeError, ValueError):
                        continue
                    if price <= 0 or trade_session_key(ts) != "afterhours":
                        continue
                    if best is None or (ts and best[1] and ts > best[1]):
                        best = (price, ts, feed)
                page_token = data.get("next_page_token")
                if not page_token:
                    break
            if best and best[2] == "sip":
                break
        if best:
            break

    if not best:
        return None
    return {
        "price": best[0],
        "price_as_of": best[1],
        "price_source": f"ah_trades_{best[2]}",
    }


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
