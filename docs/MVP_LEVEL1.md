# MVP Level 1 — Research Assistant + Watchlist Scorer

## Stack (configured)

| Need | Source | Status |
|------|--------|--------|
| Quotes + candles | **Alpaca** + **Finnhub** | Live |
| News / catalysts | **Finnhub** company news | Live |
| Filings | **SEC EDGAR** (User-Agent) | Live for mapped tickers |
| AI analysis | **Manual** — export file | `POST /api/export/ai-pack` |
| Charts | TradingView / thinkorswim | Manual (your workflow) |

## Daily workflow

1. Start backend + dashboard
2. Click **Run scan** (or wait for scheduled scan)
3. Review **Live Movers** / Long / Short / Squeeze tabs
4. Click **Export for ChatGPT** — files saved to `backend/data/exports/`
5. Open the `.md` or `.json` file → paste into ChatGPT with your daily prompt
6. Trade manually in Schwab/TOS with OCO stops

## Export API

```http
POST /api/export/ai-pack?limit=30
GET  /api/export/ai-pack?limit=30          # preview in browser
GET  /api/export/ai-pack/latest/json     # download last JSON
```

Export includes: top longs, top shorts, squeeze watch, full mover list, scores, catalysts, trade plans, and a pre-built `chatgpt_prompt` field.

## Environment

See `.env` — only `ALPACA_*`, `FINNHUB_API_KEY`, and `SEC_USER_AGENT` required for MVP.

**Security:** Never commit `.env`. Rotate keys if exposed in chat or screenshots.
