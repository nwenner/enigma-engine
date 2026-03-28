# Project Research Summary

**Project:** Enigma Engine — Map Seed Manager
**Domain:** D2R .d2s binary file patching + named library CRUD
**Researched:** 2026-03-28
**Confidence:** HIGH (offset cross-confirmed, patterns are clean extensions of existing code)

## Executive Summary

Map seed management is a well-bounded binary patching problem layered on top of infrastructure the project already has. The map seed (`MapId`) is a 32-bit little-endian unsigned integer embedded in each `.d2s` character file. Reading it requires a single `struct.unpack_from("<I", data, offset)` call; writing it requires the same in reverse followed by a checksum recalculation. The checksum algorithm is already implemented and tested in `demon_service.py`. No new dependencies, frameworks, or architectural patterns are needed — this feature is structurally identical to the Demon Vault already in production.

The single non-trivial technical risk is offset version-dependence. Every public community tool hardcodes offset `0xAB` (171), which is correct for v96–99 saves. D2R v100+ saves shift the entire post-`0x14` header region by 16 bytes, moving the map seed to `0x9B` (155). This shift is already documented and handled in `d2s_parser.py` for the difficulty field — the seed implementation must apply the same conditional. Writing to the wrong offset on a v100+ file corrupts the skill hotkey assignment block. Because the wrong-offset read still returns a plausible-looking uint32 (no exception is thrown), the bug is silent. **Empirical verification of the correct offset must happen before any write code is built.**

The recommended approach is a strict two-phase backend build followed by a frontend phase. Phase 1 implements read-only: seed extraction, the `SavedSeed` DB model, and the `GET /api/seeds/current` endpoint, ending with mandatory empirical verification against a real v100+ save file. Phase 2 adds the write path (apply seed, backup, checksum, library CRUD) only after Phase 1 is confirmed correct. Phase 3 is the frontend page. This ordering ensures the most dangerous code (binary write) is built on a verified foundation.

---

## Key Findings

### Recommended Stack

No new dependencies are required. The implementation extends existing services using only Python stdlib `struct` and SQLAlchemy. The complete project stack is unchanged: Python 3.12 + FastAPI + SQLite/SQLAlchemy async + React 18 + TanStack Query + Tailwind CSS + Docker.

**Core technologies and their roles in this feature:**
- `struct.unpack_from / struct.pack_into`: read/write the 4-byte seed field — stdlib, zero dependency
- `backend/services/d2s_parser.py`: already owns version detection logic; seed offset logic belongs here or in a thin `seed_service.py` that imports the version
- `SQLAlchemy` (`SavedSeed` model): stores the named seed library globally (no season scoping)
- `TanStack Query` + `Tailwind CSS`: frontend follows established page patterns (Seeds.tsx mirrors Demon.tsx)
- `backend/services/demon_service.py`: the checksum algorithm already implemented here is authoritative — reuse it, do not reimplement

**Version-conditional offset (critical):**
```
seed_offset = 0x009B if version >= 100 else 0x00AB
```
Version is read from offset `0x04` (uint32), same as existing parser. This is the same 16-byte shift already applied to the difficulty field at `d2s_parser.py:129–135`.

### Expected Features

**Must have (table stakes):**
- Read current seed from every character in the latest vault snapshot — nothing else works without this
- Display all characters with their current seed (decimal + hex) — players need to see seeds before saving any
- Save seed to named library entry (name required, notes optional) — the entire purpose of the feature
- Apply (restore) a saved seed to any target character — the core write operation
- Mandatory `pre_seed_restore` backup before every apply — non-negotiable per project binary safety protocol
- D2R-not-running check before apply (same `guard_mothership_write()` used by grail and demon vault)
- Delete a library entry — obvious CRUD
- New snapshot record after apply — keeps vault state consistent

**Should have (differentiators):**
- Dual display: seed shown as both decimal and hex (`0xAB39C208`) — community discusses seeds both ways
- Source character recorded on library entry — reminds player why they saved a seed
- `saved_at` timestamp on library entries — correlates seed to "that season with the great LK layout"
- Edit name/notes on an existing entry via `PATCH /api/seeds/{id}`
- Hardcore-dead character warning before apply — seeds applied to a dead HC character are silently discarded by D2R

**Defer to v2+:**
- Overwrite warning (current seed not saved in library before apply) — nice safety net, not blocking
- Manual seed entry (type in arbitrary number) — seeds should always come from real save files
- Map rendering / visual area previews — requires a separate map generation engine, completely out of scope
- Seed sharing / export / import — out of scope for a local sync tool
- Auto-push to device after seed restore — user already knows how to use Sync to Device

### Architecture Approach

Map seed management follows the Demon Vault pattern without deviation. All reads come from the local vault snapshot (no SSH needed). All writes go to the local snapshot file behind a mandatory backup and D2R-running guard, after which the user pushes to device manually via the existing Dashboard. The `_calculate_checksum` function already in `demon_service.py` should be extracted to `backend/services/d2s_utils.py` and imported by both services to avoid divergence.

**Major components:**

