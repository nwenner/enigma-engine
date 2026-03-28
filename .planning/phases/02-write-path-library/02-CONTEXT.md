# Phase 2: Write Path + Library - Context

**Gathered:** 2026-03-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 2 delivers the full write path and seed library (API only — no frontend):
1. `SavedSeed` ORM model in `backend/models.py`
2. `write_map_seed(data: bytes, seed: int) -> bytes` helper in `backend/services/d2s_parser.py`
3. Shared checksum utility extracted from `demon_service.py` to `backend/services/d2s_utils.py`
4. CRUD API for seed library: save, list, edit name/notes, delete
5. Apply endpoint: `POST /api/seeds/{id}/apply` — backup → patch .d2s in-place → trigger push
6. All four safety gates: pre_seed_restore backup, D2R running check, checksum recalc, file size assertion

No frontend in this phase. Phase 3 adds the Seeds page.

</domain>

<decisions>
## Implementation Decisions

### SavedSeed Model

- **D-01:** `SavedSeed` stores: `id`, `seed_value` (int), `name` (str), `notes` (str, nullable), `source_character` (str, e.g. "Tald"), `source_class` (str, e.g. "Warlock"), `source_version` (int, e.g. 105), `saved_at` (datetime). No FK to Characters table — just a snapshot string for display context.
- **D-02:** No `season_id` FK — seeds are globally valid across seasons. Do NOT add any season relationship.
- **D-03:** Duplicate seed values are allowed — same integer can be saved multiple times under different names. No unique constraint on `seed_value`.

### Library CRUD API

- **D-04:** Save endpoint: `POST /api/seeds/library` — body `{ character: str, name: str, notes: str | null }`. Reads seed from latest snapshot for the given character, stores with source metadata. Returns saved entry.
- **D-05:** List endpoint: `GET /api/seeds/library` — returns all entries, newest first. No pagination needed for v1.
- **D-06:** Edit endpoint: `PATCH /api/seeds/library/{id}` — body `{ name: str, notes: str | null }`. Updates name and notes only — seed value and source metadata are immutable once saved.
- **D-07:** Delete endpoint: `DELETE /api/seeds/library/{id}` — removes entry, returns 204.

### Apply Endpoint

- **D-08:** Apply: `POST /api/seeds/{id}/apply` — body `{ character: str }` (target character filename stem). Matches the demon restore pattern exactly.
- **D-09:** Success response: `{ success: true, seed_name: str, character: str, seed_hex: str }` — enough for a UI toast like "Applied 'Act1 Dec' to Tald (0x7FB203B4)".
- **D-10:** Error cases with distinct HTTP responses:
  - `409` — D2R is running (`guard_mothership_write()` handles this automatically)
  - `404` — Seed ID not found in library
  - `404` — No snapshot available (no manual/game_close snapshot exists)
  - `404` — Target character `.d2s` not found in latest snapshot

### Write Safety (Binary Protocol)

- **D-11:** Apply operation sequence: (1) call `guard_mothership_write(session)` — raises 409 if D2R running, (2) `_create_local_backup_snapshot(session, snap, "pre_seed_restore")` — copies snapshot dir, (3) patch `.d2s` in-place using `write_map_seed()`, (4) assert `len(patched) == len(original)` — seed patch must NOT change file size, (5) `trigger_mothership_push(background_tasks, session)`.
- **D-12:** Post-apply snapshot: in-place write only (same as demon/grail). The existing `BackupSnapshot` record remains "latest" — it now contains the patched file. No new snapshot record needed after apply.
- **D-13:** `write_map_seed(data: bytes, seed: int) -> bytes` — version-conditional offset (same as `read_map_seed`), returns new bytes with seed patched and checksum recalculated. File size must not change. Raises `D2SParseError` on truncated file.

### Checksum / Utility Extraction

- **D-14:** Extract `_calculate_checksum` from `backend/services/demon_service.py` into a new `backend/services/d2s_utils.py`. Both `demon_service.py` and the new `seed_service.py` import from it. This is the shared checksum utility STATE.md identified.
- **D-15:** `_create_local_backup_snapshot()` already exists in `grail_service.py` — copy it into `seed_service.py` (same as demon/grail pattern of each service having its own copy). Do NOT refactor to a shared util — that's a future cleanup.

