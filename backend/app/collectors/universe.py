"""Ticker universe for scans — movers first, then expanded US list."""

from typing import Any

from app.collectors import fmp
from app.collectors.base import has_alpaca, has_finnhub, has_fmp

# Fallback when APIs unavailable (~200 liquid names)
DEFAULT_UNIVERSE = [
    "AAPL", "MSFT", "NVDA", "AMD", "TSLA", "META", "AMZN", "GOOGL", "GOOG", "BRK.B",
    "JPM", "V", "UNH", "XOM", "LLY", "MA", "HD", "PG", "JNJ", "AVGO",
    "SOXL", "SOXS", "TQQQ", "SQQQ", "SPY", "QQQ", "IWM", "SOXX", "DIA", "ARKK",
    "SMCI", "ARM", "MU", "INTC", "COIN", "MARA", "RIOT", "MSTR", "HOOD", "PLTR",
    "SNOW", "CRWD", "NET", "DKNG", "ROKU", "SHOP", "SQ", "PYPL", "UBER", "ABNB",
    "GME", "AMC", "RIVN", "LCID", "NIO", "XPEV", "LI", "BABA", "PDD", "JD",
    "XBI", "LABU", "LABD", "MRNA", "PFE", "BNTX", "CVNA", "UPST", "AFRM", "SOFI",
    "WOLF", "RXT", "WIX", "MRAM", "PIII", "IONQ", "RGTI", "QBTS", "SOUN", "BBAI",
    "CLSK", "HUT", "BITF", "CIFR", "WULF", "CORZ", "IREN", "SMR", "OKLO", "CEG",
    "VST", "NRG", "FSLR", "ENPH", "SEDG", "RUN", "PLUG", "FCEL", "BE", "CHPT",
    "BA", "LMT", "RTX", "NOC", "GD", "GE", "CAT", "DE", "F", "GM",
    "BAC", "WFC", "C", "GS", "MS", "SCHW", "AXP", "BLK", "CME", "ICE",
    "NFLX", "DIS", "CMCSA", "T", "VZ", "TMUS", "CHTR", "WBD", "PARA", "SPOT",
    "COST", "WMT", "TGT", "LOW", "SBUX", "MCD", "YUM", "CMG", "DPZ", "NKE",
    "LULU", "ON", "ANF", "AEO", "GAP", "ROST", "TJX", "BBY", "ULTA", "RH",
    "CRM", "ORCL", "ADBE", "NOW", "PANW", "ZS", "FTNT", "DDOG", "MDB", "TEAM",
    "U", "RBLX", "TTWO", "EA", "ATVI", "MTCH", "PINS", "SNAP", "RDDT", "BMBL",
    "TSM", "ASML", "LRCX", "KLAC", "AMAT", "QCOM", "TXN", "ADI", "MRVL", "ONON",
    "EWY", "FXI", "KWEB", "YINN", "YANG", "EEM", "VWO", "GLD", "SLV", "USO",
    "UVXY", "VXX", "SVXY", "TLT", "HYG", "JNK", "XLF", "XLE", "XLK", "XLV",
    "XLP", "XLY", "XLI", "XLB", "XLU", "XLRE", "XLC", "IGV", "HACK", "CIBR",
    "BITO", "ETHA", "ETHE", "GBTC", "IBIT", "FBTC", "ARKB", "BITX", "ETHU", "CONL",
]


async def load_symbols(limit: int = 200) -> list[str]:
    if has_fmp():
        rows = await fmp.fetch_stock_list(limit=limit * 3)
        symbols = [r["symbol"] for r in rows if r.get("symbol")][:limit]
        if symbols:
            return symbols
    if has_finnhub():
        from app.collectors import finnhub

        syms = await finnhub.fetch_us_symbols(limit)
        if syms:
            return syms
    return DEFAULT_UNIVERSE[:limit]


async def load_mover_symbols(limit: int = 50) -> list[str]:
    from app.collectors import alpaca

    if has_alpaca():
        alpaca_syms = await alpaca.fetch_movers(min(limit, 100))
        if alpaca_syms:
            return alpaca_syms
    return DEFAULT_UNIVERSE[:limit]


async def load_scan_universe(limit: int) -> list[str]:
    """Movers first, then pad to `limit` with full US / default universe."""
    limit = max(1, limit)
    out: list[str] = []

    movers = await load_mover_symbols(min(limit, 100))
    out.extend(movers)

    if len(out) < limit:
        if has_fmp():
            extra = await fmp.fetch_stock_list(limit=limit * 2)
            for row in extra:
                sym = row.get("symbol")
                if sym and sym not in out:
                    out.append(sym)
                if len(out) >= limit:
                    break
        elif has_finnhub():
            from app.collectors import finnhub

            extra = await finnhub.fetch_us_symbols(limit)
            for sym in extra:
                if sym not in out:
                    out.append(sym)
                if len(out) >= limit:
                    break
        else:
            for sym in DEFAULT_UNIVERSE:
                if sym not in out:
                    out.append(sym)
                if len(out) >= limit:
                    break

    return out[:limit]
