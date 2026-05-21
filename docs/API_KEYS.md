# API Keys Guide

## Required for live prices and scans

| Key | Provider | Sign up | Used for |
|-----|----------|---------|----------|
| `POLYGON_API_KEY` | [Polygon.io](https://polygon.io/) | Free tier available | Gainers/losers, snapshots, VWAP, minute bars |
| **OR** `ALPACA_API_KEY` + `ALPACA_API_SECRET` | [Alpaca](https://alpaca.markets/) | Paper trading free | Snapshots, movers |
| **OR** `FMP_API_KEY` | [Financial Modeling Prep](https://site.financialmodelingprep.com/) | Free tier | Quotes, profiles, analyst targets |

**Minimum:** one market data provider. **Best:** Polygon + FMP together.

## Optional but recommended

| Key | Provider | Used for |
|-----|----------|----------|
| `FMP_API_KEY` | Financial Modeling Prep | Ticker universe, market cap, float, analyst targets |
| `BENZINGA_API_KEY` | [Benzinga](https://www.benzinga.com/apis) | Real-time headlines and catalyst classification |
| `OPENAI_API_KEY` | [OpenAI](https://platform.openai.com/) | Structured action trees, deep ticker research |

## Free (no key)

| Service | Config | Used for |
|---------|--------|----------|
| SEC EDGAR | `SEC_USER_AGENT=YourApp your@email.com` | 8-K, offerings, insider Form 4 (major tickers + search) |

## Not implemented (manual / future)

| Source | Notes |
|--------|-------|
| Schwab API | Manual orders in thinkorswim; broker API optional later |
| TradingView | Chart alerts manual; webhook integration possible later |
| Reuters / MarketWatch | Use Benzinga or OpenAI web search via Deep Research |

## After adding keys

1. Edit `.env` in project root.
2. Restart backend: `uvicorn app.main:app --reload --port 8000`
3. Open dashboard → **Run scan** or `POST /api/scanners/run`
4. Check `GET /health` — `ready_for_live_data` should be `true`
