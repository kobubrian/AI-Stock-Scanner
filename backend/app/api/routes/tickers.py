from fastapi import APIRouter, HTTPException

from app.collectors.market import fetch_ticker_snapshot
from app.models.ticker import TickerSnapshot

router = APIRouter(prefix="/tickers", tags=["tickers"])


@router.get("/{symbol}", response_model=TickerSnapshot)
async def get_ticker(symbol: str):
    snap = await fetch_ticker_snapshot(symbol.upper())
    if not snap.ticker:
        raise HTTPException(404, "Invalid symbol")
    return snap
