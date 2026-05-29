"""Debug why fetch_afterhours_from_trades returns None for AMD."""
import asyncio
from datetime import datetime, timedelta, timezone

from app.collectors.alpaca import DATA_BASE, _headers
from app.collectors.base import http_client
from app.collectors.session_util import current_session_label, trade_session_key


async def probe(feed: str, start: str, end: str) -> None:
    params = {"feed": feed, "start": start, "end": end, "limit": 10000}
    async with http_client() as client:
        r = await client.get(
            f"{DATA_BASE}/stocks/AMD/trades",
            headers=_headers(),
            params=params,
        )
    print(f"\n{feed} {start} -> {end} status={r.status_code}")
    if r.status_code != 200:
        print(r.text[:300])
        return
    trades = r.json().get("trades") or []
    ah = []
    for t in trades:
        ts_s = t.get("t")
        from app.collectors.alpaca import _parse_alpaca_time

        ts = _parse_alpaca_time(ts_s)
        if trade_session_key(ts) == "afterhours":
            ah.append((ts, float(t.get("p") or 0)))
    ah.sort(key=lambda x: x[0])
    print("  trades", len(trades), "ah", len(ah), "last", ah[-3:] if ah else None)


async def main() -> None:
    print("session", current_session_label())
    end = datetime.now(timezone.utc)
    for days_ago in range(2):
        day_end = end - timedelta(days=days_ago)
        day_start = day_end - timedelta(hours=30)
        s = day_start.strftime("%Y-%m-%dT%H:%M:%SZ")
        e = day_end.strftime("%Y-%m-%dT%H:%M:%SZ")
        await probe("sip", s, e)
        await probe("iex", s, e)

    # explicit Friday AH window May 22
    await probe("sip", "2026-05-22T20:00:00Z", "2026-05-23T00:00:00Z")

    from app.collectors.alpaca import fetch_afterhours_from_trades

    print("\nfetch_afterhours_from_trades:", await fetch_afterhours_from_trades("AMD"))


if __name__ == "__main__":
    asyncio.run(main())
