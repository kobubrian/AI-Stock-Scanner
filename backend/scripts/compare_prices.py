import asyncio

from app.collectors.session_prices import fetch_multi_session_market
from app.collectors.session_util import current_session_label


async def main() -> None:
    print("session now:", current_session_label())
    for sym in ["UNH", "AAPL", "TSLA", "NVDA"]:
        r = await fetch_multi_session_market(sym)
        print(
            sym,
            "| active:", r.get("active_session"),
            "| now:", r.get("price"),
            "| close:", r.get("regular_close"),
            "| AH:", r.get("afterhours_price"),
            "| ON:", r.get("overnight_price"),
            "| PM:", r.get("premarket_price"),
        )


if __name__ == "__main__":
    asyncio.run(main())
