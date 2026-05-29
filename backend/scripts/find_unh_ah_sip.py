"""Paginate SIP trades for UNH after-hours window."""
import asyncio
from datetime import datetime, timezone

from app.collectors.alpaca import DATA_BASE, _headers, _parse_alpaca_time
from app.collectors.base import http_client
from app.collectors.session_util import trade_session_key


async def main() -> None:
    start = "2026-05-21T20:00:00Z"
    end = "2026-05-22T00:00:00Z"
    token = None
    best = None
    page = 0
    while page < 20:
        params = {
            "feed": "sip",
            "start": start,
            "end": end,
            "limit": 10000,
        }
        if token:
            params["page_token"] = token
        async with http_client() as client:
            r = await client.get(
                f"{DATA_BASE}/stocks/UNH/trades",
                headers=_headers(),
                params=params,
            )
        if r.status_code != 200:
            print("stop", r.status_code)
            break
        data = r.json()
        trades = data.get("trades") or []
        for t in trades:
            p = float(t.get("p") or 0)
            ts = _parse_alpaca_time(t.get("t"))
            if trade_session_key(ts) != "afterhours":
                continue
            if best is None or (ts and best[0] and ts > best[0]):
                best = (ts, p)
        token = data.get("next_page_token")
        page += 1
        print("page", page, "trades", len(trades), "token", bool(token))
        if not token:
            break
    print("best ah", best)


if __name__ == "__main__":
    asyncio.run(main())
