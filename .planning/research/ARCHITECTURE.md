# Architecture Patterns: Map Seed Integration

**Domain:** Map seed read/write for an existing FastAPI + React D2R save manager
**Researched:** 2026-03-28
**Overall confidence:** HIGH (offset verified across 4 independent tools; integration patterns drawn directly from demon_service.py and demon router as the closest analog)

---

## Recommended Architecture

Map seed management follows the **Demon Vault pattern** exactly: read from local vault snapshot, write to local snapshot file with mandatory pre-write backup, user pushes to device manually afterward. No new architectural patterns are needed — this is a clean extension of existing infrastructure.

### Component Boundaries

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| `backend/services/seed_service.py` | Pure binary: read seed from .d2s bytes, write seed to .d2s bytes, recalculate checksum | Nothing (stateless pure functions) |
| `backend/routers/seeds.py` | HTTP endpoints, Pydantic models, snapshot resolution, D2R guard, backup orchestration | `seed_service`, `backup_manager`, `models`, `auto_sync` |
| `backend/models.py` — `SavedSeed` table | Persist named seed library entries | SQLAlchemy, referenced by router |
| `backend/database.py` — `init_db()` | CREATE TABLE migration for `saved_seeds` | SQLAlchemy engine |
| `backend/main.py` | Register `seeds_router` at `/api` | FastAPI app |
| `frontend/src/pages/Seeds.tsx` | Map Seeds page — list characters/seeds, save to library, apply from library | API hooks |
| `frontend/src/api/hooks.ts` | TanStack Query hooks for all seed endpoints | axios client |
| `frontend/src/api/types.ts` | TypeScript types for all seed API responses | used by hooks + page |
| `frontend/src/App.tsx` | Add `/seeds` route + NAV_ITEMS entry | React Router |

---

## Map Seed Location in .d2s

**Offset:** 171 (0xAB), 4 bytes, little-endian uint32

