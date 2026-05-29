# Dev Log

Purpose: concise engineering handoff log for multi-device workflow.

## Entry Template

Date:
Branch:
Goal:
Changes:
Files:
Validation:
Next Steps:
Blockers:

---

## 2026-05-25

Branch: `main`
Goal: Improve off-hours pricing accuracy and reduce tab-switch latency.

Changes:
- Added session-aware market pricing and better after-hours fallback logic.
- Added backend quote cache and frontend tab/price caching for faster UX.
- Updated scanner routes to allow cached tab loads and explicit forced refreshes.

Files:
- `backend/app/collectors/session_prices.py`
- `backend/app/collectors/session_util.py`
- `backend/app/collectors/alpaca.py`
- `backend/app/services/scanner.py`
- `backend/app/services/price_cache.py`
- `backend/app/api/routes/scanners.py`
- `frontend/src/components/Dashboard.tsx`
- `frontend/src/components/MoversTable.tsx`
- `frontend/src/lib/priceCache.ts`

Validation:
- Verified AMD after-hours resolves to ~462.98 from AH trades, not unstable quote mid.
- Verified UNH shows separate market and AH values when available.

Next Steps:
- Restart backend/frontend and validate a few symbols from each tab.
- If needed, tighten stale-quote thresholds per feed/session.

Blockers:
- SIP access constraints can return 403 for some recent windows depending on plan.
