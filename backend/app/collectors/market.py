"""MVP market data — Alpaca primary, Finnhub enrich/fallback."""

from typing import Any

from app.collectors import alpaca, finnhub
from app.collectors.base import has_alpaca, has_finnhub
from app.config import get_settings
from app.models.ticker import TickerSnapshot


async def fetch_raw_market(symbol: str) -> dict[str, Any]:
    symbol = symbol.upper()
    raw: dict[str, Any] | None = None

    if has_alpaca():
        raw = await alpaca.fetch_snapshot(symbol)

    if (not raw or not raw.get("price")) and has_finnhub():
        raw = await finnhub.fetch_quote(symbol)

    if not raw:
        return {
            "ticker": symbol,
            "price": 0.0,
            "previous_close": 0.0,
            "percent_change": 0.0,
            "volume": 0,
            "source": "none",
            "data_available": False,
        }

    raw["ticker"] = symbol
    raw["data_available"] = bool(raw.get("price"))

    # Alpaca snapshot already has session VWAP, volume, HOD/LOD — skip Finnhub
    # candles/metrics here to avoid blowing the free-tier rate limit (403/429).
    alpaca_ok = raw.get("source") == "alpaca" and raw.get("price")
    has_structure = bool(raw.get("vwap") and raw.get("volume"))

    if has_finnhub() and not (alpaca_ok and has_structure):
        bars = await finnhub.fetch_candles(symbol)
        finnhub.enrich_from_candles(raw, bars)

    if (
        has_finnhub()
        and get_settings().finnhub_fetch_metrics
        and not (alpaca_ok and raw.get("market_cap"))
    ):
        metrics = await finnhub.fetch_metrics(symbol)
        if metrics:
            raw["market_cap"] = metrics.get("marketCapitalization")
            raw["shares_outstanding"] = metrics.get("shareOutstanding")
            raw["float_shares"] = metrics.get("floatShares") or metrics.get(
                "shareOutstanding"
            )
            avg_vol = metrics.get("10DayAverageTradingVolume") or metrics.get(
                "3MonthAverageTradingVolume"
            )
            if avg_vol and raw.get("volume"):
                raw["avg_volume"] = float(avg_vol) * 1_000_000
                raw["relative_volume"] = round(
                    raw["volume"] / raw["avg_volume"], 2
                )

    return raw


async def fetch_ticker_snapshot(symbol: str) -> TickerSnapshot:
    from app.services.pipeline import build_snapshot

    return await build_snapshot(symbol)
