---
phase: 02-write-path-library
verified: 2026-03-28T20:00:00Z
status: passed
score: 6/6 must-haves verified
re_verification: false
---

# Phase 2: Write Path + Library Verification Report

**Phase Goal:** Users can save seeds to a named library and apply any saved seed to any character's vault snapshot
**Verified:** 2026-03-28
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Success Criteria (from ROADMAP.md)

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | User can save a character's current seed to the library with a name and optional notes, and it persists across app restarts | VERIFIED | `POST /api/seeds/library` writes `SavedSeed` ORM row to SQLite; `seeds.py` lines 212-249 |
| 2 | User can edit the name and notes of an existing library entry via the API | VERIFIED | `PATCH /api/seeds/library/{seed_id}` at `seeds.py` lines 261-276 |
| 3 | User can delete a seed from the library and it no longer appears | VERIFIED | `DELETE /api/seeds/library/{seed_id}` at `seeds.py` lines 279-290, returns 204 |
| 4 | Applying a seed to a character creates a `pre_seed_restore` backup snapshot before any file is touched | VERIFIED | `seed_service.py` lines 104-109: `_create_local_backup_snapshot(session, snap, "pre_seed_restore")` called before `d2s_path.write_bytes` |
| 5 | Apply operation returns an error when D2R is detected as running; the file is not modified | VERIFIED | `seed_service.py` line 102: `await guard_mothership_write(session)` called before backup and before write; guard raises 409 |
| 6 | After a successful apply, reading the seed back from the modified vault snapshot returns the applied seed value | VERIFIED | `test_success_path_patches_file_on_disk` confirms `read_map_seed(patched_data) == 0xCAFEBABE`; all 32 tests pass |

**Score:** 6/6 success criteria verified

---

### Observable Truths (from PLAN must_haves)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | SavedSeed ORM class exists in backend/models.py with all required columns | VERIFIED | `models.py` lines 293-304: id, seed_value, name, notes, source_character, source_class, source_version, saved_at — no season_id, no UniqueConstraint |
| 2 | d2s_utils.py exports _calculate_checksum and produces the correct result | VERIFIED | `d2s_utils.py` lines 12-18: function present; demon vault tests (15 passing) confirm correct output |
| 3 | demon_service.py imports _calculate_checksum from d2s_utils instead of defining it locally | VERIFIED | `demon_service.py` line 21: `from backend.services.d2s_utils import _calculate_checksum`; no local `def _calculate_checksum` |
| 4 | write_map_seed() patches seed at correct version-conditional offset and recalculates checksum | VERIFIED | `d2s_parser.py` lines 187-223; `test_checksum_recalculated` passes in Docker |
| 5 | apply_seed_to_snapshot() creates a pre_seed_restore backup before touching any file | VERIFIED | `seed_service.py` lines 104-109: backup called at line 106, file write at line 121 |
| 6 | POST /api/seeds/library saves a seed with name, notes, and source metadata from the snapshot | VERIFIED | `seeds.py` lines 212-249; reads seed, parse_d2s for class, struct for version |
| 7 | GET /api/seeds/library returns all saved seeds newest-first | VERIFIED | `seeds.py` lines 252-258; `.order_by(SavedSeed.saved_at.desc())` |
| 8 | PATCH /api/seeds/library/{id} updates only name and notes | VERIFIED | `seeds.py` lines 261-276; only `entry.name` and `entry.notes` updated |
| 9 | DELETE /api/seeds/library/{id} removes the entry and returns 204 | VERIFIED | `seeds.py` lines 279-290; `status_code=204` |
| 10 | POST /api/seeds/{id}/apply calls guard_mothership_write, creates pre_seed_restore backup, patches .d2s, triggers push | VERIFIED | `seeds.py` lines 293-318 delegates to `apply_seed_to_snapshot`; full sequence confirmed in `seed_service.py` |

