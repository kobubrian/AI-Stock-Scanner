from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class Catalyst(BaseModel):
    type: str = ""
    summary: str = ""
    quality: str = ""
    source: str = ""
    timestamp: datetime | None = None


class Scores(BaseModel):
    long_score: float = 0.0
    short_score: float = 0.0
    squeeze_risk: float = 0.0
    catalyst_quality: float = 0.0
    overnight_long_score: float = 0.0
    overnight_short_score: float = 0.0
    liquidity_score: float = 0.0
    valuation_stretch_score: float = 0.0


class TradePlan(BaseModel):
    entry_trigger: str = ""
    stop: float | None = None
    target_1: float | None = None
    target_2: float | None = None
    target_3: float | None = None


class TickerSnapshot(BaseModel):
    ticker: str
    price: float = 0.0
    previous_close: float = 0.0
    percent_change: float = 0.0
    volume: int = 0
    relative_volume: float = 0.0
    market_cap: float | None = None
    bid: float | None = None
    ask: float | None = None
    spread_percent: float | None = None
    vwap: float | None = None
    above_vwap: bool | None = None
    hod: float | None = None
    lod: float | None = None
    gap_percent: float | None = None
    dollar_volume: float | None = None
    float_shares: float | None = None
    sector: str | None = None
    price_as_of: datetime | None = None
    price_source: str = ""
    session: str = ""
    active_session: str = ""
    price_session: str = ""
    regular_close: float | None = None
    afterhours_price: float | None = None
    afterhours_percent_change: float | None = None
    premarket_price: float | None = None
    overnight_price: float | None = None
    market_price: float | None = None
    catalysts: list[Catalyst] = Field(default_factory=list)
    analyst_targets: list[dict[str, Any]] = Field(default_factory=list)
    last_news_time: datetime | None = None
    scores: Scores = Field(default_factory=Scores)
    trade_plan: TradePlan = Field(default_factory=TradePlan)
    score_breakdown: dict[str, float] = Field(default_factory=dict)
    data_source: str = "none"
    data_available: bool = False
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def example(cls, symbol: str) -> "TickerSnapshot":
        return cls(ticker=symbol.upper(), data_available=False)
