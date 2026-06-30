"""Scanner service — live movers, watchlists."""

import asyncio
from typing import Literal

from sqlalchemy import select

from app.collectors import polygon, universe
from app.collectors.base import has_polygon
from app.config import get_settings
from app.db.models import CandidateRow, ScanRunRow
from app.db.session import async_session
from app.models.ticker import TickerSnapshot
from app.services.pipeline import build_snapshot, build_snapshot_from_raw

ScanKind = Literal["live", "long", "short", "squeeze", "overnight_long", "overnight_short"]

DISPLAY_DEFAULT = 100


def passes_scan_filters(snap: TickerSnapshot) -> bool:
    """Min daily share volume and market cap (from settings)."""
    if not snap.data_available or float(snap.price or 0) <= 0:
        return False

    settings = get_settings()
    vol_min = int(settings.scan_min_daily_volume or 0)
    vol = int(snap.volume or 0)
    if vol_min > 0 and vol > 0 and vol < vol_min:
        return False
    # Volume 0 with a valid price usually means closed market / Finnhub-only quote — keep row.

    cap_min = float(settings.scan_min_market_cap or 0)
    if cap_min > 0:
        mc = snap.market_cap
        # Only exclude when cap is known and below minimum (missing cap = keep row).
        if mc is not None and float(mc) < cap_min:
            return False

    return True


def apply_scan_filters(snapshots: list[TickerSnapshot]) -> list[TickerSnapshot]:
    return [s for s in snapshots if passes_scan_filters(s)]


def dedupe_snapshots(snapshots: list[TickerSnapshot]) -> list[TickerSnapshot]:
    """One row per ticker. Prefer live data, then larger |% change|. Preserves first-seen order."""
    by_ticker: dict[str, TickerSnapshot] = {}
    for s in snapshots:
        k = (s.ticker or "").upper()
        if not k:
            continue
        cur = by_ticker.get(k)
        if cur is None:
            by_ticker[k] = s
            continue
        if (s.data_available and not cur.data_available) or (
            s.data_available == cur.data_available
            and abs(s.percent_change) > abs(cur.percent_change)
        ):
            by_ticker[k] = s

    out: list[TickerSnapshot] = []
    seen: set[str] = set()
    for s in snapshots:
        k = (s.ticker or "").upper()
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(by_ticker[k])
    return out


async def run_scan(scan_type: str = "premarket", limit: int = 30) -> list[TickerSnapshot]:
    settings = get_settings()
    limit = min(max(1, limit), settings.scan_max_symbols)
    include_news = limit <= settings.scan_news_max_symbols

    symbols = await universe.load_scan_universe(limit)
    snapshots = dedupe_snapshots(await _fetch_many(symbols, include_news=include_news))
    snapshots = apply_scan_filters(snapshots)
    snapshots.sort(key=lambda s: abs(s.percent_change), reverse=True)

    async with async_session() as session:
        run = ScanRunRow(scan_type=scan_type, symbol_count=len(snapshots))
        session.add(run)
        await session.flush()
        for snap in snapshots:
            session.add(
                CandidateRow(
                    scan_run_id=run.id,
                    symbol=snap.ticker,
                    snapshot_json=snap.model_dump_json(),
                    long_score=snap.scores.long_score,
                    short_score=snap.scores.short_score,
                    squeeze_risk=snap.scores.squeeze_risk,
                )
            )
        await session.commit()

    if snapshots:
        await refresh_prices(symbols=[s.ticker for s in snapshots])

    return await get_latest_scan() or snapshots


async def _fetch_many(symbols: list[str], *, include_news: bool = True) -> list[TickerSnapshot]:
    if has_polygon():
        gainers = await polygon.fetch_gainers(len(symbols))
        snaps: list[TickerSnapshot] = []
        for t in gainers:
            raw = polygon.parse_snapshot(t)
            if raw.get("price"):
                snaps.append(await build_snapshot_from_raw(raw))
        if snaps:
            return snaps

    concurrency = 8 if len(symbols) <= 100 else 12 if len(symbols) <= 500 else 16
    sem = asyncio.Semaphore(concurrency)

    async def one(sym: str) -> TickerSnapshot | None:
        async with sem:
            try:
                return await build_snapshot(
                    sym, include_news=include_news, fetch_ah_trades=False
                )
            except Exception:
                return None

    results = await asyncio.gather(*[one(s) for s in symbols])
    return [r for r in results if r is not None]


