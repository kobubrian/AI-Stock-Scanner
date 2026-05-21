"""In-app alerts from scan results."""

from sqlalchemy import select

from app.db.models import AlertRow
from app.db.session import async_session
from app.models.ticker import TickerSnapshot


async def evaluate_alerts(snapshots: list[TickerSnapshot]) -> list[AlertRow]:
    new_alerts: list[AlertRow] = []
    for snap in snapshots:
        if snap.scores.squeeze_risk >= 75:
            new_alerts.append(
                AlertRow(
                    symbol=snap.ticker,
                    alert_type="squeeze_risk",
                    message=f"{snap.ticker}: SqueezeRisk {snap.scores.squeeze_risk:.0f} — avoid blind shorts",
                )
            )
        if snap.scores.long_score >= 70 and snap.above_vwap:
            new_alerts.append(
                AlertRow(
                    symbol=snap.ticker,
                    alert_type="long_setup",
                    message=f"{snap.ticker}: LongScore {snap.scores.long_score:.0f}, above VWAP",
                )
            )
        if snap.scores.short_score >= 70 and snap.above_vwap is False:
            new_alerts.append(
                AlertRow(
                    symbol=snap.ticker,
                    alert_type="short_setup",
                    message=f"{snap.ticker}: ShortScore {snap.scores.short_score:.0f}, below VWAP",
                )
            )
        if snap.spread_percent and snap.spread_percent > 2:
            new_alerts.append(
                AlertRow(
                    symbol=snap.ticker,
                    alert_type="wide_spread",
                    message=f"{snap.ticker}: spread {snap.spread_percent:.2f}%",
                )
            )

    if new_alerts:
        async with async_session() as session:
            session.add_all(new_alerts)
            await session.commit()
    return new_alerts


async def list_alerts(limit: int = 50) -> list[AlertRow]:
    async with async_session() as session:
        result = await session.execute(
            select(AlertRow).order_by(AlertRow.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())
