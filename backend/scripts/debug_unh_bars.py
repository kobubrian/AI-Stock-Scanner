import asyncio
from datetime import datetime, timedelta, timezone

import httpx

from app.collectors.alpaca import _headers, DATA_BASE
from app.config import get_settings


async def main() -> None:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=2)
    params = {
        "symbols": "UNH",
        "timeframe": "1Min",
        "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "limit": 10000,
        "feed": "iex",
    }
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.get(
            f"{DATA_BASE}/stocks/UNH/bars", headers=_headers(), params=params
        )
        print("status", r.status_code)
        data = r.json()
    bars = (data.get("bars") or {}).get("UNH") or []
    print("bars count", len(bars))
    # last bars around 20-24 UTC
    for b in bars[-30:]:
        print(b.get("t"), b.get("c"), b.get("v"))


asyncio.run(main())
