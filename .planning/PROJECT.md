# Enigma Engine — Map Seed Milestone

## What This Is

Enigma Engine is a self-hosted web app (FastAPI + React, Dockerized) that bidirectionally syncs Diablo 2 Resurrected `.d2s` save files between a Windows PC and Steam Deck. It manages sync state, backups, character tracking, a Holy Grail tracker, an Item Vault, and a Demon Vault — all accessible from a local web UI.

This milestone adds **Map Seed management**: read the procedurally-generated map seed from any character's save file, save desirable seeds to a named library with notes, and apply any saved seed to any character to reproduce a known-good farming layout.

## Core Value

Save and restore D2R map seeds so known-good farming layouts are never lost.

## Requirements

### Validated

- ✓ Bidirectional .d2s sync between PC and Steam Deck over SSH/SFTP — existing
- ✓ Auto-sync watcher with game-close detection and device-online push — existing
- ✓ Manual Check In and Sync to Device — existing
- ✓ Conflict detection and resolution — existing
- ✓ Snapshot-based backup system (game_close, manual, pre_sync, season_archive) — existing
- ✓ Binary .d2s parser (struct-based character fields) — existing
- ✓ Binary .d2i stash parser (deterministic bit-position tracking) — existing
- ✓ Character tracking per season — existing
- ✓ Holy Grail tracker (deposit/retrieve via Tab 5) — existing
- ✓ Item Vault (store/retrieve items, gold vault) — existing
- ✓ Demon Vault (save/restore bound Warlock demon) — existing
- ✓ Season management (start, archive, stats) — existing
- ✓ Season rewards (item library, claim flow) — existing

### Active

- [ ] Read the map seed value from a character's .d2s file (from latest vault snapshot)
- [ ] Display all characters' current seeds on a Map Seeds page
- [x] Save a seed to a persistent library with a name and optional notes — *Validated in Phase 02: write-path-library*
- [x] Apply any saved seed to any character's .d2s file (patch in vault snapshot) — *Validated in Phase 02: write-path-library*
- [x] After applying, create a new snapshot from the modified file — *Validated in Phase 02: write-path-library*
- [x] Seed library persists globally (not season-scoped) — *Validated in Phase 02: write-path-library*

### Out of Scope

- Per-season seed scoping — seeds are good across seasons, no need to archive them
- Auto-push to device after seed restore — user syncs manually via existing Sync to Device
- Manual seed entry — seeds are always read from the save file, not typed in
- Map screenshots or visual area previews — out of scope for v1
- Sharing seeds between users (export/import) — not needed yet

## Context

- **Existing binary safety protocol**: Any modification to a .d2s file requires a full backup (BackupSnapshot) before the write. Map seed restore must follow this — create a `pre_seed_restore` backup snapshot before patching the file.
- **D2R must be closed**: All write operations check that D2R is not running before modifying files. Same check applies here.
- **Vault snapshot as source of truth**: Reads and writes happen against the latest `manual` or `game_close` snapshot in the local vault — consistent with grail, item vault, and demon vault patterns.
- **Map seed location in .d2s**: The map seed is a 32-bit unsigned integer. Location in D2R format needs to be verified empirically (likely around offset 0xA8 or similar — to be confirmed in Phase 1 research).
- **Existing parser**: `backend/services/d2s_parser.py` already parses character fields. Map seed parsing will extend this.
- **Frontend patterns**: New page follows the established nav pattern (e.g., Item Vault `/stash`, Demon Vault `/demon`).

## Constraints

- **Tech stack**: FastAPI + SQLAlchemy async (backend), React + TypeScript + TanStack Query + Tailwind (frontend) — no new frameworks
- **Binary safety**: NEVER modify a save file without creating a BackupSnapshot first — non-negotiable per established protocol
- **D2R running check**: Must verify D2R is not running before any file modification
- **Snapshot-based reads**: Read operations use the local vault snapshot, not live SSH, for consistency and speed

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Seed library is global (not season-scoped) | A good map layout is valuable across seasons | Confirmed — no season_id FK on SavedSeed (Phase 02) |
| Read/write from vault snapshot, not live SSH | Consistent with grail/vault pattern; no SSH needed for reads | Confirmed — seed_service reads from latest snapshot path (Phase 02) |
| Snapshot only after restore (no auto-push) | User controls when changes go to device | Confirmed — apply flow creates snapshot, no auto-push (Phase 02) |
| Apply seed to any character (not just source) | Core use case: share great maps across all characters | Confirmed — apply endpoint accepts any character filename (Phase 02) |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-03-28 after Phase 02 (write-path-library) complete*
