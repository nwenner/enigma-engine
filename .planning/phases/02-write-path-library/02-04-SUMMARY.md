---
phase: 02-write-path-library
plan: "04"
subsystem: api
tags: [fastapi, seed, d2s, backup, testing]

# Dependency graph
requires:
  - phase: 02-write-path-library/02-02
    provides: apply_seed_to_snapshot service + write_map_seed
  - phase: 02-write-path-library/02-03
    provides: seeds.py CRUD endpoints and SavedSeed ORM
provides:
  - POST /api/seeds/{seed_id}/apply endpoint
  - Unit tests for seed service apply flow and write_map_seed round-trip
affects: [phase-03-frontend, integration-testing]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Router delegates to service: apply_seed endpoint looks up SavedSeed, raises 404 if absent, then delegates to apply_seed_to_snapshot"
    - "TDD test pattern for service with mock filesystem (tmp_path) and mock session"

key-files:
  created:
    - tests/test_seed_service.py
  modified:
    - backend/routers/seeds.py

key-decisions:
  - "seed_id (not id) used consistently as path param — matches delete_seed pattern in same router"
  - "Router handles 404 for missing seed before delegating to service — separates DB lookup from filesystem logic"

patterns-established:
  - "Router 404 guard: lookup ORM record in router, raise 404 before calling service — consistent with demon/grail restore pattern"
  - "Test isolation: mock get_settings().data_dir to tmp_path — avoids touching production data dir"

requirements-completed: [SEED-07, SEED-08, SEED-09, SEED-10, SEED-11]

# Metrics
duration: 12min
completed: 2026-03-28
---

# Phase 02 Plan 04: Apply Endpoint + Service Tests Summary

**POST /api/seeds/{seed_id}/apply wired to apply_seed_to_snapshot with 7 unit tests covering round-trip write, 404 paths, success dict shape, and disk patch verification**

## Performance

- **Duration:** 12 min
- **Started:** 2026-03-28T19:00:00Z
- **Completed:** 2026-03-28T19:12:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Added `POST /api/seeds/{seed_id}/apply` endpoint to `backend/routers/seeds.py` — looks up SavedSeed by ID, raises 404 if not found, delegates to `apply_seed_to_snapshot`
- Added `BackgroundTasks` to the router's FastAPI imports and `ApplySeedRequest` schema
- Created `tests/test_seed_service.py` with 7 tests: 3 round-trip tests for `write_map_seed`, 4 tests for `apply_seed_to_snapshot` (404 no snapshot, 404 char missing, success dict, file patched on disk)
- Full suite: 655 passed, 7 skipped — no regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Add apply endpoint to seeds.py** - `b7d6148` (feat)
2. **Task 2: Write tests for seed service apply flow** - `3b15088` (test)

## Files Created/Modified

- `backend/routers/seeds.py` - Added `BackgroundTasks` import, `ApplySeedRequest` schema, `apply_seed` route, `apply_seed_to_snapshot` import
- `tests/test_seed_service.py` - New: TestWriteMapSeedRoundTrip (3 tests) + TestApplySeedToSnapshot (4 tests)

## Decisions Made

- `{seed_id}` used as path param (not `{id}`) — consistent with `delete_seed` in same router
- Router handles 404 for missing SavedSeed before calling service — DB concerns in router, filesystem concerns in service

## Deviations from Plan

None — plan executed exactly as written. The prior agents' work (plans 02-01 through 02-03) was cherry-picked into this worktree before execution since those commits were on other worktree branches.

## Issues Encountered

Prior plan commits (02-01, 02-02, 02-03) were on separate worktree branches and not in this branch's HEAD. Cherry-picked all 8 preceding commits in order before starting plan 04 tasks. No conflicts.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- Phase 02 complete: all 8 requirements SEED-04 through SEED-11 have implementation
- `POST /api/seeds/{seed_id}/apply` is the final missing endpoint — map seed write path is complete
- Phase 03 (frontend) can now build the Map Seeds UI against all backend endpoints

---
*Phase: 02-write-path-library*
*Completed: 2026-03-28*

## Self-Check: PASSED

- FOUND: backend/routers/seeds.py
- FOUND: tests/test_seed_service.py
- FOUND: .planning/phases/02-write-path-library/02-04-SUMMARY.md
- FOUND: commit b7d6148 (feat: apply endpoint)
- FOUND: commit 3b15088 (test: seed service tests)
