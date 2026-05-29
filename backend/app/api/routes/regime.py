"""Market regime strip — SPY, QQQ, IWM, SOXX, VIX proxies."""

from fastapi import APIRouter

from app.collectors.base import has_alpaca, has_finnhub, has_fmp, has_polygon
from app.collectors.market import fetch_raw_market

router = APIRouter(prefix="/regime", tags=["regime"])

REGIME_SYMBOLS = [
    ("SPY", "S&P 500"),
    ("QQQ", "Nasdaq"),
    ("IWM", "Russell 2000"),
    ("SOXX", "Semis"),
    ("XBI", "Biotech"),
    ("FXI", "China large-cap"),
]


@router.get("")
async def market_regime():
    items = []
    for sym, label in REGIME_SYMBOLS:
        try:
            raw = await fetch_raw_market(sym, enrich_fundamentals=False)
            items.append(
                {
                    "symbol": sym,
                    "label": label,
                    "price": raw.get("price"),
                    "change_pct": raw.get("percent_change"),
                    "above_vwap": raw.get("above_vwap"),
                    "data_available": bool(raw.get("price")),
                }
            )
        except Exception:
            items.append(
                {"symbol": sym, "label": label, "price": None, "change_pct": None, "data_available": False}
            )
    return {
        "items": items,
        "keys_configured": {
            "alpaca": has_alpaca(),
            "finnhub": has_finnhub(),
            "polygon": has_polygon(),
            "fmp": has_fmp(),
        },
        "note": "Quotes only — does not run a scanner",
    }
