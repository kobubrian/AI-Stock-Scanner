"""Find UNH after-hours prints near 386.92."""
import asyncio
from datetime import datetime, timezone

from app.collectors.alpaca import DATA_BASE, _headers, _parse_alpaca_time
from app.collectors.base import http_client
from app.collectors.session_util import trade_session_key


async def scan_trades(feed: str, start: str, end: str) -> None:
    params = {"feed": feed, "start": start, "end": end, "limit": 10000}
    async with http_client() as client:
        r = await client.get(
            f"{DATA_BASE}/stocks/UNH/trades",
            headers=_headers(),
            params=params,
        )
    if r.status_code != 200:
        print(feed, "status", r.status_code)
        return
    trades = r.json().get("trades") or []
    ah = []
    for t in trades:
        p = float(t.get("p") or 0)
        ts = _parse_alpaca_time(t.get("t"))
        if trade_session_key(ts) == "afterhours":
            ah.append((ts, p))
    ah.sort(key=lambda x: x[0] or datetime.min.replace(tzinfo=timezone.utc))
    print(feed, "total", len(trades), "ah", len(ah))
    if ah:
        print("  last 5 ah:", ah[-5:])
        near = [x for x in ah if 386.5 < x[1] < 387.5]
        print("  near 386.92:", near[-10:])


async def scan_bars(feed: str) -> None:
    from datetime import timedelta

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=3)
    params = {
        "feed": feed,
        "timeframe": "1Min",
        "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "limit": 10000,
    }
    async with http_client() as client:
        r = await client.get(
            f"{DATA_BASE}/stocks/UNH/bars",
            headers=_headers(),
            params=params,
        )
    print("bars", feed, r.status_code)
    if r.status_code != 200:
        return
    bl = r.json().get("bars") or []
    ah_b = []
    for b in bl:
        ts = _parse_alpaca_time(b.get("t"))
        if trade_session_key(ts) == "afterhours":
            ah_b.append((ts, float(b.get("c") or 0)))
    ah_b.sort(key=lambda x: x[0])
    print("  ah bars", len(ah_b), "last", ah_b[-3:] if ah_b else None)


async def find_price(feed: str, target: float = 386.92) -> None:
    from datetime import timedelta

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=4)
    params = {
        "feed": feed,
        "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "limit": 10000,
    }
    async with http_client() as client:
        r = await client.get(
            f"{DATA_BASE}/stocks/UNH/trades",
            headers=_headers(),
            params=params,
        )
    if r.status_code != 200:
        print("find", feed, r.status_code)
        return
    trades = r.json().get("trades") or []
    hits = []
    for t in trades:
        p = float(t.get("p") or 0)
        if abs(p - target) < 0.02:
            ts = _parse_alpaca_time(t.get("t"))
            hits.append((ts, p, trade_session_key(ts)))
    hits.sort(key=lambda x: x[0] or datetime.min.replace(tzinfo=timezone.utc))
    print(feed, f"hits near {target}:", len(hits))
    for row in hits[-8:]:
        print(" ", row)


async def main() -> None:
    await scan_trades("iex", "2026-05-22T20:00:00Z", "2026-05-23T00:00:00Z")
    await scan_trades("sip", "2026-05-22T20:00:00Z", "2026-05-23T00:00:00Z")
    await find_price("sip")
    await find_price("iex")


if __name__ == "__main__":
    asyncio.run(main())
