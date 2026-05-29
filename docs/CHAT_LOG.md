# Chat Log

Purpose: keep a lightweight index of important agent chats and outcomes so context is easy to recover on any device.

## Entry Template

Date:
Title:
Link:
Scope:
Decisions:
Open Items:

---

## 2026-05-25

Title: After-hours pricing fixes
Link: [After-hours pricing fixes](2cd10637-151a-40d3-a685-f20ad22ec4e8)
Scope:
- Added multi-session price handling and improved extended-hours display behavior.
- Investigated AMD/UNH after-hours mismatches and validated feed behavior.

Decisions:
- Prefer freshest valid after-hours trade data over unstable quote mids for off-hours display.
- Keep additional session prices visible in UI (close/AH/PM/ON/market) when relevant.

Open Items:
- Continue validating symbols during weekends/holidays after backend restart.
