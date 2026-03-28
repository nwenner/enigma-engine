---
phase: 01-parser-read-verification
verified: 2026-03-28T00:00:00Z
status: passed
score: 5/5 must-haves verified
re_verification: false
---

# Phase 1: Parser + Read Verification Report

**Phase Goal:** The app can reliably read map seeds from vault snapshot files and the correct offset is empirically confirmed
**Verified:** 2026-03-28
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `read_map_seed()` returns the correct 4-byte LE uint from offset 0x9B for v100+ files | VERIFIED | `d2s_parser.py:179` — `offset = 0x9B if version >= 100 else 0xAB`; `test_v100_seed_read_correctly` passes with 0x01C73932 |
| 2 | `read_map_seed()` returns the correct 4-byte LE uint from offset 0xAB for v96-99 files | VERIFIED | Same conditional at `d2s_parser.py:179`; `test_v99_seed_read_correctly` passes with 0xDEADBEEF |
| 3 | `GET /api/seeds/current` returns all characters from the latest vault snapshot with `seed_decimal` and `seed_hex` | VERIFIED | `seeds.py:88-115` — iterates `snap_dir.glob("*.d2s")`, builds `SeedEntry` with both fields; `seed_hex` formatted as `0x{seed:08X}` |
| 4 | `GET /api/seeds/debug/{character}` returns raw hex windows at both candidate offsets for empirical verification | VERIFIED | `seeds.py:118-160` — reads both offsets 0x9B and 0xAB, returns `SeedDebugResponse` with hex windows via `_hex_window()`; Nick confirmed `seed_at_v100` matches d2mapseed output (2026-03-28) |
| 5 | A corrupt or truncated .d2s file does not crash the `/seeds/current` endpoint | VERIFIED | `seeds.py:111-112` — `except (D2SParseError, OSError, struct.error) as e: errors.append(f"{path.name}: {e}")` — errors collected per-file, endpoint always returns full response |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/services/d2s_parser.py` | `read_map_seed(data: bytes) -> int` helper | VERIFIED | `def read_map_seed` at line 169; standalone function, not integrated into `D2SCharacter` or `parse_d2s()` |
| `backend/routers/seeds.py` | GET /seeds/current and GET /seeds/debug/{character} endpoints | VERIFIED | Both routes present at lines 88 and 118; `router = APIRouter(tags=["seeds"])` at line 26 |
| `backend/main.py` | seeds router registration | VERIFIED | `from backend.routers import seeds as seeds_router` at line 19; `app.include_router(seeds_router.router, prefix="/api")` at line 55 |
| `tests/test_seeds_parser.py` | Unit tests for `read_map_seed` | VERIFIED | 5 test methods in `TestReadMapSeed`; `from __future__ import annotations` present; Tald.d2s fixture at `tests/fixtures/Tald.d2s` (3882 bytes) |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `backend/routers/seeds.py` | `backend/services/d2s_parser.py` | `import read_map_seed` | WIRED | Line 23: `from backend.services.d2s_parser import CLASS_NAMES, D2SParseError, MAGIC, parse_d2s, read_map_seed` |
| `backend/routers/seeds.py` | `backend/models.py` | BackupSnapshot query for latest snapshot | WIRED | Line 22 import; lines 31-45 `_latest_snapshot()` queries `BackupSnapshot` with Season guard (copied verbatim from demon.py) |
| `backend/main.py` | `backend/routers/seeds.py` | include_router registration | WIRED | Line 19 import + line 55 `app.include_router(seeds_router.router, prefix="/api")` |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `seeds.py` GET /seeds/current | `entries` (list of SeedEntry) | `BackupSnapshot` DB query → disk read of `*.d2s` files → `parse_d2s()` + `read_map_seed()` | Yes — queries DB for latest snapshot, reads binary files from snapshot directory on disk | FLOWING |
| `seeds.py` GET /seeds/debug/{character} | `seed_at_v100`, `seed_at_v99` | Same `BackupSnapshot` query → reads `{character}.d2s` from snapshot dir | Yes — reads actual file bytes and unpacks at both offsets | FLOWING |

### Behavioral Spot-Checks

| Behavior | Check | Status |
|----------|-------|--------|
| `read_map_seed()` parses v100+ offset correctly | `test_v100_seed_read_correctly` asserts `0x01C73932` | PASS (5/5 tests confirmed by SUMMARY) |
| `read_map_seed()` parses v96-99 offset correctly | `test_v99_seed_read_correctly` asserts `0xDEADBEEF` | PASS |
| Tald.d2s returns known-correct seed | `test_tald_fixture_returns_known_seed` asserts `0x01C73932` | PASS — confirmed empirically by Nick against d2mapseed tool |
| Truncated file raises error, not crash | `test_file_too_small_raises_parse_error` and `test_v105_truncated_raises_parse_error` | PASS |
| Full test suite — no regressions | 643 passed, 7 skipped | PASS (reported in SUMMARY) |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| SEED-01 | 01-01-PLAN.md | App reads the map seed from each character's .d2s file in the latest vault snapshot | SATISFIED | `GET /api/seeds/current` iterates all `.d2s` files in the latest snapshot and returns seed per character |
| SEED-02 | 01-01-PLAN.md | App handles version-conditional offset (v96-99 at 0xAB, v100+ at 0x9B) correctly | SATISFIED | `read_map_seed()` at `d2s_parser.py:179` — `offset = 0x9B if version >= 100 else 0xAB`; v96-99 and v100+ unit tests both pass; Nick confirmed v100+ value correct against d2mapseed |

No orphaned requirements: REQUIREMENTS.md maps SEED-01 and SEED-02 to Phase 1 — both claimed in 01-01-PLAN.md and both satisfied.

SEED-03 (Map Seeds page) is mapped to Phase 3 and is NOT a Phase 1 requirement. Correctly deferred.

### Anti-Patterns Found

None detected. Scan of `backend/services/d2s_parser.py`, `backend/routers/seeds.py`, and `tests/test_seeds_parser.py` found:

- No TODO / FIXME / PLACEHOLDER comments
- No stub return patterns (`return []`, `return {}`, `return null`)
- No hardcoded empty data passed to rendering paths
- No console-log-only implementations
- Error handling in `/seeds/current` uses proper isolation (per-file try/except) rather than swallowing all errors silently

### Human Verification Required

All automated checks passed. One item was verified by human (Task 3 checkpoint):

**Seed value correctness — completed 2026-03-28**

Nick confirmed `seed_at_v100` from `GET /api/seeds/debug/Tald` matches d2mapseed tool output for the Tald.d2s character. Offset `0x9B` for v100+ saves is empirically confirmed correct. The Phase 2 write code gate is cleared.

The v96-99 offset (0xAB) was not independently verified against a live v96-99 save file — this is acceptable because v96-99 is the pre-2.x D2R release format and current saves are v100+. The unit test with a synthetic file at 0xAB provides structural coverage.

### Gaps Summary

No gaps. All five must-have truths are verified. Both Phase 1 requirements (SEED-01, SEED-02) are satisfied. The human checkpoint (Task 3) was completed with positive outcome. Full test suite passes with 643 passing, 7 skipped, no regressions.

---

_Verified: 2026-03-28_
_Verifier: Claude (gsd-verifier)_
