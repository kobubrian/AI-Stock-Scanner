"""APScheduler — premarket, open, midday, overnight scans (Pacific Time)."""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import get_settings
from app.services import alerts, scanner

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler(timezone="America/Los_Angeles")


def _parse_hhmm(s: str) -> tuple[int, int]:
    parts = s.strip().split(":")
    return int(parts[0]), int(parts[1]) if len(parts) > 1 else 0


async def _job(scan_type: str) -> None:
    logger.info("Running scheduled scan: %s", scan_type)
    snaps = await scanner.run_scan(scan_type, limit=30)
    await alerts.evaluate_alerts(snaps)


def start_scheduler() -> None:
    settings = get_settings()
    if not settings.scheduler_enabled:
        logger.info("Scheduler disabled (set SCHEDULER_ENABLED=true to enable)")
        return
    jobs = [
        ("premarket", settings.scan_premarket),
        ("open_confirm", settings.scan_open_confirm),
        ("midday", settings.scan_midday),
        ("overnight", settings.scan_overnight),
    ]
    for scan_type, hhmm in jobs:
        h, m = _parse_hhmm(hhmm)
        scheduler.add_job(
            _job,
            CronTrigger(hour=h, minute=m, day_of_week="mon-fri"),
            args=[scan_type],
            id=f"scan_{scan_type}",
            replace_existing=True,
        )
    if not scheduler.running:
        scheduler.start()
        logger.info("Scheduler started with %d jobs", len(jobs))


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
