"""MVP market data — Alpaca primary, Finnhub enrich/fallback."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.collectors import alpaca, finnhub
from app.collectors.base import has_alpaca, has_finnhub
from app.collectors.session_util import current_session_label
from app.config import get_settings
from app.models.ticker import TickerSnapshot


def _price_age_seconds(price_as_of: Any) -> float:
    if price_as_of is None:
        return 999999.0
    if isinstance(price_as_of, datetime):
        ts = price_as_of
    else:
        try:
            s = str(price_as_of)
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            ts = datetime.fromisoformat(s)
        except ValueError:
            return 999999.0
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - ts).total_seconds()


async def reconcile_current_price(raw: dict[str, Any], symbol: str) -> dict[str, Any]:
    """
    Prefer Finnhub /quote when Alpaca last trade is stale or invalid.
    Matches Yahoo/Finnhub overnight 'current' better than an old after-hours print.
    """
    if not has_finnhub() or not raw.get("price"):
        raw["session"] = current_session_label()
        return raw

    alp_price = float(raw.get("price") or 0)
    age = _price_age_seconds(raw.get("price_as_of"))
    session_now = current_session_label()

    fq = await finnhub.fetch_quote(symbol)
    if not fq or not fq.get("price"):
        raw["session"] = session_now
        return raw

    fh_price = float(fq["price"])
    rel_diff = abs(alp_price - fh_price) / fh_price if fh_price else 0.0

    # Use Finnhub when Alpaca is stale, wrong, or missing (not when fresh overnight feed).
    use_finnhub = age > 900 or rel_diff > 0.02 or alp_price <= 0

    if use_finnhub:
        raw.update(
            {
                "price": fh_price,
                "previous_close": fq.get("previous_close") or raw.get("previous_close"),
                "percent_change": fq.get("percent_change", raw.get("percent_change")),
                "price_as_of": fq.get("price_as_of", raw.get("price_as_of")),
                "price_source": "finnhub_quote",
                "session": session_now,
                "source": "finnhub",
            }
        )
    else:
        raw["session"] = session_now

    return raw


def _market_cap_dollars(value: Any) -> float | None:
    """Normalize Finnhub/FMP market cap values to USD."""
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v <= 0:
        return None
    # Finnhub profile2/metrics report capitalization in millions.
    if v < 1_000_000:
        return v * 1_000_000
    return v


async def _enrich_market_cap(raw: dict[str, Any], symbol: str) -> None:
    if raw.get("market_cap"):
        raw["market_cap"] = _market_cap_dollars(raw["market_cap"])
        return

    if has_finnhub():
        profile = await finnhub.fetch_company_profile(symbol)
        mc = profile.get("marketCapitalization")
        if mc:
            raw["market_cap"] = _market_cap_dollars(mc)
            if profile.get("shareOutstanding") and not raw.get("shares_outstanding"):
                raw["shares_outstanding"] = float(profile["shareOutstanding"]) * 1_000_000
            if profile.get("finnhubIndustry") and not raw.get("sector"):
                raw["sector"] = profile.get("finnhubIndustry")
            return

    from app.collectors.base import has_fmp
    from app.collectors import fmp

    if has_fmp():
        profile = await fmp.fetch_profile(symbol)
        if profile:
            mc = profile.get("mktCap") or profile.get("marketCap")
            if mc:
                raw["market_cap"] = _market_cap_dollars(mc)


async def fetch_raw_market(
    symbol: str,
    *,
    enrich_fundamentals: bool = True,
    fetch_ah_trades: bool = True,
) -> dict[str, Any]:
    symbol = symbol.upper()
    raw: dict[str, Any] | None = None

    if has_alpaca():
        from app.collectors.session_prices import fetch_multi_session_market

        raw = await fetch_multi_session_market(symbol, fetch_ah_trades=fetch_ah_trades)

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

    if (
        raw.get("price")
        and int(raw.get("volume") or 0) <= 0
        and has_alpaca()
        and raw.get("source") != "alpaca"
    ):
        snap = await alpaca.fetch_snapshot_data(symbol, feed="iex")
        if snap:
            built = alpaca.build_snapshot_from_data(symbol, snap)
            vol = int(built.get("volume") or 0)
            if vol > 0:
                raw["volume"] = vol
                raw["vwap"] = raw.get("vwap") or built.get("vwap")
                raw["hod"] = raw.get("hod") or built.get("hod")
                raw["lod"] = raw.get("lod") or built.get("lod")

    # Alpaca snapshot already has session VWAP, volume, HOD/LOD — skip Finnhub
    # candles/metrics here to avoid blowing the free-tier rate limit (403/429).
    alpaca_ok = raw.get("source") == "alpaca" and raw.get("price")
    has_structure = bool(raw.get("vwap") and raw.get("volume"))

    if enrich_fundamentals and has_finnhub() and not (alpaca_ok and has_structure):
        bars = await finnhub.fetch_candles(symbol)
        finnhub.enrich_from_candles(raw, bars)

    if (
        enrich_fundamentals
        and has_finnhub()
        and get_settings().finnhub_fetch_metrics
        and not (alpaca_ok and raw.get("market_cap"))
    ):
        metrics = await finnhub.fetch_metrics(symbol)
        if metrics:
            raw["market_cap"] = _market_cap_dollars(metrics.get("marketCapitalization"))
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

    if enrich_fundamentals:
        if not raw.get("market_cap"):
            await _enrich_market_cap(raw, symbol)
        elif raw.get("market_cap"):
            raw["market_cap"] = _market_cap_dollars(raw["market_cap"])

    # Multi-session fetch already picks best quote; only Finnhub fill-in if still empty.
    if not raw.get("price") and has_finnhub():
        raw = await reconcile_current_price(raw, symbol)
    elif raw.get("source") != "finnhub":
        raw["session"] = raw.get("active_session") or raw.get("session") or current_session_label()
    return raw


async def fetch_ticker_snapshot(symbol: str) -> TickerSnapshot:
    from app.services.pipeline import build_snapshot

    return await build_snapshot(symbol)
