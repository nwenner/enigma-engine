---
phase: 02-write-path-library
plan: 01
subsystem: database
tags: [sqlalchemy, d2s, checksum, orm, models]

# Dependency graph
requires: []
provides:
  - SavedSeed ORM model in backend/models.py (saved_seeds table)
  - backend/services/d2s_utils.py with shared _calculate_checksum helper
affects:
  - 02-02 (seed_service.py uses d2s_utils._calculate_checksum)
  - 02-03 (seeds router uses SavedSeed model)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Shared binary utility module pattern: extract repeated low-level helpers to d2s_utils.py"
    - "SavedSeed model follows BoundDemon shape: no season FK, no unique constraint on value"

key-files:
  created:
    - backend/services/d2s_utils.py
  modified:
    - backend/models.py
    - backend/services/demon_service.py

key-decisions:
  - "SavedSeed has no season_id FK — seeds are globally valid across seasons (D-02)"
  - "No UniqueConstraint on seed_value — duplicate seeds allowed (D-03)"
  - "_calculate_checksum extracted to d2s_utils.py — shared between demon_service and future seed_service (D-14)"

patterns-established:
  - "d2s_utils.py is the canonical home for low-level D2S binary helpers shared across services"

requirements-completed:
  - SEED-11

# Metrics
duration: 10min
completed: 2026-03-28
---

# Phase 02 Plan 01: Foundation Layer Summary

**SavedSeed ORM model added and _calculate_checksum extracted from demon_service into shared d2s_utils.py**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-03-28T18:40:00Z
- **Completed:** 2026-03-28T18:50:00Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Created `backend/services/d2s_utils.py` with shared `_calculate_checksum` helper, eliminating the duplication that will exist once `seed_service.py` is built in plan 02-02
- Updated `demon_service.py` to import from `d2s_utils` instead of defining the function locally — all 15 demon vault tests remain green
- Added `SavedSeed` ORM class to `backend/models.py` with all 8 required columns, following the `BoundDemon` template shape, with no season FK and no unique constraint on seed_value as per design decisions

## Task Commits

Each task was committed atomically:

1. **Task 1: Create d2s_utils.py and extract checksum from demon_service** - `560a44e` (feat)
2. **Task 2: Add SavedSeed model to backend/models.py** - `067ffda` (feat)

**Plan metadata:** (docs commit below)

## Files Created/Modified
- `backend/services/d2s_utils.py` - New shared D2S binary utility module with `_calculate_checksum`
- `backend/models.py` - Added `SavedSeed` class at end under Map Seed Library section
- `backend/services/demon_service.py` - Replaced local `_calculate_checksum` with import from `d2s_utils`

## Decisions Made
- `_calculate_checksum` placed in `d2s_utils.py` (not `d2s_parser.py`) per D-14 — parser handles struct reads, utils handles low-level binary math
- `SavedSeed.seed_value` uses `Integer` (SQLAlchemy/SQLite handles uint32 range without overflow)
- No `__table_args__` needed — simple append after `BossSummonProgress`

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- `d2s_utils.py` ready for `seed_service.py` to import `_calculate_checksum` in plan 02-02
- `SavedSeed` model available for CRUD endpoints in plan 02-03
- No blockers

## Self-Check: PASSED

- FOUND: backend/services/d2s_utils.py
- FOUND: backend/models.py (SavedSeed class)
- FOUND: commit 560a44e (feat: extract checksum)
- FOUND: commit 067ffda (feat: add SavedSeed)
- Verification commands all passed

---
*Phase: 02-write-path-library*
*Completed: 2026-03-28*
