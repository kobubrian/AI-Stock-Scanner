import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    alerts_route,
    export,
    health,
    journal,
    regime,
    research,
    scanners,
    tickers,
)
from app.config import get_settings
from app.db.session import init_db
from app.jobs.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    data_dir = Path(__file__).resolve().parents[1] / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    await init_db()
    start_scheduler()
    yield
    stop_scheduler()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Trading Research Scanner API",
        description="Scanners, scoring, AI validation, alerts, and journal",
        version="0.3.0-mvp",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(tickers.router, prefix="/api")
    app.include_router(scanners.router, prefix="/api")
    app.include_router(journal.router, prefix="/api")
    app.include_router(research.router, prefix="/api")
    app.include_router(alerts_route.router, prefix="/api")
    app.include_router(regime.router, prefix="/api")
    app.include_router(export.router, prefix="/api")
    return app


app = create_app()