**Score:** 10/10 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/services/d2s_utils.py` | Shared D2S checksum utility | VERIFIED | 19 lines; `_calculate_checksum` function present and substantive |
| `backend/models.py` | SavedSeed ORM model | VERIFIED | `class SavedSeed(Base)` at line 293; 8 columns confirmed |
| `backend/services/d2s_parser.py` | write_map_seed helper | VERIFIED | `write_map_seed` at line 187; version-conditional, checksum recalc, size assert |
| `backend/services/seed_service.py` | Seed write orchestration | VERIFIED | 135 lines; `apply_seed_to_snapshot`, `_create_local_backup_snapshot`, `_latest_snapshot` all present |
| `backend/routers/seeds.py` | Library CRUD + apply endpoints | VERIFIED | 319 lines; 7 routes registered: `/seeds/current`, `/seeds/debug/{character}`, `/seeds/library` (POST+GET), `/seeds/library/{seed_id}` (PATCH+DELETE), `/seeds/{seed_id}/apply` |
| `tests/test_seed_service.py` | Service-layer tests | VERIFIED | `TestWriteMapSeedRoundTrip` (3 tests) + `TestApplySeedToSnapshot` (4 tests); all 7 pass |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `demon_service.py` | `d2s_utils.py` | `from backend.services.d2s_utils import _calculate_checksum` | WIRED | line 21; no local definition remains |
| `d2s_parser.py` | `d2s_utils.py` | `from backend.services.d2s_utils import _calculate_checksum` | WIRED | line 26; used at line 216 in `write_map_seed` |
| `seed_service.py` | `d2s_utils.py` | `from backend.services.d2s_utils import _calculate_checksum` | IMPORTED — UNUSED | line 23; `_calculate_checksum` imported but never called in service body (checksum work delegated to `write_map_seed` in parser). Not a bug — checksum is still recalculated correctly. Dead import only. |
| `seed_service.py` | `d2s_parser.py` | `write_map_seed` call | WIRED | `write_map_seed` imported at line 22; called at line 113 |
| `seeds.py` | `models.py` | `from backend.models import.*SavedSeed` | WIRED | line 27; `SavedSeed` used in all CRUD handlers |
| `seeds.py` | `seed_service.py` | `from backend.services.seed_service import apply_seed_to_snapshot` | WIRED | line 29; called at line 313 in `apply_seed` route |
| `seeds.py` | `auto_sync.py` | `BackgroundTasks` passed to `apply_seed_to_snapshot` | WIRED | `background_tasks: BackgroundTasks` at line 297; passed through to service |
| `main.py` | `seeds.py` | `app.include_router(seeds_router.router, prefix="/api")` | WIRED | `main.py` lines 19 + 55 |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `seeds.py` POST `/seeds/library` | `seed` (from `read_map_seed`) | `d2s_path.read_bytes()` from snapshot dir | Yes — reads real .d2s bytes | FLOWING |
| `seeds.py` GET `/seeds/library` | `result.scalars().all()` | `select(SavedSeed).order_by(saved_at.desc())` | Yes — real DB query | FLOWING |
| `seed_service.py` `apply_seed_to_snapshot` | `patched` bytes | `write_map_seed(original, saved_seed.seed_value)` | Yes — mutates real file bytes and writes to disk | FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| `write_map_seed` round-trip v100 | `pytest tests/test_seeds_parser.py::TestWriteMapSeed::test_v100_seed_written_correctly` | PASS | PASS |
| `write_map_seed` checksum recalculated | `pytest tests/test_seeds_parser.py::TestWriteMapSeed::test_checksum_recalculated` | PASS | PASS |
| `apply_seed_to_snapshot` patches file on disk | `pytest tests/test_seed_service.py::TestApplySeedToSnapshot::test_success_path_patches_file_on_disk` | PASS | PASS |
| `apply_seed_to_snapshot` 404 when no snapshot | `pytest tests/test_seed_service.py::TestApplySeedToSnapshot::test_returns_404_when_no_snapshot` | PASS | PASS |
| All Phase 2 tests | `pytest tests/test_seed_service.py tests/test_seeds_parser.py tests/test_demon_vault.py -v` | 32 passed | PASS |
| Seeds router imports cleanly | `python3 -c "from backend.routers.seeds import router; print(len(router.routes))"` | 7 routes | PASS |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| SEED-04 | 02-03-PLAN.md | User can save a seed to the library with a name and optional notes | SATISFIED | `POST /api/seeds/library` in `seeds.py` lines 212-249 |
| SEED-05 | 02-03-PLAN.md | User can edit the name and notes of a saved seed | SATISFIED | `PATCH /api/seeds/library/{seed_id}` in `seeds.py` lines 261-276 |
| SEED-06 | 02-03-PLAN.md | User can delete a seed from the library | SATISFIED | `DELETE /api/seeds/library/{seed_id}` in `seeds.py` lines 279-290 |
| SEED-07 | 02-02-PLAN.md, 02-04-PLAN.md | User can apply any saved seed to any character's .d2s file | SATISFIED | `POST /api/seeds/{seed_id}/apply` → `apply_seed_to_snapshot` |
| SEED-08 | 02-02-PLAN.md, 02-04-PLAN.md | Apply creates a `pre_seed_restore` backup snapshot before modifying any file | SATISFIED | `seed_service.py` lines 104-109; backup precedes file write |
| SEED-09 | 02-02-PLAN.md, 02-04-PLAN.md | Apply is blocked when D2R is detected as running | SATISFIED | `guard_mothership_write(session)` at `seed_service.py` line 102 raises 409 |
| SEED-10 | 02-02-PLAN.md, 02-04-PLAN.md | Apply creates a new vault snapshot from the modified file | SATISFIED | `trigger_mothership_push(background_tasks, session)` at `seed_service.py` line 127; push runs after write |
| SEED-11 | 02-01-PLAN.md, 02-02-PLAN.md, 02-04-PLAN.md | Checksum is recalculated correctly after patching the seed bytes | SATISFIED | `write_map_seed` zeros checksum field then recalculates via `_calculate_checksum`; `test_checksum_recalculated` passes |

All 8 requirements (SEED-04 through SEED-11) are SATISFIED. No orphaned requirements.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `backend/services/seed_service.py` | 23 | `from backend.services.d2s_utils import _calculate_checksum` — imported but never called | Info | Zero functional impact; checksum recalculation correctly handled inside `write_map_seed`. Dead import added per plan spec but plan spec itself was over-specified — the service delegates to the parser rather than calling checksum directly. |

No blockers. No stubs. No placeholder implementations.

---

### Human Verification Required

None. All success criteria are verifiable programmatically. The frontend (Phase 3) has not been built yet — endpoint behavior is confirmed via unit tests and router inspection.

---

### Gaps Summary

No gaps. All 8 requirements are implemented, all artifacts exist and are substantive, all key links are wired, and the test suite passes (32 tests: 0 failures, 0 regressions against Phase 1 baseline).

The one informational item — an unused `_calculate_checksum` import in `seed_service.py` — has zero functional impact. The checksum is correctly recalculated inside `write_map_seed` in `d2s_parser.py`, which is called by the service. The import was specified in the plan's acceptance criteria but the implementation chose the cleaner delegation pattern.

---

_Verified: 2026-03-28T20:00:00Z_
_Verifier: Claude (gsd-verifier)_
