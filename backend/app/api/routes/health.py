from fastapi import APIRouter

from app.collectors.base import (
    has_alpaca,
    has_benzinga,
    has_finnhub,
    has_fmp,
    has_openai,
    has_polygon,
)
from app.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    settings = get_settings()
    return {
        "status": "ok",
        "env": settings.app_env,
        "mvp": "level_1_research_assistant",
        "services": {
            "alpaca": has_alpaca(),
            "finnhub": has_finnhub(),
            "sec_edgar": True,
            "polygon": has_polygon(),
            "fmp": has_fmp(),
            "benzinga": has_benzinga(),
            "openai": has_openai(),
        },
        "ready_for_live_data": has_alpaca() or has_finnhub(),
        "ready_for_news": has_finnhub() or has_benzinga(),
        "ai_mode": "manual_export" if not has_openai() else "api_or_export",
    }
