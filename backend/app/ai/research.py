"""OpenAI structured research for top candidates."""

import json
from typing import Any

from openai import AsyncOpenAI

from app.ai.prompts import TICKER_RESEARCH_SYSTEM, build_ticker_prompt
from app.collectors.base import has_openai
from app.config import get_settings
from app.db.models import AIResearchRow
from app.db.session import async_session
from app.models.ticker import TickerSnapshot


async def analyze_ticker(snapshot: TickerSnapshot) -> dict[str, Any]:
    settings = get_settings()
    account = {
        "balance": settings.account_balance,
        "pdt_restricted": settings.account_pdt_restricted,
        "max_risk": settings.max_risk_per_trade,
    }

    if not has_openai():
        return _offline_analysis(snapshot)

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    prompt = build_ticker_prompt(snapshot.model_dump(mode="json"), account)

    response = await client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": TICKER_RESEARCH_SYSTEM},
            {"role": "user", "content": prompt + "\nRespond with JSON only."},
        ],
        response_format={"type": "json_object"},
        temperature=0.3,
    )
    text = response.choices[0].message.content or "{}"
    result = json.loads(text)

    async with async_session() as session:
        session.add(
            AIResearchRow(
                symbol=snapshot.ticker,
                request_json=json.dumps({"prompt": prompt[:2000]}),
                response_json=json.dumps(result),
            )
        )
        await session.commit()

    return result


def _offline_analysis(snapshot: TickerSnapshot) -> dict[str, Any]:
    """Rule-based fallback when OPENAI_API_KEY is missing."""
    bias = "neutral"
    if snapshot.scores.long_score > snapshot.scores.short_score + 15:
        bias = "long"
    elif snapshot.scores.short_score > snapshot.scores.long_score + 15:
        bias = "short"
    if snapshot.scores.squeeze_risk >= 75:
        bias = "avoid"

    return {
        "ticker": snapshot.ticker,
        "bias": bias,
        "timeframe": "daytrade",
        "long_score": snapshot.scores.long_score,
        "short_score": snapshot.scores.short_score,
        "squeeze_risk": snapshot.scores.squeeze_risk,
        "catalyst_quality": "medium" if snapshot.catalysts else "none",
        "current_price": snapshot.price,
        "fair_value_estimate": "Requires FMP/analyst data or OpenAI",
        "entry_zone": snapshot.trade_plan.entry_trigger,
        "stop_loss": snapshot.trade_plan.stop,
        "targets": [
            t
            for t in [
                snapshot.trade_plan.target_1,
                snapshot.trade_plan.target_2,
                snapshot.trade_plan.target_3,
            ]
            if t
        ],
        "action_tree": _action_tree(snapshot, bias),
        "key_risks": _key_risks(snapshot),
        "news_summary": "; ".join(c.summary for c in snapshot.catalysts[:3]) or "No headlines (add BENZINGA_API_KEY)",
        "valuation_summary": "Add FMP_API_KEY for analyst targets",
        "confidence": "low",
        "avoid_reason": "Active squeeze — do not blind short" if snapshot.scores.squeeze_risk >= 75 else None,
        "source": "offline_rules",
    }


def _action_tree(snapshot: TickerSnapshot, bias: str) -> str:
    if bias == "long":
        return "1) Confirm above VWAP 2) Buy pullback 3) Stop below VWAP 4) Scale at targets"
    if bias == "short":
        return "1) Wait for failed HOD 2) Entry on VWAP loss 3) Stop above failed high 4) Cover in fragments"
    if bias == "avoid":
        return "Do not trade — squeeze risk elevated; wait for failure confirmation"
    return "No edge — wait for catalyst or structure"


def _key_risks(snapshot: TickerSnapshot) -> list[str]:
    risks = []
    if snapshot.scores.squeeze_risk >= 60:
        risks.append("Squeeze / low float")
    if snapshot.spread_percent and snapshot.spread_percent > 1.5:
        risks.append(f"Wide spread {snapshot.spread_percent}%")
    if not snapshot.data_available:
        risks.append("No live market data — add POLYGON_API_KEY or ALPACA keys")
    return risks or ["Standard intraday volatility"]
