# Trading Research + Scanner System — Implementation Plan

Based on the project specification. **Principle:** API-first, research automation first, human-confirmed trades, risk before prediction.

---

## Architecture Overview

```
Market/News/SEC/Social APIs
    → Data Collector (normalized ticker objects)
    → Feature Engine
    → Scoring Engine (rule-based first)
    → Candidate Ranking
    → OpenAI validation (top 10–50 only)
    → Dashboard + Alerts
    → Manual execution (Schwab/TOS)
    → Trade Journal + feedback loop
```

**Build order:** Scanner → Rule scoring → AI layer → Dashboard/alerts → Journal/backtest → ML (later) → Broker automation (optional, last).

---

## Phase 0 — Environment & Project Skeleton (Week 1)

| Step | Deliverable | Status |
|------|-------------|--------|
| 0.1 | Python 3.11+ venv, `requirements.txt`, `.env` from `.env.example` | |
| 0.2 | FastAPI backend with `/health`, config loader, structured logging | |
| 0.3 | SQLite (dev) / PostgreSQL (prod) via SQLAlchemy + Alembic migrations | |
| 0.4 | Next.js dashboard shell with tab layout matching spec | |
| 0.5 | Docker Compose (optional): Postgres + Redis | |

**Commands:** See root `README.md` and `scripts/setup.ps1`.

---

## Phase 1 — Data Layer (Weeks 1–2)

### 1.1 Ticker Universe
- Load active US-listed tickers (CSV/API: Polygon, FMP, or static seed file).
- Tag sectors/themes; optional ETF exclusion list.
- Store in `tickers` table with `symbol`, `name`, `sector`, `market_cap`, `float`, `is_etf`.

### 1.2 Market Data Connector
- **Primary:** Polygon.io or Alpaca (quotes, 1m/5m candles, premarket/AH).
- **Fallback:** Financial Modeling Prep, Twelve Data.
- Normalize into ticker object schema (price, bid/ask, spread, OHLC, volume, RVOL, VWAP, HOD/LOD, etc.).
- Timestamp every field; expose staleness in API.

### 1.3 News Connector
- Benzinga, GlobeNewswire, PR Newswire, or aggregated feed.
- Map headlines → tickers; store `source`, `timestamp`, `headline`, `url`.
- Keyword classifier: earnings, offering, FDA, AI/crypto, MOU, etc.

### 1.4 SEC Filings Connector
- SEC EDGAR API: 8-K, S-3, ATM, shelf, 10-Q, Form 4.
- Poll every 1–5 minutes during market hours.

### 1.5 Social/Sentiment (optional MVP+)
- Reddit, Stocktwits, X — rate-limited; hype/squeeze narrative flags only.

**Refresh cadence:** Market data 15–60s; news 30–60s; filings 1–5m.

---

## Phase 2 — Feature Engine (Week 2–3)

Compute derived features per ticker; persist snapshot for scoring history.

| Group | Features |
|-------|----------|
| Price action | Gap %, intraday %, HOD/LOD distance, VWAP distance, premarket gap, failed HOD count, HH/HL, trend slope |
| Volume | RVOL, dollar volume, 5m/10m volume, volume spike ratio, up/down candle volume |
| Catalyst | Earnings, guidance, upgrade/cut, offering, shelf, ATM, MOU, FDA, bankruptcy, AI keywords |
| Valuation | vs analyst target, target freshness, EV/sales, P/E, growth, debt, cash |
| Risk | Low float, squeeze risk, borrow/HTB, spread %, halt risk, overnight gap risk |

**Module:** `backend/app/features/engine.py` — pure functions + batch runner over watchlist.

---

## Phase 3 — Scoring Engine (Week 3)

Transparent rule-based scores (0–100), explainable breakdown JSON per score.

| Score | Purpose |
|-------|---------|
| LongScore | Long continuation quality |
| ShortScore | Fade/short setup quality |
| SqueezeRisk | Danger of blind shorts (high = avoid) |
| CatalystQuality | Real vs hype catalyst |
| OvernightLongScore / OvernightShortScore | Hold overnight/weekend |
| LiquidityScore | Spread + dollar volume |
| ValuationStretchScore | Price vs fair value / stale targets |

**Rules (summary):**
- LongScore ↑: earnings beat, raised guidance, contracts, fresh upgrades, VWAP hold, HH/HL, sector strength.
- LongScore ↓: parabolic move, vague catalyst, stale targets below price, fading volume, wide spread, offering risk.
- ShortScore ↑: huge move on weak news, above targets, weak fundamentals, HOD fail, VWAP loss, LH pattern.
- SqueezeRisk ↑: low float, high SI, high RVOL, AI/crypto headlines, IPO, wide spread, stop-runs.

**Module:** `backend/app/scoring/rules.py` + `scorer.py`.

---

## Phase 4 — Daily Workflow & Triggers (Week 3–4)

| Time (PT) | Job | Purpose |
|-----------|-----|---------|
| 4:00 AM | Premarket full scan | Movers, gaps, catalysts, day-trade + overnight candidates |
| 6:30–7:30 AM | Open confirmation | Filter fake premarket; VWAP/volume hold |
| 10:00–10:30 AM | Mini refresh | Midday updates, squeezes/fades |
| 12:00–12:45 PM | Overnight screen | Rank overnight/weekend longs/shorts |
| After close | Review job | Predictions vs outcomes → journal |

**Re-scan triggers:** QQQ/IWM/SOXX hard reversal, top gainer list change, macro news, sector ETF >1.5–2%, halt wave, final hour, PDT change.

