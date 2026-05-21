"""Market regime strip — SPY, QQQ, IWM, SOXX, VIX proxies."""

from fastapi import APIRouter

from app.collectors.base import has_fmp, has_polygon
from app.services.pipeline import build_snapshot

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
            snap = await build_snapshot(sym)
            items.append(
                {
                    "symbol": sym,
                    "label": label,
                    "price": snap.price,
                    "change_pct": snap.percent_change,
                    "above_vwap": snap.above_vwap,
                    "data_available": snap.data_available,
                }
            )
        except Exception:
            items.append(
                {"symbol": sym, "label": label, "price": None, "change_pct": None, "data_available": False}
            )
    return {
        "items": items,
        "keys_configured": {
            "polygon": has_polygon(),
            "fmp": has_fmp(),
        },
        "note": "Add POLYGON_API_KEY or ALPACA keys for live regime data",
    }
