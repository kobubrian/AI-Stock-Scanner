from fastapi import APIRouter, HTTPException

from app.ai import research as ai_research
from app.collectors.market import fetch_ticker_snapshot

router = APIRouter(prefix="/research", tags=["research"])


@router.get("/{symbol}")
async def research_ticker(symbol: str):
    snapshot = await fetch_ticker_snapshot(symbol.upper())
    if not snapshot.ticker:
        raise HTTPException(404, "Ticker not found")
    analysis = await ai_research.analyze_ticker(snapshot)
    return {"snapshot": snapshot, "analysis": analysis}
