"""Fetch prices per market session (RTH, after-hours, premarket, overnight)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.collectors import alpaca
from app.collectors.alpaca import _parse_alpaca_time
from app.collectors.base import has_alpaca, has_finnhub
from app.collectors.session_util import current_session_label, trade_session_key
from app.config import get_settings

def _pct(price: float, prev: float) -> float:
    if prev and price:
        return round((price - prev) / prev * 100, 2)
    return 0.0


def _quote_entry(
    price: float,
    *,
    price_as_of: datetime | None,
    price_source: str,
    prev_close: float,
) -> dict[str, Any]:
    return {
        "price": price,
        "price_as_of": price_as_of,
        "price_source": price_source,
        "percent_change": _pct(price, prev_close),
    }


def _classify_sip_snapshot(data: dict[str, Any], prev_close: float) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    daily = data.get("dailyBar") or {}
    rth_close = float(daily.get("c") or 0)
    if rth_close > 0:
        out["regular"] = _quote_entry(
            rth_close,
            price_as_of=_parse_alpaca_time(daily.get("t")),
            price_source="daily_close",
            prev_close=prev_close,
        )

    by_sess: dict[str, tuple[float, datetime | None, str]] = {}
    far = datetime(1970, 1, 1, tzinfo=timezone.utc)

    for field, src_name in (
        ("latestTrade", "latest_trade"),
        ("minuteBar", "minute_bar"),
    ):
        block = data.get(field) or {}
        price_key = "p" if field == "latestTrade" else "c"
        if block.get(price_key) is None:
            continue
        try:
            price = float(block[price_key])
            ts = _parse_alpaca_time(block.get("t"))
            key = trade_session_key(ts)
            if not key:
                continue
            cur = by_sess.get(key)
            if cur is None or (ts or far) > (cur[1] or far):
                by_sess[key] = (price, ts, src_name)
        except (TypeError, ValueError):
            continue

    lq = data.get("latestQuote") or {}
    try:
        bp, ap = float(lq.get("bp") or 0), float(lq.get("ap") or 0)
        if bp > 0 and ap > 0 and ap >= bp * 0.5:
            mid = (bp + ap) / 2
            spread_pct = (ap - bp) / mid if mid else 1.0
            # Reject broken/wide NBBO (e.g. half-spread > 5% → bogus ~470 mid on AMD).
            if mid <= bp * 5 and spread_pct <= 0.05:
                ts = _parse_alpaca_time(lq.get("t"))
                key = trade_session_key(ts)
                if key:
                    cur = by_sess.get(key)
                    if cur is None or (ts or far) > (cur[1] or far):
                        by_sess[key] = (mid, ts, "quote_mid")
    except (TypeError, ValueError):
        pass

    base_prev = prev_close or rth_close
    for key, (price, ts, src) in by_sess.items():
        out[key] = _quote_entry(
            price,
            price_as_of=ts,
            price_source=src,
            prev_close=base_prev,
        )
    return out


def _quote_timestamp(q: dict[str, Any]) -> datetime:
    ts = q.get("price_as_of")
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            return ts.replace(tzinfo=timezone.utc)
        return ts
    return datetime.min.replace(tzinfo=timezone.utc)


def _merge_session_quote(
    session_quotes: dict[str, dict[str, Any]],
    key: str,
    entry: dict[str, Any],
) -> None:
    """Keep the quote with the newest timestamp for a session bucket."""
    cur = session_quotes.get(key)
    if not cur or _quote_timestamp(entry) >= _quote_timestamp(cur):
        session_quotes[key] = entry


def _pick_primary(
    session_quotes: dict[str, dict[str, Any]],
    active: str,
) -> tuple[str, dict[str, Any]]:
    """Headline price: freshest extended quote off-hours; RTH during regular session."""
    if active in ("overnight_closed", "weekend", "afterhours", "premarket"):
        best_key = ""
        best_q: dict[str, Any] = {}
        best_ts = datetime.min.replace(tzinfo=timezone.utc)
        for key in ("afterhours", "overnight", "premarket", "market", "regular"):
            q = session_quotes.get(key)
            if not q or not q.get("price"):
                continue
            if q.get("price_source") == "quote_mid":
                continue
            ts = _quote_timestamp(q)
            if ts > best_ts:
                best_ts = ts
                best_key = key
                best_q = q
        if best_q:
            return best_key, best_q

    if active == "overnight_closed":
        order = ["overnight", "afterhours", "premarket", "regular", "market"]
    elif active == "afterhours":
        order = ["afterhours", "market", "regular"]
    elif active == "premarket":
        order = ["premarket", "market", "regular"]
    else:
        order = ["regular", "afterhours", "premarket", "overnight", "market"]

    for key in order:
        q = session_quotes.get(key)
        if q and q.get("price"):
            return key, q
    return "", {}


def _display_session(active: str) -> str:
    if active == "overnight_closed":
        return "overnight"
    return active


async def fetch_multi_session_market(
    symbol: str, *, fetch_ah_trades: bool = True
) -> dict[str, Any]:
    """Primary price for current session + per-session quotes for extended display."""
    symbol = symbol.upper()
    active = current_session_label()
    session_quotes: dict[str, dict[str, Any]] = {}
    prev_close = 0.0
    volume = 0
    vwap = bid = ask = spread = hod = lod = None
    source = "none"

    if has_alpaca():
        sip_data = await alpaca.fetch_snapshot_data(symbol, feed="sip")
        if not sip_data:
            sip_data = await alpaca.fetch_snapshot_data(symbol, feed="iex")
        if sip_data:
            source = "alpaca"
            built = alpaca.build_snapshot_from_data(symbol, sip_data)
            prev_close = float(built.get("previous_close") or 0)
            volume = int(built.get("volume") or 0)
            if volume <= 0:
                prev_bar = sip_data.get("prevDailyBar") or {}
                volume = int(prev_bar.get("v") or 0)
            vwap = built.get("vwap")
            bid, ask = built.get("bid"), built.get("ask")
            spread = built.get("spread_percent")
            hod, lod = built.get("hod"), built.get("lod")
            session_quotes.update(_classify_sip_snapshot(sip_data, prev_close))

        if fetch_ah_trades:
            ah = await alpaca.fetch_afterhours_from_trades(symbol)
        else:
            ah = None
        if ah and ah.get("price"):
            base = prev_close or float(
                (session_quotes.get("regular") or {}).get("price") or 0
            )
            _merge_session_quote(
                session_quotes,
                "afterhours",
                _quote_entry(
                    float(ah["price"]),
                    price_as_of=ah.get("price_as_of"),
                    price_source=str(ah.get("price_source") or "ah_trades"),
                    prev_close=base,
                ),
            )

        if active in ("overnight_closed", "weekend"):
            settings = get_settings()
            for feed in (settings.alpaca_overnight_feed or "overnight", "boats"):
                on_data = await alpaca.fetch_snapshot_data(symbol, feed=feed)
                if not on_data:
                    continue
                built = alpaca.build_snapshot_from_data(symbol, on_data)
                if built.get("price"):
                    base = prev_close or float(
                        (session_quotes.get("regular") or {}).get("price") or 0
                    )
                    session_quotes["overnight"] = _quote_entry(
                        float(built["price"]),
                        price_as_of=built.get("price_as_of"),
                        price_source=str(built.get("price_source") or feed),
                        prev_close=base,
                    )
                    break

    market_price = None
    if has_finnhub():
        from app.collectors import finnhub

        fq_head = await finnhub.fetch_quote(symbol)
        if fq_head and fq_head.get("price"):
            market_price = float(fq_head["price"])
            session_quotes["market"] = _quote_entry(
                market_price,
                price_as_of=fq_head.get("price_as_of"),
                price_source="finnhub_quote",
                prev_close=float(fq_head.get("previous_close") or prev_close),
            )

    price_key, primary = _pick_primary(session_quotes, active)
    if not primary and has_finnhub():
        from app.collectors import finnhub

        fq = await finnhub.fetch_quote(symbol)
        if fq and fq.get("price"):
            source = "finnhub"
            prev_close = float(fq.get("previous_close") or prev_close)
            primary = _quote_entry(
                float(fq["price"]),
                price_as_of=fq.get("price_as_of"),
                price_source="finnhub_quote",
                prev_close=prev_close,
            )
            price_key = "regular"

    if not primary:
        return {
            "ticker": symbol,
            "price": 0.0,
            "previous_close": prev_close,
            "percent_change": 0.0,
            "volume": 0,
            "source": "none",
            "data_available": False,
            "active_session": _display_session(active),
            "session_quotes": {},
        }

    display_sess = _display_session(active)
    if active == "weekend" and price_key in ("afterhours", "overnight", "premarket"):
        display_sess = _display_session(price_key)

    return {
        "ticker": symbol,
        "price": float(primary["price"]),
        "previous_close": prev_close,
        "percent_change": float(primary.get("percent_change") or 0),
        "volume": volume,
        "bid": bid,
        "ask": ask,
        "spread_percent": spread,
        "vwap": vwap,
        "above_vwap": (float(primary["price"]) >= vwap) if vwap else None,
        "hod": hod,
        "lod": lod,
        "price_as_of": primary.get("price_as_of"),
        "price_source": primary.get("price_source", ""),
        "session": display_sess,
        "active_session": display_sess,
        "price_session": price_key,
        "source": source,
        "data_available": True,
        "session_quotes": session_quotes,
        "regular_close": (session_quotes.get("regular") or {}).get("price"),
        "afterhours_price": (session_quotes.get("afterhours") or {}).get("price"),
        "afterhours_percent_change": (session_quotes.get("afterhours") or {}).get(
            "percent_change"
        ),
        "premarket_price": (session_quotes.get("premarket") or {}).get("price"),
        "overnight_price": (session_quotes.get("overnight") or {}).get("price"),
        "market_price": market_price,
    }
