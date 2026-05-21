from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.alerts import list_alerts

router = APIRouter(prefix="/alerts", tags=["alerts"])


class AlertOut(BaseModel):
    id: int
    symbol: str
    alert_type: str
    message: str
    created_at: datetime


@router.get("", response_model=list[AlertOut])
async def get_alerts(limit: int = 50):
    rows = await list_alerts(limit)
    return [
        AlertOut(
            id=r.id,
            symbol=r.symbol,
            alert_type=r.alert_type,
            message=r.message,
            created_at=r.created_at,
        )
        for r in rows
    ]
