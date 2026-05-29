import asyncio

from app.collectors.alpaca import _parse_alpaca_time, _session_label, fetch_snapshot_data


async def main() -> None:
    for feed in ("sip", "overnight", "iex"):
        d = await fetch_snapshot_data("UNH", feed=feed)
        print("=== feed", feed, "===")
        if not d:
            print("no data")
            continue
        for k in ("latestTrade", "latestQuote", "minuteBar", "dailyBar", "prevDailyBar"):
            block = d.get(k) or {}
            ts = _parse_alpaca_time(block.get("t"))
            print(k, block, "sess", _session_label(ts))


asyncio.run(main())