1. `backend/services/seed_service.py` — pure binary functions: `read_seed(data, version) -> int`, `apply_seed(data, version, seed) -> bytes`. Stateless. Raises `ValueError` if file is too short.
2. `backend/routers/seeds.py` — HTTP endpoints, snapshot resolution, D2R guard, backup orchestration, DB access. Mirrors `backend/routers/demon.py`.
3. `backend/models.py` — `SavedSeed` table: `id, name, seed_value, character_filename, notes, saved_at`. No `season_id` column (global library by design).
4. `backend/services/d2s_utils.py` — shared `_calculate_checksum(data: bytearray) -> None`. Imported by `demon_service.py` and `seed_service.py`.
5. `frontend/src/pages/Seeds.tsx` — two-panel layout: left = character list with current seeds + "Save" button per row; right = seed library with Apply/Delete/Edit controls.

**Data flows:**
- Read (no SSH): `GET /api/seeds/current` iterates `*.d2s` in latest vault snapshot, calls `read_seed()` per file
- Apply: `POST /api/seeds/{id}/apply` — load seed from DB, load target `.d2s` from snapshot, guard, backup, patch, write, trigger mothership push

### Critical Pitfalls

1. **Wrong offset for v100+ files** — hardcoded offset `171` reads into the `AssignedSkills` block on v100+ saves, not the map seed. Write silently corrupts skill hotkeys. Prevention: use `0x9B if version >= 100 else 0xAB`; verify empirically in Phase 1 before writing any write path.

2. **Invalid checksum after write** — D2R silently drops characters with a bad checksum (they simply do not appear in character select). Two failure modes: not zeroing the checksum field before calculation, and integer overflow without `& 0xFFFFFFFF` masking. Prevention: reuse `_calculate_checksum()` from `demon_service.py` exactly; write a round-trip unit test that verifies a modified file produces the same checksum D2R would expect.

3. **File length assertion missing** — seed patch is fixed-width (4 bytes replacing 4 bytes); file size must not change. Unlike demon restore, the filesize field at offset `0x08` must NOT be updated. Prevention: `assert len(patched) == len(original)` after patch, explicit comment explaining why filesize is not updated.

4. **Endianness error** — reading/writing as big-endian produces a plausible but wrong uint32 silently. Prevention: always use `struct.unpack_from("<I", ...)` / `struct.pack_into("<I", ...)`, store seed as integer in DB, display as `f"0x{seed:08X}"`.

5. **Accidental season scoping on SavedSeed model** — if a `season_id` FK is added by reflex (copying from `Character` or `GrailEntry` models), seeds disappear after season reset. Prevention: no `season_id` column; add explicit comment `# NOT season-scoped — seeds are globally valid` to the model.

---

## Implications for Roadmap

Based on combined research, the feature decomposes into three clean phases with a hard dependency gate between Phase 1 and Phase 2.

### Phase 1: Parser + Read Verification

**Rationale:** The offset question must be answered empirically before any write code is built. Phase 1 is entirely read-only and reversible — no risk to save files.

**Delivers:**
- `seed_service.py` with `read_seed(data, version)` using version-conditional offsets
- `SavedSeed` model in `models.py` (no `season_id`, explicit comment)
- `GET /api/seeds/current` endpoint returning all characters with seeds (decimal + hex)
- Router registered in `main.py`
- Empirical verification: call the endpoint against real save files, compare against `d2mapseed` tool output or hex dump — confirm `0x9B` for v100+, `0xAB` for v96-99

**Addresses:** Table stakes items 1 and 2 (read + display)

**Avoids:** Pitfall 1 (wrong offset), Pitfall 5 (endianness), Pitfall 7 (accidental season scoping)

**Gate:** Do not proceed to Phase 2 until seed values from the endpoint match known-correct values for at least one v100+ and one v96-99 file.

---

### Phase 2: Write Path + Library CRUD

**Rationale:** Write path is built only after offset is verified. Checksum reuse from `demon_service.py` eliminates the main implementation risk.

**Delivers:**
- `apply_seed(data, version, seed) -> bytes` in `seed_service.py` with `assert len(patched) == len(original)`
- Extraction of `_calculate_checksum` to `backend/services/d2s_utils.py`; `demon_service.py` refactored to import from it
- `pre_seed_restore` retention group added to `backup_manager._prune_backups()` (keep 5)
- `POST /api/seeds/save` — save current seed of a character to the library
- `GET /api/seeds/library` — list all library entries
- `DELETE /api/seeds/{id}` — remove entry
- `PATCH /api/seeds/{id}` — edit name/notes
- `POST /api/seeds/{id}/apply` — full apply flow: guard, backup, patch, write, mothership push
- Round-trip unit test: read file, apply new seed, verify checksum, verify seed reads back correctly

**Addresses:** Table stakes items 3–8 (save, apply, backup, D2R guard, CRUD, snapshot)

**Avoids:** Pitfall 2 (checksum), Pitfall 3 (filesize), Pitfall 8 (cross-character targeting)

---

### Phase 3: Frontend

**Rationale:** Backend is fully operational before UI is built; no integration surprises.