**Confidence:** HIGH — confirmed at offset 171 by four independent tools:
- [feored/d2mapseed](https://github.com/feored/d2mapseed) (`OFFSET_MAP_SEED_START = 171`)
- [pairofdocs/d2s_edit_recalc](https://github.com/pairofdocs/d2s_edit_recalc) (documents "171, <value>, decimal")
- [WalterCouto/D2CE d2s_File_Format.md](https://github.com/WalterCouto/D2CE/blob/main/d2s_File_Format.md) (Map ID at byte 171 for versions 92+)
- [noobient.com 2025-11-21](https://noobient.com/2025/11/21/finding-the-map-seed-in-diablo-ii-resurrected/) (confirmed for D2R)

**Version note:** The existing `d2s_parser.py` shows that v100+ shifts some fields by -0x10 (difficulty block moves from 0x00A8 to 0x0098). Offset 171 (0xAB) is in a different region of the fixed header and all tools report it as stable across versions 92+ through D2R v100+. **However, this MUST be empirically verified in Phase 1 by reading offset 171 from a real v100+ .d2s file and comparing with the in-game displayed seed (readable via maphack or tools like d2mapseed).** Do not ship Phase 2 without that verification.

**Read:**
```python
import struct
seed = struct.unpack_from("<I", d2s_data, 171)[0]
```

**Write:** patch bytes at offset 171, then recalculate checksum (same rotate-left-1 algorithm already implemented in `demon_service.py::_calculate_checksum`). The filesize field at offset 8 does NOT change (seed patch is same size).

---

## New DB Model: `SavedSeed`

Add to `backend/models.py`. The table is global (not season-scoped) per the PROJECT.md decision.

```python
class SavedSeed(Base):
    __tablename__ = "saved_seeds"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    name         = Column(String, nullable=False)        # user label, e.g. "Great Chaos layout"
    seed_value   = Column(Integer, nullable=False)       # uint32 stored as signed int (SQLite ok)
    character_filename = Column(String, nullable=False)  # source file, e.g. "Niko.d2s"
    notes        = Column(String, nullable=True)
    saved_at     = Column(DateTime, default=datetime.utcnow, nullable=False)
```

**Migration** — add to `init_db()` in `backend/database.py` using the existing try/except ALTER TABLE pattern:
```python
# saved_seeds table is created by Base.metadata.create_all on new installs.
# No ALTER TABLE needed — new table, not a column addition to an existing table.
```
`Base.metadata.create_all` handles new tables automatically on startup. No manual migration SQL needed for this table.

---

## New API Endpoints

All under `backend/routers/seeds.py`, registered in `backend/main.py` as `app.include_router(seeds_router.router, prefix="/api")`.

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/seeds/current` | Read current seed from every .d2s in the latest vault snapshot. Returns list of `{filename, name, seed}` — one per character. No SSH needed. |
| `POST` | `/api/seeds/save` | Save a seed value to the named library. Body: `{character, name, notes?}`. Reads seed from snapshot, creates DB record. |
| `GET` | `/api/seeds/library` | List all saved seeds from DB. Returns list of `SavedSeedRecord`. |
| `DELETE` | `/api/seeds/{id}` | Delete a saved seed from the library. |
| `POST` | `/api/seeds/{id}/apply` | Apply a saved seed to a character. Body: `{character}`. Creates `pre_seed_restore` backup, patches .d2s in snapshot, triggers mothership push. |

### Pydantic Models

```python
class CharacterSeedResponse(BaseModel):
    filename: str          # "Niko.d2s"
    name: str              # "Niko"
    seed: int              # uint32 as Python int
    seed_hex: str          # "0x08939C62" — display convenience

class SaveSeedRequest(BaseModel):
    character: str         # filename without .d2s
    name: str
    notes: Optional[str] = None

class SavedSeedRecord(BaseModel):
    id: int
    name: str
    seed_value: int
    seed_hex: str
    character_filename: str
    notes: Optional[str]
    saved_at: str          # ISO datetime

class ApplySeedRequest(BaseModel):
    character: str         # target character, filename without .d2s
```

---

## Apply-Seed Integration with Backup/Snapshot System

The apply flow follows `demon_router.restore_demon` exactly. Steps in order:

1. Resolve latest `manual`/`game_close` snapshot (season-aware, same `_latest_snapshot()` helper pattern).
2. Load the target character's `.d2s` from the snapshot directory.
3. Call `guard_mothership_write(session)` — checks D2R is not running on either device.
4. Call `create_local_snapshot(session, snap, label="pre_seed_restore")` — copies the snapshot directory before any mutation.
5. Call `seed_service.apply_seed(d2s_data, seed_value)` — returns patched bytes with valid checksum.
6. Write patched bytes back to the `.d2s` file in the snapshot directory.
7. Call `trigger_mothership_push(background_tasks, session)` — enqueues push to connected devices.

**Retention for `pre_seed_restore`:** Add to `_prune_backups()` in `backup_manager.py`:
```python
elif label == "pre_seed_restore":
    # use label.startswith("pre_seed") or exact match; keep 5
    keep = 5
```

**No auto-push to device:** `trigger_mothership_push` handles the mothership state update. The user then uses the existing "Sync to Device" button on the Dashboard to push to PC or Deck — consistent with demon restore behavior.

---

## `seed_service.py` Function Signatures

```python
SEED_OFFSET = 171  # verified across 4 sources; empirical check required in Phase 1

def read_seed(d2s_data: bytes) -> int:
    """Return the 32-bit map seed as a Python int. Raises ValueError if file too short."""

def apply_seed(d2s_data: bytes, seed: int) -> bytes:
    """
    Patch seed into d2s_data at SEED_OFFSET.
    Recalculates checksum (offset 12) using the existing rotate-left-1 algorithm.
    Does NOT change filesize (offset 8) — patch is same size as original.
    Returns new bytes.
    """
```

The `_calculate_checksum` function from `demon_service.py` should be extracted to a shared utility (e.g., `backend/services/d2s_utils.py`) rather than duplicated. Both demon restore and seed apply need it.

---

## d2s_parser.py Extension

`parse_d2s()` currently returns a `D2SCharacter` dataclass. Two options:

**Option A (preferred):** Add an optional `seed` field to `D2SCharacter` and parse it in `parse_d2s()`.
```python
@dataclass
class D2SCharacter:
    ...
    seed: int = 0   # map seed, uint32 at offset 171
```
This makes seed available everywhere `parse_d2s` is called (sync hooks, character list). The `BackupSnapshot.characters` JSON column would automatically carry seed values after this change.

**Option B:** Keep `parse_d2s` unchanged; `seed_service.read_seed()` reads the raw bytes independently.

Option A is cleaner and makes seeds visible in character tracking at zero extra cost. Option B is safer if empirical verification reveals offset 171 is wrong — it isolates the risk. **Recommend Option B for Phase 1 (verify first), then promote to Option A in Phase 2 after offset is confirmed.**

---

## Frontend Page: `Seeds.tsx`

**Route:** `/seeds`
**Nav entry:** `{ to: "/seeds", label: "Map Seeds", icon: "🗺️" }` — add to `NAV_ITEMS` in `App.tsx`

**Page layout (two-panel, same as Demon.tsx pattern):**

**Panel 1 — Current Seeds (read-only)**
- Calls `useCurrentSeeds()` hook → `GET /api/seeds/current`
- Table: character name | seed hex value | "Save to Library" button per row
- Clicking "Save to Library" opens an inline form: name field + optional notes
- Shows snapshot timestamp (same `snapshot_at` pattern as Demon page)

**Panel 2 — Seed Library**
- Calls `useSeedLibrary()` hook → `GET /api/seeds/library`
- Card list: seed name | original character | hex value | notes | "Apply" button | "Delete" button
- "Apply" opens a character selector dropdown (populated from `useCurrentSeeds()` data) + confirm dialog
- Success/error inline messages (same `setMsg`/`setErr` pattern from Demon.tsx)

**D2R running guard:** Check `usePreflight()` data; disable Apply button with tooltip if D2R is running on either machine (same `d2rRunning` check as Demon.tsx line 41).

---

## Data Flow: Seed Read (No SSH)

```
GET /api/seeds/current
  → seeds router: resolve latest snapshot (season-aware)
  → iterate *.d2s files in snapshot directory
  → seed_service.read_seed(file_bytes) per file
  → return list[CharacterSeedResponse]
```

Entirely local — no SSH, no device connection needed. Fast, safe.

## Data Flow: Seed Apply

```
POST /api/seeds/{id}/apply  body={character}
  → seeds router: load SavedSeed from DB
  → resolve latest snapshot
  → load target .d2s bytes
  → guard_mothership_write(session)       # D2R running check
  → create_local_snapshot(..., "pre_seed_restore")  # mandatory backup
  → seed_service.apply_seed(bytes, seed) # patch + checksum
  → write patched bytes to snapshot file
  → trigger_mothership_push(...)          # update mothership state
  → return {success, seed_hex, character}
```

---

## Build Order

Backend must be built and verified before frontend. Seed service logic must be confirmed empirically before the apply endpoint goes in.

### Phase 1: Parser + Read (Backend Only)
1. Create `backend/services/seed_service.py` with `read_seed()` only
2. Add `SavedSeed` model to `backend/models.py`
3. Add `GET /api/seeds/current` endpoint to `backend/routers/seeds.py`
4. Register router in `backend/main.py`
5. **Empirical verification**: call the endpoint, compare returned seeds against values from `d2mapseed` tool or in-game display — confirm offset 171 is correct for both v96-99 and v100+ files
6. If offset wrong: correct `SEED_OFFSET` before proceeding to Phase 2

### Phase 2: Write + Library (Backend)
1. Add `apply_seed()` to `seed_service.py` (only after Phase 1 offset confirmed)
2. Extract `_calculate_checksum` to shared `d2s_utils.py` (refactor demon_service.py to import from it)
3. Add `pre_seed_restore` retention group to `backup_manager._prune_backups()`
4. Add `POST /api/seeds/save`, `GET /api/seeds/library`, `DELETE /api/seeds/{id}`, `POST /api/seeds/{id}/apply`
5. Run full test suite

### Phase 3: Frontend
1. Add TypeScript types to `frontend/src/api/types.ts`
2. Add hooks to `frontend/src/api/hooks.ts`
3. Create `frontend/src/pages/Seeds.tsx`
4. Add route and nav entry to `frontend/src/App.tsx`

---

## Anti-Patterns to Avoid

### Apply Seed Without Pre-Write Backup
**What goes wrong:** Seed patch corrupts .d2s; no recovery path.
**Prevention:** `create_local_snapshot(..., "pre_seed_restore")` is mandatory before any `.write_bytes()` call. Mirrors the demon restore and grail service patterns.

### Skipping D2R Running Check
**What goes wrong:** Game reads the file mid-write; save corruption.
**Prevention:** `guard_mothership_write(session)` call before any file modification (already established in demon restore flow).

### Assuming Offset 171 Without Verification
**What goes wrong:** Reads garbage data; applies wrong seed silently.
**Prevention:** Phase 1 ends with a mandatory empirical check comparing parsed values against a known tool (d2mapseed or d2mapseed-sp). Do not write Phase 2 code until read is confirmed correct.

### Duplicating `_calculate_checksum`
**What goes wrong:** Two implementations drift; one gets a bug fix the other misses.
**Prevention:** Extract to `backend/services/d2s_utils.py` in Phase 2 and import in both `demon_service.py` and `seed_service.py`.

### Making Seeds Season-Scoped
**What goes wrong:** A great farming map disappears after season reset; defeats the purpose.
**Prevention:** `SavedSeed` has no `season_id` column. Per PROJECT.md decision: "A good map layout is valuable across seasons."

---

## Key Integration Points (Summary)

| Concern | Solution | Existing Analogue |
|---------|----------|-------------------|
| Read from vault snapshot | `fetch_stash_local()` pattern — iterate snapshot dir, read files locally | `stash_service.fetch_stash_local()` |
| Mandatory pre-write backup | `create_local_snapshot(session, snap, "pre_seed_restore")` | `grail_service.py`, `demon router` |
| D2R running guard | `guard_mothership_write(session)` | `demon router` line 333 |
| Checksum recalculation | Shared `d2s_utils._calculate_checksum()` | `demon_service._calculate_checksum()` |
| Retention pruning | `label == "pre_seed_restore"`, keep 5 | `pre_grail_*`, `pre_vault_*` groups |
| Post-apply device push | `trigger_mothership_push(background_tasks, session)` | `demon router` line 345 |
| Season-aware snapshot query | `BackupSnapshot.created_at >= active_season.started_at` filter | `demon router::_latest_snapshot()` |
| Frontend state refresh | `queryClient.invalidateQueries()` in mutation `onSuccess` | All existing mutation hooks |

---

## Sources

- [feored/d2mapseed — Python map seed tool (OFFSET_MAP_SEED_START = 171)](https://github.com/feored/d2mapseed)
- [pairofdocs/d2s_edit_recalc — D2 LoD and D2R save editor (offset 171 documented)](https://github.com/pairofdocs/d2s_edit_recalc)
- [WalterCouto/D2CE d2s_File_Format.md — Map ID at byte 171 for versions 92+](https://github.com/WalterCouto/D2CE/blob/main/d2s_File_Format.md)
- [noobient.com — Finding the Map Seed in D2R (2025-11-21)](https://noobient.com/2025/11/21/finding-the-map-seed-in-diablo-ii-resurrected/)
- [divineblade7/d2mapseed-sp — D2R single-player map seed tool](https://github.com/divineblade7/d2mapseed-sp)
- Existing codebase: `backend/services/demon_service.py`, `backend/routers/demon.py`, `backend/services/backup_manager.py`, `backend/services/d2s_parser.py`
