from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from app.db.models import JournalRow
from app.db.session import async_session

router = APIRouter(prefix="/journal", tags=["journal"])


class JournalCreate(BaseModel):
    symbol: str
    setup_type: str = ""
    side: str = ""
    catalyst: str = ""
    long_score: float | None = None
    short_score: float | None = None
    squeeze_risk: float | None = None
    planned_entry: float | None = None
    planned_stop: float | None = None
    planned_targets: str = ""
    actual_entry: float | None = None
    actual_exit: float | None = None
    pnl_dollars: float | None = None
    pnl_percent: float | None = None
    mistake_tag: str = ""
    lesson: str = ""
    notes: str = ""


class JournalOut(JournalCreate):
    id: int
    created_at: datetime


@router.get("", response_model=list[JournalOut])
async def list_journal(limit: int = 50):
    async with async_session() as session:
        result = await session.execute(
            select(JournalRow).order_by(JournalRow.created_at.desc()).limit(limit)
        )
        rows = result.scalars().all()
    return [
        JournalOut(
            id=r.id,
            symbol=r.symbol,
            setup_type=r.setup_type,
            side=r.side,
            catalyst=r.catalyst,
            long_score=r.long_score,
            short_score=r.short_score,
            squeeze_risk=r.squeeze_risk,
            planned_entry=r.planned_entry,
            planned_stop=r.planned_stop,
            planned_targets=r.planned_targets,
            actual_entry=r.actual_entry,
            actual_exit=r.actual_exit,
            pnl_dollars=r.pnl_dollars,
            pnl_percent=r.pnl_percent,
            mistake_tag=r.mistake_tag,
            lesson=r.lesson,
            notes=r.notes,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.post("", response_model=JournalOut)
async def create_entry(body: JournalCreate):
    row = JournalRow(**body.model_dump())
    async with async_session() as session:
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return JournalOut(id=row.id, created_at=row.created_at, **body.model_dump())
