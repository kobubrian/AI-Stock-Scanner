from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Query

from app.config import get_settings
from app.models.ticker import TickerSnapshot
from app.services import alerts, scanner

router = APIRouter(prefix="/scanners", tags=["scanners"])

WatchKind = Literal[
    "live", "long", "short", "squeeze", "overnight_long", "overnight_short"
]


def _max_scan() -> int:
    return get_settings().scan_max_symbols


@router.get("/live", response_model=list[TickerSnapshot])
async def live_movers(
    kind: WatchKind = "live",
    limit: int = Query(100, ge=1, le=500),
):
    """Filter the last completed scan only — never starts a new scan."""
    snapshots = await scanner.get_latest_scan()
    return scanner.filter_watchlist(snapshots, kind, display_limit=limit)


@router.get("/cache", response_model=list[TickerSnapshot])
async def scan_cache():
    """Full last scan (all symbols). Never auto-runs."""
    return await scanner.get_latest_scan()


@router.get("/meta")
async def scan_meta():
    return await scanner.get_latest_scan_meta()


@router.post("/refresh-prices", response_model=list[TickerSnapshot])
async def refresh_prices(
    kind: WatchKind = "live",
    limit: int = Query(100, ge=1, le=500),
):
    """Re-fetch live Alpaca/Finnhub quotes for the last scan — no full rescan."""
    await scanner.refresh_prices()
    snapshots = await scanner.get_latest_scan()
    return scanner.filter_watchlist(snapshots, kind, display_limit=limit)


@router.get("/limits")
async def scan_limits():
    s = get_settings()
    return {
        "scan_max_symbols": s.scan_max_symbols,
        "scan_news_max_symbols": s.scan_news_max_symbols,
        "note": (
            f"Scans above {s.scan_news_max_symbols} symbols skip per-ticker news "
            "(prices/scores only) to avoid Finnhub rate limits. "
            f"Max {s.scan_max_symbols} symbols; large scans take several minutes."
        ),
    }


@router.post("/run")
async def trigger_scan(
    background_tasks: BackgroundTasks,
    scan_type: str = "manual",
    limit: int = Query(50, ge=1),
):
    cap = _max_scan()
    if limit > cap:
        return {"status": "error", "message": f"limit exceeds max {cap}"}
    background_tasks.add_task(_run_and_alert, scan_type, limit)
    return {
        "status": "started",
        "scan_type": scan_type,
        "limit": limit,
        "max_symbols": cap,
    }


async def _run_and_alert(scan_type: str, limit: int) -> None:
    snaps = await scanner.run_scan(scan_type, limit=limit)
    await alerts.evaluate_alerts(snaps)
