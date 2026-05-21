## Finnhub 403 / 429 (free tier)

**Typical causes**

1. **Too many requests** — Each scan calls Finnhub several times **per ticker**. `/stock/candle`, `/company-news`, and (if enabled) `/stock/metric` share a **roughly 60 calls/minute** free allowance. Bursting ~25 symbols × multiple endpoints blows through that → **429** or **403**.

2. **`/stock/metric` on free plans** — Often returns **403** (“premium”). The app **disables metrics by default** (`FINNHUB_FETCH_METRICS=false`). Only enable if your Finnhub plan includes fundamentals.

**What we changed**

- If **Alpaca** returns VWAP + volume for a symbol, Finnhub **candles + metrics are skipped** for that symbol (Alpaca carries intraday VWAP/session volume already).
- Metrics are **opt-in**: `FINNHUB_FETCH_METRICS=false` by default.
- Failures no longer crash the pipeline; problematic endpoints can be skipped for the rest of the process after **403**.
- Optional spacing between Finnhub HTTP calls:

```env
FINNHUB_MIN_REQUEST_INTERVAL_SEC=1.05
```

(~1 request per second ≈ stays under free-tier limits.)

- To stop headline calls entirely (SEC filings still run):

```env
FINNHUB_FETCH_COMPANY_NEWS=false
```

**Short Watch**

Previously required `short_score >= 55` and tight squeeze caps, which often yielded **zero rows**. It now uses a **lower strict threshold**, then **fallback lists** sorted by short score when empty.
