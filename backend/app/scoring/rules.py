"""Weighted scoring per blueprint: catalyst 25%, price/VWAP 20%, volume 15%, valuation 15%, sentiment 10%, squeeze 10%, overnight 5%."""

from app.models.ticker import Scores, TradePlan


def score_ticker(features: dict, catalysts: list) -> tuple[Scores, TradePlan, dict]:
    catalyst_s = _catalyst_score(features, catalysts)
    price_s = _price_structure_score(features)
    volume_s = _volume_liquidity_score(features)
    valuation_s = _valuation_score(features)
    sentiment_s = _sentiment_score(features)
    squeeze_s = _squeeze_risk_score(features)
    overnight_s = _overnight_score(features)

    composite_long = (
        catalyst_s * 0.25
        + price_s * 0.20
        + volume_s * 0.15
        + valuation_s * 0.15
        + sentiment_s * 0.10
        + (100 - squeeze_s) * 0.10
        + overnight_s * 0.05
    )
    composite_short = (
        (100 - catalyst_s) * 0.20
        + (100 - price_s) * 0.25
        + volume_s * 0.15
        + valuation_s * 0.20
        + (100 - sentiment_s) * 0.10
        + squeeze_s * 0.05
        + (100 - overnight_s) * 0.05
    )

    scores = Scores(
        long_score=_clamp(composite_long),
        short_score=_clamp(composite_short),
        squeeze_risk=_clamp(squeeze_s),
        catalyst_quality=_clamp(catalyst_s),
        overnight_long_score=_clamp(overnight_s),
        overnight_short_score=_clamp(100 - overnight_s),
        liquidity_score=_clamp(volume_s),
        valuation_stretch_score=_clamp(valuation_s),
    )
    price = float(features.get("price") or 0)
    plan = build_trade_plan(price, features, scores)
    breakdown = {
        "catalyst": catalyst_s,
        "price_vwap": price_s,
        "volume_liquidity": volume_s,
        "valuation": valuation_s,
        "sentiment": sentiment_s,
        "squeeze_risk": squeeze_s,
        "overnight": overnight_s,
    }
    return scores, plan, breakdown


def _catalyst_score(features: dict, catalysts: list) -> float:
    if features.get("has_offering"):
        return 15.0
    q = features.get("catalyst_quality_best", "none")
    if q == "high" or features.get("has_earnings"):
        return 90.0
    if q == "medium" or features.get("has_analyst"):
        return 60.0
    if features.get("has_theme_hype"):
        return 35.0
    if catalysts:
        return 45.0
    return 25.0


def _price_structure_score(features: dict) -> float:
    s = 50.0
    if features.get("above_vwap"):
        s += 25
    else:
        s -= 20
    if features.get("near_hod"):
        s += 10
    if features.get("failed_hod_hint"):
        s -= 15
    if features.get("parabolic"):
        s -= 20
    return _clamp(s)


def _volume_liquidity_score(features: dict) -> float:
    rvol = float(features.get("relative_volume") or 0)
    spread = features.get("spread_percent")
    s = min(rvol * 12, 70)
    if spread is not None:
        if spread < 0.5:
            s += 25
        elif spread > 2:
            s -= 25
    dv = float(features.get("dollar_volume") or 0)
    if dv > 50_000_000:
        s += 10
    return _clamp(s)


def _valuation_score(features: dict) -> float:
    if features.get("stale_target") and features.get("price_above_target"):
        return 75.0
    if features.get("price_above_target"):
        return 65.0
    return 40.0


def _sentiment_score(features: dict) -> float:
    if features.get("has_theme_hype"):
        return 70.0
    if features.get("parabolic"):
        return 65.0
    return 45.0


def _squeeze_risk_score(features: dict) -> float:
    s = 20.0
    if features.get("low_float"):
        s += 30
    if float(features.get("relative_volume") or 0) > 5:
        s += 25
    if features.get("has_theme_hype"):
        s += 20
    if features.get("above_vwap"):
        s += 15
    if features.get("parabolic"):
        s += 15
    spread = features.get("spread_percent")
    if spread and spread > 2:
        s += 10
    return _clamp(s)


def _overnight_score(features: dict) -> float:
    s = 50.0
    if features.get("above_vwap") and features.get("near_hod"):
        s += 25
    if features.get("has_offering"):
        s -= 30
    if features.get("parabolic"):
        s -= 20
    return _clamp(s)


def build_trade_plan(price: float, features: dict, scores: Scores) -> TradePlan:
    if price <= 0:
        return TradePlan()
    atr_est = price * 0.03
    if scores.long_score >= scores.short_score:
        stop = round(price - atr_est * 1.5, 2)
        t1 = round(price + atr_est, 2)
        t2 = round(price + atr_est * 2, 2)
        t3 = round(price + atr_est * 3, 2)
        trigger = "Pullback to VWAP or reclaim; avoid vertical chase"
    else:
        stop = round(price + atr_est * 1.5, 2)
        t1 = round(price - atr_est, 2)
        t2 = round(price - atr_est * 2, 2)
        t3 = round(price - atr_est * 3, 2)
        trigger = "Failed HOD / VWAP loss / lower high; no blind short squeeze"
    return TradePlan(
        entry_trigger=trigger,
        stop=stop,
        target_1=t1,
        target_2=t2,
        target_3=t3,
    )


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, round(v, 1)))
