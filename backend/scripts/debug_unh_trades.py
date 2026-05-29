import asyncio

import httpx

from app.collectors.alpaca import _headers, _parse_alpaca_time, _session_label, DATA_BASE
from app.collectors.session_util import trade_session_key


async def main() -> None:
    params = {
        "feed": "iex",
        "limit": 1000,
        "start": "2026-05-21T20:00:00Z",
        "end": "2026-05-22T04:00:00Z",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            f"{DATA_BASE}/stocks/UNH/trades",
            headers=_headers(),
            params=params,
        )
        print("status", r.status_code)
        data = r.json()
    trades = data.get("trades") or []
    print("trades", len(trades))
    for t in trades[-20:]:
        ts = _parse_alpaca_time(t.get("t"))
        key = trade_session_key(ts)
        print(ts, key, t.get("p"), t.get("s"))


asyncio.run(main())