### Service File

- **D-16:** Create `backend/services/seed_service.py` — contains `write_map_seed()` helper (if not kept in `d2s_parser.py`), `_create_local_backup_snapshot()` copy, and `apply_seed_to_snapshot()` orchestration function. Router calls the service, not raw file ops.

### Claude's Discretion

- Router file name: `backend/routers/seeds.py` already exists (Phase 1). Add new endpoints there — don't create a second seeds router.
- Test patterns: follow `tests/test_seeds_parser.py` and `tests/test_demon_vault.py` for structure.
- `_latest_snapshot()` and `_snapshot_dir()` already in `seeds.py` (copied from demon.py in Phase 1) — reuse directly.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Write pattern template (most important)
- `backend/routers/demon.py` — exact restore pattern: guard_mothership_write → backup → patch → write_bytes → trigger_mothership_push
- `backend/services/demon_service.py` — `restore_demon_to_d2s()` (in-place patch + checksum recalc), `_calculate_checksum()` (to extract)
- `backend/services/grail_service.py` — `_create_local_backup_snapshot()` (pre_* backup pattern)

### Phase 1 foundation
- `backend/routers/seeds.py` — existing Phase 1 router (add new endpoints here, don't create a second file)
- `backend/services/d2s_parser.py` — `read_map_seed()`, version offset logic, `D2SParseError`

### Model template
- `backend/models.py` — `BoundDemon` class (exact template shape for `SavedSeed` model)

### Project constraints
- `CLAUDE.md` — project conventions (imports, naming, logging, binary safety rule)
- `.planning/STATE.md` — key decisions (no season_id, no auto-push, phase gate details)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `guard_mothership_write(session)` in `auto_sync.py` — call this first in apply endpoint; handles D2R check + 409
- `trigger_mothership_push(background_tasks, session)` in `auto_sync.py` — call this after write; handles auto-sync push
- `_create_local_backup_snapshot(session, snap, label)` in `grail_service.py` — copy this into `seed_service.py`
- `_calculate_checksum(data: bytes) -> int` in `demon_service.py` — extract to `d2s_utils.py`
- `_latest_snapshot(session)` and `_snapshot_dir(snap)` already in `seeds.py` (Phase 1)

### Established Patterns
- Write flow: `guard_mothership_write` → local backup → patch file → `.write_bytes()` → `trigger_mothership_push` — every write endpoint follows this exactly
- File size assertion after patch: `assert len(patched) == len(original)` — seed patch is a fixed 4-byte replacement, size must not change
- Backup label convention: `pre_{operation}` — `pre_seed_restore` matches `pre_grail_deposit`, `pre_grail_retrieve`

### Integration Points
- `backend/main.py` — no changes needed; seeds router already registered
- `backend/models.py` — add `SavedSeed` class after `BoundDemon`
- `backend/services/d2s_utils.py` — new file; `demon_service.py` and `seed_service.py` import from it

</code_context>

<specifics>
## Specific Ideas

- `seed_hex` format in library responses: `f"0x{seed_value:08X}"` — same as Phase 1 seeds endpoint
- `source_version` field: store the raw version int (e.g. 105), not a label like "v100+" — more precise
- Apply confirmation toast text model: `"Applied '{seed_name}' to {character} ({seed_hex})"` — keep the response shape `{ success, seed_name, character, seed_hex }` to enable this

</specifics>

<deferred>
## Deferred Ideas

- Extracting `_latest_snapshot` / `_snapshot_dir` / `_create_local_backup_snapshot` to a shared utility — future cleanup
- Pagination on `GET /api/seeds/library` — v1 library is small, not needed yet
- Auto-push to device after seed restore — SEED-V2-01, explicitly out of v1 scope
- Seed sharing (export/import) — SEED-V2-02

</deferred>

---

*Phase: 02-write-path-library*
*Context gathered: 2026-03-28*
