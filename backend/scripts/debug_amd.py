import asyncio

from app.collectors import finnhub
from app.collectors.alpaca import fetch_afterhours_from_trades, fetch_snapshot_data
from app.collectors.session_prices import fetch_multi_session_market
from app.collectors.session_util import current_session_label


async def main() -> None:
    print("session:", current_session_label())
    fq = await finnhub.fetch_quote("AMD")
    print("finnhub:", fq)
    ah = await fetch_afterhours_from_trades("AMD")
    print("ah trades:", ah)
    for feed in ("iex", "overnight", "boats"):
        d = await fetch_snapshot_data("AMD", feed=feed)
        lt = (d or {}).get("latestTrade") or {}
        print(f"snapshot {feed}:", lt.get("p"), lt.get("t"))
    r = await fetch_multi_session_market("AMD")
    skip = {"session_quotes"}
    print("multi:", {k: v for k, v in r.items() if k not in skip})


if __name__ == "__main__":
    asyncio.run(main())
