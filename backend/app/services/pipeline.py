"""Collect -> features -> score -> snapshot."""

from datetime import datetime, timezone
from typing import Any

from app.collectors import market as market_collector
from app.collectors import news, sec
from app.collectors.market import fetch_raw_market
from app.features.engine import compute_features
from app.models.ticker import Catalyst, TickerSnapshot
from app.scoring.rules import score_ticker


def _session_fields(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "price_as_of": raw.get("price_as_of"),
        "price_source": str(raw.get("price_source") or ""),
        "session": str(raw.get("session") or raw.get("active_session") or ""),
        "active_session": str(raw.get("active_session") or raw.get("session") or ""),
        "price_session": str(raw.get("price_session") or ""),
        "regular_close": raw.get("regular_close"),
        "afterhours_price": raw.get("afterhours_price"),
        "afterhours_percent_change": raw.get("afterhours_percent_change"),
        "premarket_price": raw.get("premarket_price"),
        "overnight_price": raw.get("overnight_price"),
        "market_price": raw.get("market_price"),
    }


async def build_snapshot(
    symbol: str,
    *,
    include_news: bool = True,
    fetch_ah_trades: bool = False,
) -> TickerSnapshot:
    raw = await fetch_raw_market(symbol, fetch_ah_trades=fetch_ah_trades)
    raw["price"] = float(raw.get("price") or 0)

    catalyst_dicts: list = []
    if include_news:
        headlines = await news.fetch_headlines(symbol)
        filings = await sec.fetch_recent_filings(symbol)
        catalyst_dicts = headlines + filings
    catalysts = [Catalyst(**{k: c[k] for k in Catalyst.model_fields if k in c}) for c in catalyst_dicts]

    _apply_analyst_targets(raw)
    if catalyst_dicts:
        latest = max(
            (c.get("timestamp") for c in catalyst_dicts if c.get("timestamp")),
            default=None,
            key=lambda x: x or datetime.min.replace(tzinfo=timezone.utc),
        )
        raw["last_news_time"] = latest

    features = compute_features(raw, catalyst_dicts)
    features["price"] = raw["price"]
    scores, plan, breakdown = score_ticker(features, catalyst_dicts)

    avg_vol = raw.get("avg_volume")
    rvol = features.get("relative_volume", 0)

    return TickerSnapshot(
        ticker=symbol.upper(),
        price=raw["price"],
        previous_close=float(raw.get("previous_close") or 0),
        percent_change=float(raw.get("percent_change") or features.get("intraday_percent") or 0),
        volume=int(raw.get("volume") or 0),
        relative_volume=rvol,
        market_cap=raw.get("market_cap"),
        bid=raw.get("bid"),
        ask=raw.get("ask"),
        spread_percent=raw.get("spread_percent"),
        vwap=raw.get("vwap"),
        above_vwap=raw.get("above_vwap"),
        hod=raw.get("hod"),
        lod=raw.get("lod"),
        gap_percent=features.get("gap_percent"),
        dollar_volume=features.get("dollar_volume"),
        float_shares=raw.get("float_shares"),
        sector=raw.get("sector"),
        catalysts=catalysts,
        analyst_targets=raw.get("analyst_targets") or [],
        last_news_time=raw.get("last_news_time"),
        scores=scores,
        trade_plan=plan,
        score_breakdown=breakdown,
        data_source=raw.get("source", "none"),
        data_available=features.get("data_available", False),
        updated_at=datetime.now(timezone.utc),
        **_session_fields(raw),
    )


def _apply_analyst_targets(raw: dict[str, Any]) -> None:
    targets = raw.get("analyst_targets") or []
    price = float(raw.get("price") or 0)
    if not targets or not price:
        raw["stale_target"] = False
        raw["price_above_target"] = False
        return
    t = targets[0] if isinstance(targets[0], dict) else {}
    target_price = float(
        t.get("targetConsensus")
        or t.get("lastPriceTarget")
        or t.get("priceTarget")
        or 0
    )
    raw["price_above_target"] = target_price > 0 and price > target_price
    raw["stale_target"] = True


async def build_snapshot_from_raw(raw: dict[str, Any]) -> TickerSnapshot:
    symbol = raw.get("ticker", "UNK")
    headlines = await news.fetch_headlines(symbol)
    filings = await sec.fetch_recent_filings(symbol)
    catalyst_dicts = headlines + filings
    catalysts = [Catalyst(**{k: c[k] for k in Catalyst.model_fields if k in c}) for c in catalyst_dicts]
    features = compute_features(raw, catalyst_dicts)
    features["price"] = float(raw.get("price") or 0)
    scores, plan, breakdown = score_ticker(features, catalyst_dicts)
    return TickerSnapshot(
        ticker=symbol.upper(),
        price=features["price"],
        previous_close=float(raw.get("previous_close") or 0),
        percent_change=float(raw.get("percent_change") or 0),
        volume=int(raw.get("volume") or 0),
        relative_volume=features.get("relative_volume", 0),
        market_cap=raw.get("market_cap"),
        bid=raw.get("bid"),
        ask=raw.get("ask"),
        spread_percent=raw.get("spread_percent"),
        vwap=raw.get("vwap"),
        above_vwap=raw.get("above_vwap"),
        hod=raw.get("hod"),
        lod=raw.get("lod"),
        gap_percent=features.get("gap_percent"),
        dollar_volume=features.get("dollar_volume"),
        catalysts=catalysts,
        **_session_fields(raw),
        analyst_targets=raw.get("analyst_targets") or [],
        scores=scores,
        trade_plan=plan,
        score_breakdown=breakdown,
        data_source=raw.get("source", "none"),
        data_available=features.get("data_available", False),
        updated_at=datetime.now(timezone.utc),
    )
