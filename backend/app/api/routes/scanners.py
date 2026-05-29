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
    live_prices: bool = Query(
        False,
        description="Refresh quotes (slow). Default off — use cached scan + price cache for fast tab switches.",
    ),
    force_prices: bool = Query(False, description="Bypass price cache when live_prices=true"),
):
    """Filter last scan; optionally refresh live prices (quotes only, not a full scan)."""
    snapshots = await scanner.get_latest_scan()
    if not snapshots:
        return []
    if live_prices:
        return await scanner.refresh_prices(
            kind=kind, display_limit=limit, force=force_prices
        )
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
    force: bool = Query(True, description="Bypass quote cache"),
):
    """Re-fetch live quotes for tickers on this tab — no full rescan."""
    return await scanner.refresh_prices(kind=kind, display_limit=limit, force=force)


@router.get("/limits")
async def scan_limits():
    s = get_settings()
    return {
        "scan_max_symbols": s.scan_max_symbols,
        "scan_news_max_symbols": s.scan_news_max_symbols,
        "scan_min_daily_volume": s.scan_min_daily_volume,
        "scan_min_market_cap": s.scan_min_market_cap,
        "note": (
            f"Scans above {s.scan_news_max_symbols} symbols skip per-ticker news "
            "(prices/scores only) to avoid Finnhub rate limits. "
            f"Max {s.scan_max_symbols} symbols; large scans take several minutes. "
            f"Filters: volume >= {s.scan_min_daily_volume:,} shares, "
            f"market cap >= ${s.scan_min_market_cap:,.0f}."
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