**Implementation:** APScheduler or Celery Beat + `backend/app/jobs/scheduler.py`.

---

## Phase 5 — Dashboard (Week 4–5)

### Tabs
Live Movers | Long Watch | Short Watch | Squeeze Watch | Overnight Candidates | Active Positions | News/Filings | AI Research | Journal

### Live Movers columns
Ticker, price, % change, gap %, volume, RVOL, dollar volume, bid/ask/spread, OHLC, VWAP status, PM high/low, prior close, cap/float/SI, catalyst summary/quality/age, analyst target + fresh/stale, all scores, entry/stop/targets.

### Market regime strip
SPY, QQQ, IWM, SOXX/SOXL, XBI, KWEB/FXI, BTC, VIX, 10Y, oil, DXY.

**Stack:** Next.js + TanStack Table; WebSocket or 15–60s polling from FastAPI.

---

## Phase 6 — OpenAI / Deep Research (Week 5)

- **Do not** use AI as the raw scanner — filter to top 10–50 first.
- Send compact evidence packets; require structured JSON output:
  - `ticker`, `bias`, `timeframe`, scores, `catalyst_quality`, `fair_value_estimate`, `entry_zone`, `stop_loss`, `targets[]`, `action_tree`, `key_risks`, `news_summary`, `valuation_summary`, `confidence`
- Rate limit: top candidates every 15–30 min or on trigger.
- Store prompts/responses for audit.

**Module:** `backend/app/ai/research.py` + prompt templates in `backend/app/ai/prompts/`.

---

## Phase 7 — Alerts (Week 5–6)

Channels: in-app, email (optional), desktop push (optional).

| Alert type | Condition |
|------------|-----------|
| Price | Entry zone, stop, target hit |
| Score | LongScore/ShortScore threshold |
| Technical | VWAP reclaim/loss, HOD break/fail |
| News | Fresh headline on watchlist ticker |
| Risk | SqueezeRisk spike, offering filing |

---

## Phase 8 — Journal & Backtesting (Week 6–7)

Log **every candidate**, not only trades.

| Group | Fields |
|-------|--------|
| Candidate | Date, time, ticker, price, scores, catalyst, news age, VWAP status, RVOL |
| Prediction | Expected 15m, 1h, close, next open/close, target/stop probability |
| Outcome | Actual returns, max favorable/adverse excursion |
| Trade | Entry, size, stop, targets, exit reason, P/L, mistake type, lesson |

**ML (later):** Logistic regression / GBM only after sufficient labeled history.

---

## Phase 9 — Trade Patterns (encoded in scoring + AI prompts)

1. **Failed squeeze short** — up big, weak catalyst, HOD fail, VWAP loss, LH; entry on failed bounce.
2. **Momentum continuation long** — real catalyst, above VWAP, HH/HL, sector confirm, volume on pushes.
3. **Weak-bounce short** — bad earnings, gap down, cannot reclaim VWAP.
4. **IPO blowoff short** — only after failure, not during discovery.

---

## Phase 10 — Risk & Order Discipline (documentation + UI)

- OCO for shorts: buy-to-cover limit + stop (not separate unlinked orders).
- Fragment exits (25% tiers + trail).
- Never trade without stop and targets; size down on low-float/wide spread; no stacked squeeze shorts; cash buffer; PDT as hard constraint.

---

## MVP Milestone Checklist (from spec)

- [ ] **1.** Project skeleton — backend, frontend, DB, config, API connectors
- [ ] **2.** Ticker universe
- [ ] **3.** Market data connector
- [ ] **4.** News connector
- [ ] **5.** Feature engine
- [ ] **6.** Scoring engine
- [ ] **7.** Dashboard table (sortable, filters, color coding, detail pages)
- [ ] **8.** OpenAI integration
- [ ] **9.** Alerts
- [ ] **10.** Journal

---

## Recommended API Keys (`.env`)

| Variable | Provider | Use |
|----------|----------|-----|
| `POLYGON_API_KEY` | Polygon.io | Quotes, candles, market cap |
| `ALPACA_API_KEY` / `SECRET` | Alpaca | Alternative market data |
| `FMP_API_KEY` | Financial Modeling Prep | Fundamentals, universe |
| `BENZINGA_API_KEY` | Benzinga | News (if subscribed) |
| `OPENAI_API_KEY` | OpenAI | Catalyst validation, action trees |
| `DATABASE_URL` | Local Postgres or SQLite | Persistence |

Start with **Polygon + FMP + OpenAI** for MVP; add Benzinga when budget allows.

---

## File / Module Map

```
backend/app/
  main.py              # FastAPI app
  config.py            # Settings from env
  collectors/          # market, news, sec, social
  features/            # feature engine
  scoring/             # rule-based scores
  ai/                  # OpenAI research layer
  jobs/                # scheduled scans
  models/              # SQLAlchemy models
  api/routes/          # REST + WebSocket
  services/            # ranking, alerts, journal

frontend/src/
  app/                 # Next.js pages per dashboard tab
  components/          # tables, regime strip, charts
  lib/api.ts           # backend client
```

---

## Next Actions After Setup

1. Add API keys to `.env`.
2. Run `python -m app.jobs.seed_tickers` (once implemented) to load universe.
3. Implement Polygon collector → verify ticker object in `/api/tickers/{symbol}`.
4. Wire feature engine → scoring → Live Movers API.
5. Build first dashboard tab (Live Movers) with real data.
