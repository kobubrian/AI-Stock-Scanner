# Overnight quotes — what you can get

US stocks trade in **several sessions**. Your scanner can use different feeds for each.

| Session (ET) | What it is | Data source in this app |
|--------------|------------|-------------------------|
| **4:00 AM – 9:30 AM** | Pre-market | Alpaca snapshot (`sip` / `iex` if configured) |
| **9:30 AM – 4:00 PM** | Regular hours | Alpaca + Finnhub |
| **4:00 PM – 8:00 PM** | After-hours | Alpaca snapshot (best with `ALPACA_MARKET_DATA_FEED=sip`) |
| **8:00 PM – 4:00 AM** | **Overnight** (Blue Ocean ATS) | Alpaca `feed=overnight` or `feed=boats` |
| **Weekends** | Closed | Last close via Finnhub `/quote` |

## What you have today (no extra Alpaca plan)

Between **8 PM and 4 AM**, most free APIs (Finnhub, Yahoo) show the **last official “current” price** — usually the **4 PM close or late after-hours**, not live overnight-session trades.

That is why prices **do not tick** overnight on IEX-only / Finnhub-only setups.

## True overnight quotes (8 PM – 4 AM, live-ish)

You need **Alpaca market data** with an **overnight / 24/5** subscription:

- **`overnight`** — indicative Blue Ocean quotes (common on Basic / lower tiers)
- **`boats`** — full BOATS tape (Algo Trader Plus; best for trading)

Docs: [Alpaca 24/5 Trading](https://docs.alpaca.markets/docs/245-trading)

### Configure `.env`

```env
# Leave blank to auto-use overnight feed during 8pm-4am ET:
ALPACA_MARKET_DATA_FEED=

ALPACA_USE_OVERNIGHT_SESSION_FEED=true
ALPACA_OVERNIGHT_FEED=overnight

# If you have Algo Trader Plus:
# ALPACA_OVERNIGHT_FEED=boats

# Better after-hours + RTH (if your plan includes SIP):
# ALPACA_MARKET_DATA_FEED=sip
```

Restart the backend after changing `.env`.

### Verify in the dashboard

1. Run a scan during **8 PM – 4 AM ET**.
2. Check the **As of** column:
   - `Closed (overnight)` + **finnhub_quote** → last close only (no overnight plan).
   - **latest_trade** / **quote_mid** with a **recent time** → Alpaca overnight feed is working.

## Finnhub

Finnhub **does not** provide a separate Blue Ocean overnight tape. It is still useful as a **fallback** when Alpaca data is stale or invalid.

## Not available on free stacks

- **NYSE/Nasdaq “live” tape** 8 PM – 4 AM without Alpaca overnight/BOATS
- **OTC** overnight on Alpaca overnight session
- **Options** overnight

## Optional: force one feed always

```env
ALPACA_MARKET_DATA_FEED=overnight
ALPACA_USE_OVERNIGHT_SESSION_FEED=false
```

Use only if you exclusively scan during the overnight window.