def _top_by(snapshots: list[TickerSnapshot], key_fn, n: int) -> list[TickerSnapshot]:
    return sorted(snapshots, key=key_fn, reverse=True)[:n]


def filter_watchlist(
    snapshots: list[TickerSnapshot],
    kind: ScanKind,
    *,
    display_limit: int = DISPLAY_DEFAULT,
) -> list[TickerSnapshot]:
    snapshots = apply_scan_filters(dedupe_snapshots(snapshots))
    if not snapshots:
        return []

    n = max(1, display_limit)

    if kind == "live":
        return _top_by(snapshots, lambda x: abs(x.percent_change), n)

    if kind == "long":
        strict = [s for s in snapshots if s.scores.long_score >= 50 and s.scores.squeeze_risk < 75]
        return _top_by(strict or snapshots, lambda x: x.scores.long_score, n)

    if kind == "short":
        strict = [s for s in snapshots if s.scores.short_score >= 45 and s.scores.squeeze_risk < 85]
        return _top_by(strict or snapshots, lambda x: x.scores.short_score, n)

    if kind == "squeeze":
        strict = [s for s in snapshots if s.scores.squeeze_risk >= 50]
        return _top_by(strict or snapshots, lambda x: x.scores.squeeze_risk, n)

    if kind == "overnight_long":
        strict = [s for s in snapshots if s.scores.overnight_long_score >= 45]
        return _top_by(strict or snapshots, lambda x: x.scores.overnight_long_score, n)

    if kind == "overnight_short":
        strict = [s for s in snapshots if s.scores.overnight_short_score >= 45]
        return _top_by(strict or snapshots, lambda x: x.scores.overnight_short_score, n)

    return _top_by(snapshots, lambda x: abs(x.percent_change), n)


async def get_latest_scan() -> list[TickerSnapshot]:
    """All tickers from the most recent scan run — never triggers a new scan."""
    async with async_session() as session:
        run_result = await session.execute(
            select(ScanRunRow).order_by(ScanRunRow.created_at.desc()).limit(1)
        )
        run = run_result.scalar_one_or_none()
        if not run:
            return []
        result = await session.execute(
            select(CandidateRow)
            .where(CandidateRow.scan_run_id == run.id)
            .order_by(CandidateRow.id.asc())
        )
        rows = result.scalars().all()

    out: list[TickerSnapshot] = []
    for row in rows:
        try:
            out.append(TickerSnapshot.model_validate_json(row.snapshot_json))
        except Exception:
            continue
    return dedupe_snapshots(out)


async def get_cached_candidates(limit: int = 50) -> list[TickerSnapshot]:
    """Backward compat — returns latest scan (ignores limit for filtering source)."""
    return await get_latest_scan()


async def get_latest_scan_meta() -> dict:
    from app.db.models import ScanRunRow

    async with async_session() as session:
        run_result = await session.execute(
            select(ScanRunRow).order_by(ScanRunRow.created_at.desc()).limit(1)
        )
        run = run_result.scalar_one_or_none()
    if not run:
        return {"symbol_count": 0, "scanned_at": None, "prices_updated_at": None, "newest_price_as_of": None}

    return {
        "symbol_count": run.symbol_count,
        "scanned_at": run.created_at.isoformat() if run.created_at else None,
        "prices_updated_at": None,
        "newest_price_as_of": None,
    }


