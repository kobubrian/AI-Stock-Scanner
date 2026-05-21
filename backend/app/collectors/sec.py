"""SEC EDGAR — free, no API key (User-Agent required)."""

from datetime import datetime, timezone
from typing import Any

from app.collectors.base import http_client
from app.config import get_settings

SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik}.json"
SEARCH = "https://efts.sec.gov/LATEST/search-index"


def _headers() -> dict[str, str]:
    ua = get_settings().sec_user_agent or "TradingResearchScanner contact@example.com"
    return {"User-Agent": ua, "Accept": "application/json"}


# Common tickers -> CIK (expand via ticker lookup in production)
_TICKER_CIK: dict[str, str] = {
    "AAPL": "0000320193",
    "MSFT": "0000789019",
    "NVDA": "0001045810",
    "TSLA": "0001318605",
    "AMD": "0000002488",
    "AMZN": "0001018724",
    "META": "0001326801",
    "GOOGL": "0001652044",
}


def _classify_form(form: str, description: str = "") -> str:
    form = (form or "").upper()
    text = (description or "").lower()
    if form in ("8-K", "6-K"):
        if any(w in text for w in ("offering", "atm", "shelf", "prospectus")):
            return "offering"
        if "earnings" in text or "results" in text:
            return "earnings"
        return "filing_8k"
    if form in ("S-3", "S-1", "424B5", "424B3"):
        return "offering"
    if form == "4":
        return "insider"
    if form in ("10-Q", "10-K"):
        return "financials"
    return "filing"


async def fetch_recent_filings(symbol: str, limit: int = 10) -> list[dict[str, Any]]:
    cik = _TICKER_CIK.get(symbol.upper())
    if not cik:
        return await _search_filings(symbol, limit)

    async with http_client() as client:
        cik_padded = str(cik).zfill(10)
        r = await client.get(
            f"https://data.sec.gov/submissions/CIK{cik_padded}.json",
            headers=_headers(),
        )
        if r.status_code != 200:
            return await _search_filings(symbol, limit)
        data = r.json()

    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    descs = recent.get("primaryDocDescription", [])
    accession = recent.get("accessionNumber", [])

    out: list[dict[str, Any]] = []
    for i in range(min(limit, len(forms))):
        form = forms[i] if i < len(forms) else ""
        out.append(
            {
                "type": _classify_form(form, descs[i] if i < len(descs) else ""),
                "form": form,
                "summary": (descs[i] if i < len(descs) else form) or form,
                "quality": "medium",
                "source": "sec_edgar",
                "timestamp": _parse_date(dates[i] if i < len(dates) else ""),
                "accession": accession[i] if i < len(accession) else "",
            }
        )
    return out


async def _search_filings(symbol: str, limit: int) -> list[dict[str, Any]]:
    async with http_client() as client:
        r = await client.get(
            f"{SEARCH}",
            headers=_headers(),
            params={"q": symbol.upper(), "dateRange": "custom", "startdt": "2024-01-01"},
        )
        if r.status_code != 200:
            return []
    return []


def _parse_date(s: str) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
