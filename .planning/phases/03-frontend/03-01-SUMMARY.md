---
phase: 03-frontend
plan: 01
subsystem: seeds-data-layer
tags: [backend, frontend, rename, types, hooks]
dependency_graph:
  requires: [02-04]
  provides: [seed-types, seed-hooks, label-field]
  affects: [frontend/src/api/types.ts, frontend/src/api/hooks.ts, backend/models.py, backend/routers/seeds.py, backend/services/seed_service.py]
tech_stack:
  added: []
  patterns: [TanStack Query useQuery/useMutation, Pydantic schema field rename, SQLAlchemy column rename]
key_files:
  created: []
  modified:
    - backend/models.py
    - backend/routers/seeds.py
    - backend/services/seed_service.py
    - tests/test_seed_service.py
    - frontend/src/api/types.ts
    - frontend/src/api/hooks.ts
decisions:
  - SavedSeed uses `label` field (not `name`) to match tag-based UI pattern per D-20
  - SeedEntry.name preserved as character display name (not renamed — different field)
metrics:
  duration: ~8min
  completed: "2026-03-28"
  tasks: 2
  files: 6
---

# Phase 03 Plan 01: Seed Data Layer (rename + types + hooks) Summary

Renamed `SavedSeed.name` to `SavedSeed.label` across backend and added complete TypeScript types and TanStack Query hooks for all six seed endpoints.

## Tasks Completed

| Task | Description | Commit | Files |
|------|-------------|--------|-------|
| 1 | Rename SavedSeed.name to .label across backend + tests | e0f0cda | backend/models.py, backend/routers/seeds.py, backend/services/seed_service.py, tests/test_seed_service.py |
| 2 | Add TypeScript types and TanStack Query hooks | 82fc546 | frontend/src/api/types.ts, frontend/src/api/hooks.ts |

## Decisions Made

- `SavedSeed.label` (not `name`) — consistent with tag-based UI pattern (D-20); `SeedEntry.name` is the D2R character display name from the `.d2s` file, kept as-is
- `seed_service.py` also updated — it referenced `saved_seed.name` in the apply flow log line and return dict (auto-fix Rule 1 — would have caused AttributeError at runtime)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed seed_service.py referencing saved_seed.name**
- **Found during:** Task 1
- **Issue:** `backend/services/seed_service.py` lines 123 and 130 referenced `saved_seed.name` but plan only listed models.py, seeds.py, and test_seed_service.py. At runtime the apply endpoint would raise AttributeError since SavedSeed no longer has a `.name` attribute.
- **Fix:** Updated `saved_seed.name` to `saved_seed.label` in the log statement and the return dict
- **Files modified:** backend/services/seed_service.py
- **Commit:** e0f0cda (bundled with Task 1 commit)

## Verification Results

- `python3 -m pytest tests/test_seed_service.py tests/test_seeds_parser.py -q` — 17 passed
- `python3 -m pytest tests/ -q` — 655 passed, 7 skipped
- `npx tsc --noEmit` — no errors
- `SavedSeed.label` exists in model, `name` column gone from SavedSeed
- All 6 hooks present: useSeedsCurrentQuery, useSeedLibrary, useSaveSeed, useUpdateSeed, useDeleteSeed, useApplySeed

## Known Stubs

None — this plan is data layer only (model, router, types, hooks). No UI rendering, no stub values.

## Self-Check: PASSED
