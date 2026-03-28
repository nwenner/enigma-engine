---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: unknown
last_updated: "2026-03-28T22:47:28.086Z"
progress:
  total_phases: 3
  completed_phases: 2
  total_plans: 7
  completed_plans: 6
---

# Project State: Enigma Engine — Map Seed Milestone

**Last updated:** 2026-03-28
**Milestone:** Map Seed Milestone

---

## Project Reference

**Core value:** Save and restore D2R map seeds so known-good farming layouts are never lost.

**Current focus:** Phase 03 — frontend

---

## Current Position

Phase: 03 (frontend) — EXECUTING
Plan: 2 of 2
| Field | Value |
|-------|-------|
| Phase | 1 — Parser + Read Verification |
| Plan | None (not started) |
| Status | Not started |
| Progress | Phase 0/3 complete |

```
[████░░░░░░] 40%
```

---

## Performance Metrics

| Metric | Value |
|--------|-------|
| Phases complete | 1/3 |
| Plans complete | 2 |
| Requirements done | 1/11 |

| Phase 02-write-path-library P01 | 10min | 2 tasks | 3 files |
| Phase 02-write-path-library P02 | 15min | 2 tasks | 3 files |
| Phase 02-write-path-library P03 | 10min | 1 tasks | 1 files |
| Phase 02-write-path-library P04 | 12min | 2 tasks | 2 files |
| Phase 03-frontend P01 | 8 | 2 tasks | 6 files |

## Accumulated Context

### Key Decisions Logged

- Seed library is global (not season-scoped) — seeds are valuable across seasons
- Read/write from vault snapshot, not live SSH — consistent with grail/vault/demon pattern
- Snapshot only after restore (no auto-push) — user controls when changes go to device
- Apply seed to any character (not just source) — core use case is sharing great maps
- SavedSeed has no season_id FK — seeds are globally valid across seasons (02-01)
- _calculate_checksum extracted to d2s_utils.py — shared between demon_service and seed_service (02-01)

### Critical Technical Notes

- Offset is version-conditional: `0x9B` for v100+, `0xAB` for v96-99
  - Same 16-byte shift already handled in `d2s_parser.py` at lines 129-135 for difficulty field
  - MUST empirically verify against real v100+ save before Phase 2 write code is built
- Checksum algorithm: reuse `_calculate_checksum` from `demon_service.py` — extract to `d2s_utils.py` in Phase 2
- File size must NOT change after seed patch (unlike demon restore) — `assert len(patched) == len(original)`
- `SavedSeed` model must NOT have a `season_id` FK — seeds are globally valid

### Phase Gate

Phase 1 → Phase 2 is a HARD GATE. Do not build any write code until seed values from `GET /api/seeds/current` are confirmed correct against at least one v100+ and one v96-99 save file.

### Todos

- (none yet)

### Blockers

- (none)

---

## Session Continuity

**To resume this milestone:**

1. Read this file for current position
2. Read `.planning/ROADMAP.md` for full phase structure
3. If a phase is in progress, read `.planning/plans/phase-N-*.md` for active plan
4. Run tests: `docker run --rm -v $(pwd):/app -w /app enigma-engine-enigma-engine python3 -m pytest tests/ -q`

**Last session:** 2026-03-28T22:47:28.084Z
**Next action:** Execute 02-02-PLAN.md (seed_service.py with read + write + apply logic)
