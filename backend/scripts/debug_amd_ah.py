import asyncio

from app.collectors.alpaca import _parse_alpaca_time, fetch_snapshot_data
from app.collectors.session_prices import _classify_sip_snapshot
from app.collectors.session_util import trade_session_key


async def main() -> None:
    d = await fetch_snapshot_data("AMD", feed="iex")
    if not d:
        return
    for k in ("latestTrade", "minuteBar", "latestQuote"):
        b = d.get(k) or {}
        ts = _parse_alpaca_time(b.get("t"))
        print(k, b.get("p") or b.get("c"), ts, trade_session_key(ts))
    cls = _classify_sip_snapshot(d, 449.44)
    print("classified ah:", cls.get("afterhours"))


if __name__ == "__main__":
    asyncio.run(main())
