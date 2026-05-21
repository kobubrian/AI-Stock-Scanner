# AI Stock Scanner — Trading Research System

Semi-automated short-term trading research: scanners, news, feature engineering, scoring, AI validation, dashboards, alerts, risk controls, and journaling. **Execution stays manual** (Schwab/thinkorswim) until the system is proven.

See [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) for the full phased build plan.

## Quick Start (Windows)

```powershell
# From project root
.\scripts\setup.ps1

# Copy and edit API keys
copy .env.example .env

# Terminal 1 — API (must run before opening the dashboard)
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000

# Terminal 2 — Dashboard (proxies /api and /health to port 8000)
cd frontend
npm run dev
```

- API: http://localhost:8000/docs  
- Dashboard: http://localhost:3000 (or 3001 if 3000 is busy)  

The UI calls **`/health` and `/api/...` on the same host as Next.js**; `next.config.ts` rewrites those to `http://localhost:8000`. You do **not** need `NEXT_PUBLIC_API_URL` for local dev.

### "Failed to fetch" in the browser

1. Start the backend first (port **8000** must match `frontend/next.config.ts` rewrites).  
2. If port 8000 is blocked, run the API on **8001** and add `frontend/.env.local`:

   ```
   NEXT_PUBLIC_API_URL=http://localhost:8001
   ```

   Then restart `npm run dev` (rewrites are ignored when this is set; the browser talks to 8001 directly).

## Project Layout

```
backend/     FastAPI, collectors, features, scoring, jobs, DB
frontend/    Next.js dashboard
docs/        Implementation plan
scripts/     setup.ps1
```

## Principles

- **API-first** — no fragile UI scraping where APIs exist  
- **Research automation first** — rank candidates before any auto-execution  
- **Human-confirmed trades** — OCO stops, manual orders  
- **Risk before prediction** — every candidate needs entry, stop, targets, invalidation, size limits  