**Delivers:**
- `frontend/src/api/types.ts` additions: `CharacterSeedResponse`, `SavedSeedRecord`, `ApplySeedRequest`
- `frontend/src/api/hooks.ts` additions: `useCurrentSeeds()`, `useSeedLibrary()`, seed mutation hooks
- `frontend/src/pages/Seeds.tsx`: two-panel layout (character list + seed library), apply confirmation modal, D2R-running guard on Apply button, hardcore-dead warning
- Route `/seeds` and nav entry "Map Seeds" added to `frontend/src/App.tsx`
- UI copy: "After applying a seed, sync to your device, then restart D2R for the new map to take effect"

**Addresses:** All differentiator features (dual display, source character, timestamp, HC warning)

**Avoids:** Pitfall 4 (D2R running confusion via UI copy), Pitfall 6 (HC dead character warning)

---

### Phase Ordering Rationale

- Phase 1 before Phase 2: the write path must not be built until offset correctness is empirically confirmed — this is the hard gate. There is no safe way to test write code if the read is returning garbage.
- Phase 2 before Phase 3: all backend endpoints must exist and be correct before the frontend is built — avoids rework from API shape changes.
- Checksum extraction in Phase 2 (not Phase 1): Phase 1 is read-only so checksum is not needed yet; extracting in Phase 2 happens naturally alongside `apply_seed` implementation.
- Backup/prune additions belong in Phase 2: they are prerequisites for the write path, not the read path.

### Research Flags

Phases with well-documented patterns (no additional research needed):
- **Phase 1:** Offset derivation is fully documented in STACK.md and confirmed in `d2s_parser.py`. Read implementation is straightforward struct call.
- **Phase 2:** Checksum algorithm is already correct in `demon_service.py`. Backup and guard patterns are established. No novel integration.
- **Phase 3:** Frontend follows the Demon.tsx pattern exactly. TanStack Query hooks and two-panel layout are already established conventions in this codebase.

No phases require a `/gsd:research-phase` call during planning. All technical questions are resolved.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | No new dependencies. All tools are stdlib or existing project libraries. Cross-confirmed across 4+ sources. |
| Features | HIGH | Features are directly analogous to the working Demon Vault. Scope is tightly bounded. Anti-features clearly identified. |
| Architecture | HIGH | Demon Vault is the exact template. Component boundaries, data flows, and endpoint shapes are fully specified. |
| Pitfalls | HIGH | Top pitfalls are well-documented. Most are already solved in existing code. Empirical gate in Phase 1 covers the main remaining uncertainty. |

**Overall confidence:** HIGH

### Gaps to Address

- **v100+ offset empirical verification:** The `0x9B` offset for v100+ is derived from the known 16-byte header shift rather than directly observed in a published tool that explicitly handles v100+. The derivation is sound (same arithmetic already validated for the difficulty field), but must be confirmed by reading a real v100+ save file before Phase 2 begins. This is the only open question in the research.

- **Checksum function merge:** `demon_service.py::_calculate_checksum` is currently private to that module. The refactor to `d2s_utils.py` is straightforward but requires updating `demon_service.py` imports and re-running tests. Plan for this at the start of Phase 2, not as an afterthought.

---

## Sources

### Primary (HIGH confidence)
- Enigma Engine `backend/services/d2s_parser.py` — v100+ 16-byte shift confirmed at lines 129–135; `diff_offset = 0x0098 if version >= 100 else 0x00A8`
- Enigma Engine `backend/services/demon_service.py` — `_calculate_checksum` reference implementation; checksum algorithm verified correct in production
- [WalterCouto/D2CE d2s_File_Format.md](https://github.com/WalterCouto/D2CE/blob/main/d2s_File_Format.md) — Map ID field at byte 171 for versions 92+
- [locbones/D2SLib-D2R](https://github.com/locbones/D2SLib-D2R) — C# D2R 2.7 library; `MapId uint32` at `0x00AB`
- [dschu012/d2s](https://github.com/dschu012/d2s) — TypeScript parser; `map_id` at `0x00AB` with little-endian ReadUInt32

### Secondary (MEDIUM confidence)
- [feored/d2mapseed](https://github.com/feored/d2mapseed) — Python tool; `OFFSET_MAP_SEED_START = 171`; checksum algorithm reference (uses `ctypes` variant — correct but `& 0xFFFFFFFF` preferred)
- [divineblade7/d2mapseed-sp](https://github.com/divineblade7/d2mapseed-sp) — D2R single-player fork; same offset and checksum
- [pairofdocs/d2s_edit_recalc](https://github.com/pairofdocs/d2s_edit_recalc) — Python editor; offset 171 documented
- [noobient.com 2025-11-21](https://noobient.com/2025/11/21/finding-the-map-seed-in-diablo-ii-resurrected/) — confirmed for D2R specifically

### Tertiary (LOW confidence)
- [krisives/d2s-format](https://github.com/krisives/d2s-format) — Classic D2 spec; offset `0xAB` documented as TODO but offset is consistent
- Community discussion threads (diablo2.io, d2jsp) — usage patterns only, no technical detail

---
*Research completed: 2026-03-28*
*Ready for roadmap: yes*
