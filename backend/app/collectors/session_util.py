"""US market session from wall clock."""

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

_NY = ZoneInfo("America/New_York")


def current_session_label() -> str:
    local = datetime.now(_NY)
    if local.weekday() >= 5:
        return "weekend"
    mins = local.hour * 60 + local.minute
    if 240 <= mins < 570:
        return "premarket"
    if 570 <= mins < 960:
        return "regular"
    if 960 <= mins < 1200:
        return "afterhours"
    return "overnight_closed"


def session_label_from_timestamp(ts: datetime | None) -> str:
    if ts is None:
        return "unknown"
    local = ts.astimezone(_NY)
    if local.weekday() >= 5:
        return "weekend"
    mins = local.hour * 60 + local.minute
    if 240 <= mins < 570:
        return "premarket"
    if 570 <= mins < 960:
        return "regular"
    if 960 <= mins < 1200:
        return "afterhours"
    return "overnight_closed"


def trade_session_key(ts: datetime | None) -> str | None:
    """Map a trade timestamp to regular / afterhours / premarket (SIP/IEX tape)."""
    if ts is None:
        return None
    sess = session_label_from_timestamp(ts)
    if sess in ("regular", "afterhours", "premarket"):
        return sess
    if sess == "overnight_closed":
        local = ts.astimezone(_NY)
        mins = local.hour * 60 + local.minute
        if 960 <= mins < 1200:
            return "afterhours"
    return None


def afterhours_utc_windows(*, lookback_days: int = 10) -> list[tuple[datetime, datetime]]:
    """4:00–8:00 PM ET after-hours windows for recent weekdays (newest first)."""
    now_local = datetime.now(_NY)
    windows: list[tuple[datetime, datetime]] = []
    for d in range(lookback_days):
        day = (now_local - timedelta(days=d)).date()
        if day.weekday() >= 5:
            continue
        start_local = datetime.combine(day, time(16, 0), tzinfo=_NY)
        end_local = datetime.combine(day, time(20, 0), tzinfo=_NY)
        windows.append(
            (
                start_local.astimezone(timezone.utc),
                end_local.astimezone(timezone.utc),
            )
        )
    return windows
