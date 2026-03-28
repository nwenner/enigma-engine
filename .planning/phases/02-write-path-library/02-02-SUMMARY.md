---
phase: 02-write-path-library
plan: 02
subsystem: binary-patch
tags: [d2s, checksum, seed, backup, fastapi, sqlalchemy]

# Dependency graph
requires:
  - phase: 02-01
    provides: d2s_utils._calculate_checksum, SavedSeed ORM model
provides:
  - write_map_seed() in backend/services/d2s_parser.py
  - backend/services/seed_service.py with apply_seed_to_snapshot orchestration
affects:
  - 02-03 (seeds router apply endpoint calls apply_seed_to_snapshot)
  - 02-04 (frontend apply flow calls the apply endpoint built in 02-03)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "write_map_seed mirrors read_map_seed — version-conditional offset, checksum recalc, size assert"
    - "_create_local_backup_snapshot copied verbatim from grail_service (D-15 — each service owns its copy)"
    - "guard_mothership_write imported lazily (inline import) to avoid circular dependency"

key-files:
  created:
    - backend/services/seed_service.py
  modified:
    - backend/services/d2s_parser.py
    - tests/test_seeds_parser.py

key-decisions:
  - "write_map_seed uses assert (not raise) for size invariant — programming error, not user error"
  - "guard_mothership_write imported inside apply_seed_to_snapshot to avoid circular import with auto_sync"

patterns-established:
  - "TDD RED→GREEN: failing tests committed before implementation"

requirements-completed:
  - SEED-07
  - SEED-08
  - SEED-09
  - SEED-10
  - SEED-11

# Metrics
duration: 15min
completed: 2026-03-28
---

# Phase 02 Plan 02: Write Path Library Summary

**write_map_seed() added to d2s_parser with version-conditional patching and checksum recalc; seed_service.py implements full guard→backup→patch→write→push apply sequence**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-03-28T19:00:00Z
- **Completed:** 2026-03-28T19:15:00Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Added `write_map_seed()` to `d2s_parser.py` — patches seed at version-conditional offset (0x9B for v100+, 0xAB for v96-99), recalculates checksum, asserts file size unchanged
- Added 5-test `TestWriteMapSeed` class to `test_seeds_parser.py` using TDD (RED commit before GREEN); all 10 parser tests pass
- Created `backend/services/seed_service.py` with full D-11 apply sequence: `guard_mothership_write` → `pre_seed_restore` backup → `write_map_seed` → disk write → `trigger_mothership_push`; importable with no errors in Docker

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): Add failing TestWriteMapSeed tests** - `8ac2c74` (test)
2. **Task 1 (GREEN): Add write_map_seed() to d2s_parser.py** - `89020b9` (feat)
3. **Task 2: Create seed_service.py** - `b04d631` (feat)

## Files Created/Modified
- `backend/services/d2s_parser.py` - Added `write_map_seed()` and `from backend.services.d2s_utils import _calculate_checksum`
- `backend/services/seed_service.py` - New service with `_latest_snapshot`, `_create_local_backup_snapshot`, `apply_seed_to_snapshot`
- `tests/test_seeds_parser.py` - Added `TestWriteMapSeed` class (5 tests), import for `write_map_seed` and `_calculate_checksum`

## Decisions Made
- `write_map_seed` uses `assert` for size invariant (programming error level, not user error) — consistent with plan spec
- `guard_mothership_write` and `trigger_mothership_push` imported inline inside the function body to avoid circular dependency with `auto_sync.py`

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Worktree branch was behind `main` (02-01 changes merged via separate worktree). Resolved by merging `main` into the worktree branch before execution.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- `write_map_seed` ready for direct use in tests or router
- `apply_seed_to_snapshot` ready for the apply endpoint in 02-03
- No blockers

## Self-Check: PASSED

- FOUND: backend/services/d2s_parser.py (write_map_seed function present)
- FOUND: backend/services/seed_service.py (apply_seed_to_snapshot present)
- FOUND: tests/test_seeds_parser.py (TestWriteMapSeed class present)
- FOUND: commit 8ac2c74 (test RED)
- FOUND: commit 89020b9 (feat GREEN)
- FOUND: commit b04d631 (feat seed_service)
- All 10 parser tests pass in Docker
- Import verification passes in Docker

---
*Phase: 02-write-path-library*
*Completed: 2026-03-28*
