---
phase: 02-write-path-library
plan: 03
subsystem: api
tags: [fastapi, sqlalchemy, pydantic, crud, seeds]

# Dependency graph
requires:
  - phase: 02-01
    provides: SavedSeed ORM model in backend/models.py (saved_seeds table)
  - phase: 01-01
    provides: read_map_seed() in d2s_parser.py, seeds.py router skeleton
provides:
  - POST /api/seeds/library — save character's current map seed to named library
  - GET /api/seeds/library — list all saved seeds newest-first
  - PATCH /api/seeds/library/{id} — update name and notes of a saved seed
  - DELETE /api/seeds/library/{id} — remove a saved seed (204)
affects:
  - 02-04 (apply endpoint will use SavedSeed from library via GET /api/seeds/library)
  - Phase 3 (frontend library UI consumes these endpoints)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Library CRUD pattern: save-from-snapshot → list-newest-first → patch-name/notes → delete-204"
    - "_seed_record() helper serializes SavedSeed ORM to SavedSeedRecord Pydantic model"

key-files:
  created: []
  modified:
    - backend/routers/seeds.py

key-decisions:
  - "version read inline (struct.unpack_from) in POST handler — avoids adding source_version to parse_d2s return"
  - "saved_at stored as UTC naive datetime (replace(tzinfo=None)) — consistent with BoundDemon pattern"
  - "DELETE returns 204 (no body) — matches REST convention, differs from demon delete which returns JSON"

patterns-established:
  - "_seed_record() helper: thin ORM-to-Pydantic serializer, placed before route block"

requirements-completed:
  - SEED-04
  - SEED-05
  - SEED-06

# Metrics
duration: 10min
completed: 2026-03-28
---

# Phase 02 Plan 03: Library CRUD Endpoints Summary

**Four seed library CRUD endpoints added to seeds.py: POST saves seed from snapshot, GET lists newest-first, PATCH updates name/notes, DELETE returns 204**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-03-28T19:00:00Z
- **Completed:** 2026-03-28T19:10:00Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments
- Added `POST /api/seeds/library` that reads the map seed from the latest vault snapshot for a character, parses the class name via `parse_d2s`, stores all source metadata in `SavedSeed`, returns 201 with `SavedSeedRecord`
- Added `GET /api/seeds/library` listing all saved seeds ordered by `saved_at` descending with no pagination
- Added `PATCH /api/seeds/library/{seed_id}` updating only `name` and `notes` fields, returns updated record
- Added `DELETE /api/seeds/library/{seed_id}` with 204 status (no body)
- Added `SaveSeedRequest`, `UpdateSeedRequest`, `SavedSeedRecord` Pydantic schemas and `_seed_record()` helper

## Task Commits

Each task was committed atomically:

1. **Task 1: Add library CRUD endpoints to seeds.py** - `00611d4` (feat)

**Plan metadata:** (docs commit below)

## Files Created/Modified
- `backend/routers/seeds.py` - Added 4 new route handlers, 3 Pydantic schemas, 1 helper function; updated imports to include `SavedSeed`, `datetime`, `timezone`

## Decisions Made
- Version extracted inline via `struct.unpack_from("<II", data, 0)` rather than adding it to `D2SCharacter` — avoids scope creep into the parser
- Used `datetime.now(timezone.utc).replace(tzinfo=None)` for `saved_at` — consistent with `BoundDemon` naive UTC pattern already in the codebase
- DELETE endpoint returns 204 with no body — cleaner REST semantics than the demon vault's `{"success": True}` pattern

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Merged upstream main into worktree to bring in foundation work**
- **Found during:** Task 1 setup
- **Issue:** Worktree was created before 02-01 and Phase 1 commits were merged into main. `SavedSeed` model and `read_map_seed` were absent from the worktree.
- **Fix:** Added upstream remote pointing to local repo and merged to bring in commits from 01-01 and 02-01 (seeds.py skeleton, SavedSeed model, d2s_utils.py, read_map_seed).
- **Files modified:** None (merge only)
- **Verification:** `grep SavedSeed backend/models.py` found at line 293; `grep read_map_seed backend/services/d2s_parser.py` found.
- **Committed in:** Merge commit (pre-task)

---

**Total deviations:** 1 auto-fixed (1 blocking — missing foundation from parallel worktree)
**Impact on plan:** Blocking issue resolved before any code was written. No scope creep.

## Issues Encountered

The parallel worktree was forked from origin/main before phases 01-01 and 02-01 were merged locally. A merge from the local repo's main branch brought in all required foundation work before implementation began.

## User Setup Required

None - no external service configuration required.

## Known Stubs

None — all four CRUD endpoints are fully wired to the `SavedSeed` ORM model and return proper data.

## Next Phase Readiness
- All four library endpoints ready for 02-04 (apply endpoint) to reference `SavedSeed` records via `GET /api/seeds/library`
- All four endpoints ready for Phase 3 frontend to consume
- No blockers

## Self-Check: PASSED

- FOUND: backend/routers/seeds.py (contains all 4 new routes)
- FOUND: commit 00611d4 (feat: library CRUD)
- grep "router.post.*seeds/library" — found at line 207
- grep "router.get.*seeds/library" — found at line 247
- grep "router.patch.*seeds/library" — found at line 256
- grep "router.delete.*seeds/library" — found at line 274
- pytest tests/ — 225 passed, 1 pre-existing failure, 25 skipped

---
*Phase: 02-write-path-library*
*Completed: 2026-03-28*