def _merge_live_quotes(snap: TickerSnapshot, raw: dict) -> TickerSnapshot:
    """Update price fields only — keep scores/catalysts from last full scan."""
    from datetime import datetime, timezone

    data = snap.model_dump()
    price = float(raw.get("price") or snap.price)
    prev = float(raw.get("previous_close") or snap.previous_close)
    pct = float(raw.get("percent_change") or 0)
    if prev and not raw.get("percent_change"):
        pct = round((price - prev) / prev * 100, 2)

    data.update(
        {
            "price": price,
            "previous_close": prev,
            "percent_change": pct,
            "volume": int(raw.get("volume") or snap.volume),
            "bid": raw.get("bid", snap.bid),
            "ask": raw.get("ask", snap.ask),
            "spread_percent": raw.get("spread_percent", snap.spread_percent),
            "vwap": raw.get("vwap", snap.vwap),
            "above_vwap": raw.get("above_vwap", snap.above_vwap),
            "hod": raw.get("hod", snap.hod),
            "lod": raw.get("lod", snap.lod),
            "price_as_of": raw.get("price_as_of", snap.price_as_of),
            "price_source": raw.get("price_source") or snap.price_source,
            "session": raw.get("session") or raw.get("active_session") or snap.session,
            "active_session": raw.get("active_session") or raw.get("session") or snap.active_session,
            "price_session": raw.get("price_session") or snap.price_session,
            "regular_close": raw.get("regular_close", snap.regular_close),
            "afterhours_price": raw.get("afterhours_price", snap.afterhours_price),
            "afterhours_percent_change": raw.get(
                "afterhours_percent_change", snap.afterhours_percent_change
            ),
            "premarket_price": raw.get("premarket_price", snap.premarket_price),
            "overnight_price": raw.get("overnight_price", snap.overnight_price),
            "market_price": raw.get("market_price", snap.market_price),
            "data_source": raw.get("source") or snap.data_source,
            "data_available": bool(price),
            "updated_at": datetime.now(timezone.utc),
        }
    )
    return TickerSnapshot.model_validate(data)


async def refresh_prices(
    symbols: list[str] | None = None,
    *,
    kind: ScanKind | None = None,
    display_limit: int = DISPLAY_DEFAULT,
    force: bool = False,
) -> list[TickerSnapshot]:
    """Re-fetch live quotes per session (SIP + overnight). No news/rescore."""
    from app.collectors.market import fetch_raw_market
    from app.services.price_cache import get, get_many, set as cache_set

    all_snaps = await get_latest_scan()
    if not all_snaps:
        return []

    if symbols is None and kind is not None:
        snapshots = filter_watchlist(all_snaps, kind, display_limit=display_limit)
        symbols = [s.ticker for s in snapshots]
    elif symbols:
        want = {s.upper() for s in symbols}
        snapshots = [s for s in all_snaps if s.ticker.upper() in want]
    else:
        snapshots = all_snaps

    if not snapshots:
        return []

    target = {s.ticker.upper() for s in snapshots}
    tickers = [s.ticker.upper() for s in snapshots]
    cached: dict[str, dict] = {}
    to_fetch = tickers
    if force:
        from app.services.price_cache import clear

        clear()
    else:
        cached, to_fetch = get_many(tickers)

    sem = asyncio.Semaphore(6)

    async def one(snap: TickerSnapshot) -> TickerSnapshot:
        sym = snap.ticker.upper()
        raw = cached.get(sym)
        if raw is None:
            async with sem:
                raw = await fetch_raw_market(
                    snap.ticker, enrich_fundamentals=False, fetch_ah_trades=True
                )
            if raw and raw.get("price"):
                cache_set(sym, raw)
        if not raw or not raw.get("price"):
            return snap
        return _merge_live_quotes(snap, raw)

    updated = await asyncio.gather(*[one(s) for s in snapshots])

    async with async_session() as session:
        run_result = await session.execute(
            select(ScanRunRow).order_by(ScanRunRow.created_at.desc()).limit(1)
        )
        run = run_result.scalar_one_or_none()
        if run:
            result = await session.execute(
                select(CandidateRow).where(CandidateRow.scan_run_id == run.id)
            )
            rows = {r.symbol.upper(): r for r in result.scalars().all()}
            for snap in updated:
                row = rows.get(snap.ticker.upper())
                if row:
                    row.snapshot_json = snap.model_dump_json()
            await session.commit()

    full = await get_latest_scan()
    if kind is not None:
        return filter_watchlist(full, kind, display_limit=display_limit)
    by_ticker = {s.ticker.upper(): s for s in updated}
    return [by_ticker.get(s.ticker.upper(), s) for s in full if s.ticker.upper() in target] or list(updated)

