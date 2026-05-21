"""Feature engine — gap, RVOL, VWAP distance, catalyst flags."""

from datetime import datetime, timezone
from typing import Any


def compute_features(raw: dict[str, Any], catalysts: list[dict]) -> dict[str, Any]:
    price = float(raw.get("price") or 0)
    prev = float(raw.get("previous_close") or 0)
    volume = int(raw.get("volume") or 0)
    vwap = raw.get("vwap")
    hod = raw.get("hod")
    lod = raw.get("lod")
    avg_vol = float(raw.get("avg_volume") or volume / max(raw.get("relative_volume") or 1, 1))

    gap_pct = ((price - prev) / prev * 100) if prev else 0.0
    rvol = (volume / avg_vol) if avg_vol > 0 else float(raw.get("relative_volume") or 0)

    hod_dist = ((hod - price) / price * 100) if hod and price else None
    lod_dist = ((price - lod) / price * 100) if lod and price else None
    vwap_dist = ((price - vwap) / vwap * 100) if vwap and price else None

    dollar_volume = price * volume if price and volume else 0

    cat_types = [c.get("type", "") for c in catalysts]
    cat_quality = [c.get("quality", "medium") for c in catalysts]

    return {
        "gap_percent": round(gap_pct, 2),
        "intraday_percent": round(float(raw.get("percent_change") or gap_pct), 2),
        "relative_volume": round(rvol, 2),
        "dollar_volume": dollar_volume,
        "spread_percent": raw.get("spread_percent"),
        "above_vwap": raw.get("above_vwap"),
        "vwap_distance_pct": round(vwap_dist, 2) if vwap_dist is not None else None,
        "hod_distance_pct": round(hod_dist, 2) if hod_dist is not None else None,
        "lod_distance_pct": round(lod_dist, 2) if lod_dist is not None else None,
        "near_hod": hod_dist is not None and hod_dist < 1.5,
        "near_lod": lod_dist is not None and lod_dist < 1.5,
        "failed_hod_hint": hod_dist is not None and hod_dist > 3 and gap_pct > 15,
        "market_cap": raw.get("market_cap"),
        "float_shares": raw.get("float_shares") or raw.get("shares_outstanding"),
        "low_float": _is_low_float(raw),
        "parabolic": gap_pct > 40 or float(raw.get("percent_change") or 0) > 40,
        "catalyst_types": cat_types,
        "has_earnings": "earnings" in cat_types,
        "has_offering": "offering" in cat_types or "filing" in cat_types,
        "has_analyst": "analyst" in cat_types,
        "has_theme_hype": "theme_hype" in cat_types,
        "catalyst_quality_best": _best_quality(cat_quality),
        "stale_target": raw.get("stale_target", False),
        "price_above_target": raw.get("price_above_target", False),
        "data_available": raw.get("data_available", bool(raw.get("price"))),
    }


def _is_low_float(raw: dict) -> bool:
    fl = raw.get("float_shares") or raw.get("shares_outstanding")
    if fl and float(fl) < 50_000_000:
        return True
    return False


def _best_quality(qualities: list[str]) -> str:
    order = {"high": 3, "medium": 2, "low": 1}
    if not qualities:
        return "none"
    return max(qualities, key=lambda q: order.get(q, 0))
