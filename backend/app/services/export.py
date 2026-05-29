"""Export scan data for manual ChatGPT / Deep Research analysis."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.models.ticker import TickerSnapshot
from app.services.scanner import filter_watchlist, get_latest_scan, run_scan

EXPORT_DIR = Path(__file__).resolve().parents[2] / "data" / "exports"

DAILY_PROMPT = """Today is {date}, current time {time} PT.

I want a short-term trading research report. Use ONLY the ticker data below (current prices and news as provided).

Account context:
- Balance: {balance}
- PDT restricted: {pdt}
- Max risk per trade: {max_risk}

For each ticker in top_longs and top_shorts, provide:
- Catalyst quality (real vs hype)
- VWAP / structure bias
- Entry zone, stop, targets (fragment exits)
- Squeeze risk if shorting
- What would invalidate the thesis
- Whether to avoid

End with: best 3 trades to take, best 3 to avoid, cash buffer note.

--- DATA PACK (JSON) ---
{json_data}
"""


def _ticker_packet(snap: TickerSnapshot) -> dict[str, Any]:
    return {
        "ticker": snap.ticker,
        "price": snap.price,
        "percent_change": snap.percent_change,
        "gap_percent": snap.gap_percent,
        "volume": snap.volume,
        "relative_volume": snap.relative_volume,
        "dollar_volume": snap.dollar_volume,
        "bid": snap.bid,
        "ask": snap.ask,
        "spread_percent": snap.spread_percent,
        "vwap": snap.vwap,
        "above_vwap": snap.above_vwap,
        "hod": snap.hod,
        "lod": snap.lod,
        "market_cap": snap.market_cap,
        "float_shares": snap.float_shares,
        "sector": snap.sector,
        "scores": snap.scores.model_dump(),
        "score_breakdown": snap.score_breakdown,
        "trade_plan": snap.trade_plan.model_dump(),
        "catalysts": [c.model_dump(mode="json") for c in snap.catalysts],
        "analyst_targets": snap.analyst_targets,
        "data_source": snap.data_source,
        "updated_at": snap.updated_at.isoformat(),
    }


async def build_ai_export_pack(limit: int = 30, *, force_rescan: bool = False) -> dict[str, Any]:
    settings = get_settings()
    snapshots = await get_latest_scan()
    if force_rescan or not snapshots:
        snapshots = await run_scan("ai_export", limit=limit)

    live = filter_watchlist(snapshots, "live")
    longs = filter_watchlist(snapshots, "long")[:10]
    shorts = filter_watchlist(snapshots, "short")[:10]
    squeezes = filter_watchlist(snapshots, "squeeze")[:10]

    pack: dict[str, Any] = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "mvp_level": 1,
        "data_sources": {
            "market": "alpaca + finnhub",
            "news": "finnhub",
            "filings": "sec_edgar",
            "ai": "manual — feed this file to ChatGPT",
        },
        "account": {
            "balance": settings.account_balance or "not_set",
            "pdt_restricted": settings.account_pdt_restricted,
            "max_risk_per_trade": settings.max_risk_per_trade or "not_set",
        },
        "summary": {
            "scanned_count": len(snapshots),
            "with_live_data": sum(1 for s in snapshots if s.data_available),
        },
        "top_longs": [_ticker_packet(s) for s in longs],
        "top_shorts": [_ticker_packet(s) for s in shorts],
        "squeeze_watch": [_ticker_packet(s) for s in squeezes],
        "all_movers": [_ticker_packet(s) for s in live],
        "avoid_high_squeeze": [
            _ticker_packet(s)
            for s in sorted(snapshots, key=lambda x: x.scores.squeeze_risk, reverse=True)[:5]
            if s.scores.squeeze_risk >= 70
        ],
    }

    json_str = json.dumps(pack, indent=2, default=str)
    pack["chatgpt_prompt"] = DAILY_PROMPT.format(
        date=datetime.now().strftime("%Y-%m-%d"),
        time=datetime.now().strftime("%H:%M"),
        balance=pack["account"]["balance"],
        pdt=pack["account"]["pdt_restricted"],
        max_risk=pack["account"]["max_risk_per_trade"],
        json_data=json_str[:50000],
    )
    return pack


def write_export_files(pack: dict[str, Any]) -> dict[str, str]:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = EXPORT_DIR / f"ai_pack_{ts}.json"
    md_path = EXPORT_DIR / f"ai_pack_{ts}.md"

    json_path.write_text(json.dumps(pack, indent=2, default=str), encoding="utf-8")

    md_lines = [
        "# Trading Research Export",
        f"Generated: {pack.get('exported_at')}",
        "",
        "## Quick stats",
        f"- Scanned: {pack['summary']['scanned_count']}",
        f"- Live data: {pack['summary']['with_live_data']}",
        "",
        "## Top long candidates",
    ]
    for t in pack.get("top_longs", [])[:10]:
        md_lines.append(
            f"- **{t['ticker']}** ${t['price']:.2f} ({t['percent_change']:+.1f}%) "
            f"Long={t['scores']['long_score']:.0f} Squeeze={t['scores']['squeeze_risk']:.0f}"
        )
    md_lines.append("\n## Top short candidates")
    for t in pack.get("top_shorts", [])[:10]:
        md_lines.append(
            f"- **{t['ticker']}** ${t['price']:.2f} ({t['percent_change']:+.1f}%) "
            f"Short={t['scores']['short_score']:.0f} Squeeze={t['scores']['squeeze_risk']:.0f}"
        )
    md_lines.append("\n---\n\n## Paste into ChatGPT\n\n")
    md_lines.append("```\n" + pack.get("chatgpt_prompt", "")[:80000] + "\n```")
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    return {"json": str(json_path), "markdown": str(md_path)}
