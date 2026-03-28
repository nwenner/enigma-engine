---
plan: 01-01
phase: 01-parser-read-verification
status: complete
completed: 2026-03-28
key-files:
  created:
    - backend/routers/seeds.py
    - tests/test_seeds_parser.py
  modified:
    - backend/services/d2s_parser.py
    - backend/main.py
---

# Plan 01-01: Add Map Seed Reading to D2S Parser

## What Was Built

Added `read_map_seed(data: bytes) -> int` to `backend/services/d2s_parser.py` with version-conditional offset logic (`0x9B` for v100+, `0xAB` for v96-99). Created `backend/routers/seeds.py` with two endpoints: `GET /api/seeds/current` (all characters with seed values from latest vault snapshot) and `GET /api/seeds/debug/{character}` (raw byte windows at both candidate offsets for empirical verification). Router registered in `main.py`. 5 unit tests added.

## Checkpoint Outcome

Human verification completed 2026-03-28. Nick confirmed `seed_at_v100` value from debug endpoint is correct. Offset `0x9B` for v100+ save files is confirmed — Phase 2 write code gate is cleared.

## Test Results

- 5/5 unit tests pass (including Tald.d2s fixture smoke test)
- Full suite: 643 passed, 7 skipped — no regressions

## Decisions

- Seed reading is a standalone helper, not integrated into `D2SCharacter` or `parse_d2s()` (per D-01)
- Debug endpoint left in permanently (per D-07)
- Parse errors isolated per-file; one bad .d2s never crashes the whole response (per D-08)
