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

    return snapshots


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
                return await build_snapshot(sym, include_news=include_news)
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
    snapshots = dedupe_snapshots(snapshots)
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

    snapshots = await get_latest_scan()
    prices_updated = None
    newest_price_as_of = None
    if snapshots:
        updated_times = [s.updated_at for s in snapshots if s.updated_at]
        if updated_times:
            prices_updated = max(updated_times).isoformat()
        price_times = [s.price_as_of for s in snapshots if s.price_as_of]
        if price_times:
            newest_price_as_of = max(price_times).isoformat()

    return {
        "symbol_count": run.symbol_count,
        "scanned_at": run.created_at.isoformat() if run.created_at else None,
        "prices_updated_at": prices_updated,
        "newest_price_as_of": newest_price_as_of,
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
            "session": raw.get("session") or snap.session,
            "data_source": raw.get("source") or snap.data_source,
            "data_available": bool(price),
            "updated_at": datetime.now(timezone.utc),
        }
    )
    return TickerSnapshot.model_validate(data)


async def refresh_prices(symbols: list[str] | None = None) -> list[TickerSnapshot]:
    """Re-fetch live quotes for latest scan symbols (fast — no news/rescore)."""
    from app.collectors import alpaca
    from app.collectors.base import has_alpaca
    from app.collectors.market import fetch_raw_market

    snapshots = await get_latest_scan()
    if not snapshots:
        return []

    target = {s.ticker.upper() for s in snapshots}
    if symbols:
        want = {s.upper() for s in symbols}
        snapshots = [s for s in snapshots if s.ticker.upper() in want]
        target = want & target

    tickers = [s.ticker.upper() for s in snapshots]
    raw_by_symbol: dict[str, dict] = {}
    if has_alpaca():
        raw_by_symbol = await alpaca.fetch_snapshots_batch(tickers)

    sem = asyncio.Semaphore(8)

    async def one(snap: TickerSnapshot) -> TickerSnapshot:
        sym = snap.ticker.upper()
        raw = raw_by_symbol.get(sym)
        if not raw or not raw.get("price"):
            async with sem:
                raw = await fetch_raw_market(sym)
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
    by_ticker = {s.ticker.upper(): s for s in updated}
    return [by_ticker.get(s.ticker.upper(), s) for s in full if s.ticker.upper() in target] or list(updated)

