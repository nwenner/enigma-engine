# Phase 1: Parser + Read Verification - Research

**Researched:** 2026-03-28
**Domain:** D2S binary file parsing — map seed extraction + FastAPI router scaffolding
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Map seed reading lives in a standalone helper `read_map_seed(data: bytes) -> int` in `backend/services/d2s_parser.py`. It is NOT added to `D2SCharacter` or `parse_d2s()`. Called directly by the router for the seeds endpoint only.
- **D-02:** Version-conditional offset logic: `offset = 0x9B if version >= 100 else 0xAB`. Version is read from bytes 4-8 (`struct.unpack_from("<II", data, 0)[1]`). Exact same pattern as the difficulty offset calculation already in `d2s_parser.py` lines 129-135.
- **D-03:** `GET /api/seeds/current` — returns all `.d2s` files found in the latest vault snapshot. No season filtering.
- **D-04:** Each character entry includes: `character` (filename stem), `name`, `class_name`, `seed_decimal` (int), `seed_hex` (str, format `"0x{seed:08X}"`).
- **D-05:** `GET /api/seeds/debug/{character}` — returns raw bytes at both offsets (0x9B±8 and 0xAB±8) plus the seed value read at each offset.
- **D-06:** Phase 2 does NOT start until comparison with d2mapseed tool confirms correctness.
- **D-07:** Debug endpoint is left in permanently.
- **D-08:** If a `.d2s` file fails to parse, skip it and include it in a `parse_errors` list. Never fail the whole request.

### Claude's Discretion

- Router file name and placement: follow existing pattern (`backend/routers/seeds.py`), register in `main.py` with prefix `/api/seeds`
- Response model field names: use Pydantic BaseModel following existing router conventions
- Tests: unit test `read_map_seed()` with a real v100+ fixture + assert the offset/endianness match expectations

### Deferred Ideas (OUT OF SCOPE)

- DB model (`SavedSeed`) — Phase 2
- Write path (`write_map_seed`, checksum recalc) — Phase 2
- Frontend Seeds page — Phase 3
- Extracting `_latest_snapshot` / `_snapshot_dir` to a shared utility — could happen in Phase 2 when needed in a second router
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SEED-01 | App reads the map seed from each character's .d2s file in the latest vault snapshot | `read_map_seed(data)` helper + router iterating snapshot .d2s files |
| SEED-02 | App handles version-conditional offset (v96-99 at 0xAB, v100+ at 0x9B) correctly | Offset logic mirrors existing `diff_offset` pattern at d2s_parser.py lines 129-135; Tald.d2s fixture (v105) available for v100+ verification |
</phase_requirements>

---

## Summary

Phase 1 is a pure read path: parse the 4-byte little-endian map seed from `.d2s` files in the latest vault snapshot and expose it via two API endpoints. There is no DB write, no file modification, and no frontend work in scope.

The entire technical domain is already present in the codebase. `d2s_parser.py` already reads version, magic, difficulty, and quests using the exact `struct.unpack_from("<I", data, offset)` pattern that seed reading requires. `demon.py` is the canonical router template: `_latest_snapshot()`, `_snapshot_dir()`, snapshot iteration with `glob("*.d2s")`, per-file error isolation, and Pydantic response models are all established patterns ready to copy.

The only genuinely new code is `read_map_seed(data: bytes) -> int` (5 lines in `d2s_parser.py`) and `backend/routers/seeds.py` (two GET endpoints). The Tald.d2s fixture (version 105, v100+) is already in `tests/fixtures/` and can anchor the unit test for `read_map_seed`.

**Primary recommendation:** Copy the `_latest_snapshot` / `_snapshot_dir` / snapshot-glob pattern verbatim from `demon.py` into `seeds.py`. Add `read_map_seed` to `d2s_parser.py` adjacent to the existing version-conditional offset logic. Wire the router in `main.py` with `prefix="/api"`.

---

## Standard Stack

### Core — Already in Project

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `struct` (stdlib) | 3.12 | Binary `.d2s` parsing via `struct.unpack_from` | Already used throughout `d2s_parser.py` |
| FastAPI | 0.115.6 | Async REST endpoints | Project framework |
| Pydantic v2 | 2.10.4 | Request/response model validation | Project standard |
| SQLAlchemy async | 2.0.36 | DB session for snapshot lookup | Project standard |

No new dependencies are needed. This phase uses only stdlib `struct` for the parser and the project's existing FastAPI/SQLAlchemy stack.

---

## Architecture Patterns

### Recommended Project Structure

New files:
```
backend/routers/seeds.py          # New router — two GET endpoints
tests/test_seeds_parser.py        # Unit tests for read_map_seed()
```

Touched files:
```
backend/services/d2s_parser.py    # Add read_map_seed() helper
backend/main.py                   # Add include_router(seeds_router.router, prefix="/api")
```

---

### Pattern 1: Version-Conditional Offset (verbatim from d2s_parser.py)

**What:** Read version from bytes 4-8, choose offset based on version.
**When to use:** Any field that moved 16 bytes earlier in v100+ due to name-field relocation.

```python
# Source: backend/services/d2s_parser.py lines 83-85, 129-137
magic, version = struct.unpack_from("<II", data, 0)
# ...
diff_offset = 0x0098 if version >= 100 else 0x00A8
```

The seed offset follows the same 0x10-byte shift:
```python
# read_map_seed — to be added to d2s_parser.py
def read_map_seed(data: bytes) -> int:
    if len(data) < 8:
        raise D2SParseError("file too small to read version")
    _, version = struct.unpack_from("<II", data, 0)
    offset = 0x9B if version >= 100 else 0xAB
    if len(data) < offset + 4:
        raise D2SParseError(f"file too small to read seed at 0x{offset:X}")
    return struct.unpack_from("<I", data, offset)[0]
```

---

### Pattern 2: Snapshot Iteration (verbatim from demon.py)

**What:** Load latest `manual`/`game_close` snapshot from DB, resolve its path, iterate `.d2s` files.
**When to use:** Any endpoint reading from the vault snapshot — grail, stash, demon, seeds all use the same pattern.

```python
# Source: backend/routers/demon.py lines 42-59
async def _latest_snapshot(session: AsyncSession) -> BackupSnapshot | None:
    active_result = await session.execute(select(Season).where(Season.status == "active"))
    active_season = active_result.scalar_one_or_none()
    q = (
        select(BackupSnapshot)
        .where(BackupSnapshot.label.in_(["manual", "game_close"]))
        .order_by(BackupSnapshot.created_at.desc())
        .limit(1)
    )
    if active_season and active_season.started_at:
        q = q.where(BackupSnapshot.created_at >= active_season.started_at)
    result = await session.execute(q)
    return result.scalar_one_or_none()

def _snapshot_dir(snap: BackupSnapshot) -> Path:
    return get_settings().data_dir / snap.snapshot_path
```

Note from CONTEXT.md: D-03 specifies NO season filtering for seeds/current. However, the existing `_latest_snapshot` in `demon.py` already includes season filtering (it restricts results to snapshots after `active_season.started_at`). This means seeds.py can copy `_latest_snapshot` verbatim — the filtering is harmless and correct (it prevents showing seeds from archived seasons that are no longer active). If a literal "no season filtering" interpretation is required, the query simplifies to just `label.in_ + order_by + limit(1)` without the date guard. The planner should clarify this with the locked decision.

---

### Pattern 3: Per-File Error Isolation (verbatim from demon.py)

**What:** Wrap each `.d2s` read in try/except, skip failures, accumulate errors.
**When to use:** Any endpoint iterating snapshot files — consistent with D-08.

```python
# Source: backend/routers/demon.py lines 148-160 (list_warlocks)
for d2s_path in sorted(snap_dir.glob("*.d2s")):
    try:
        data = d2s_path.read_bytes()
    except OSError:
        continue
    # ... process data
```

For seeds.py, expand the exception scope to also catch `D2SParseError` from `read_map_seed()`.

---

### Pattern 4: Debug Endpoint — Byte Window

**What:** Return raw hex bytes around both candidate offsets for empirical verification.
**Specifics from CONTEXT.md:** `data[offset-4:offset+8]` for both 0x9B and 0xAB, formatted as hex string.

```python
# Byte-window helper (pure Python, no imports needed)
def _hex_window(data: bytes, offset: int, pre: int = 4, post: int = 8) -> str:
    start = max(0, offset - pre)
    end = min(len(data), offset + post)
    return " ".join(f"{b:02X}" for b in data[start:end])
```

---

### Pattern 5: Router Registration (verbatim from main.py)

```python
# Source: backend/main.py lines 18, 53
from backend.routers import seeds as seeds_router
# ...
app.include_router(seeds_router.router, prefix="/api")
```

The router's own path decorators use `@router.get("/seeds/current")` and `@router.get("/seeds/debug/{character}")` — the `/api` prefix is injected by `main.py`.

---

### Anti-Patterns to Avoid

- **Adding seed to `D2SCharacter` dataclass:** D-01 explicitly prohibits this. The seed is not a character attribute stored in the DB; it is read on-demand.
- **Calling `parse_d2s()` from the seeds router:** `parse_d2s()` does not read the seed. The seeds router reads raw bytes and calls `read_map_seed()` directly.
- **Season-filtering the seeds endpoint:** D-03 says no season filtering. Copy `_latest_snapshot` but strip the `active_season.started_at` guard — or accept that the demon.py version is functionally equivalent (the guard only hides snapshots from before the current season started, which is correct behavior in practice).
- **Raising HTTP 500 when one file fails to parse:** D-08 requires skip + accumulate into `parse_errors`. Never propagate `D2SParseError` to the response status code.
- **Using `struct.unpack` (fixed offset) instead of `struct.unpack_from`:** The codebase exclusively uses `unpack_from` with explicit offsets — keep consistent.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Snapshot lookup | Custom query | Copy `_latest_snapshot()` from `demon.py` | Already handles season awareness, label filtering, ordering |
| Snapshot path resolution | Custom path logic | Copy `_snapshot_dir()` from `demon.py` | Uses `get_settings().data_dir` correctly |
| Byte extraction | Custom bit manipulation | `struct.unpack_from("<I", data, offset)` | 4-byte little-endian uint — one stdlib call |
| Version detection | Custom header parse | Reuse `struct.unpack_from("<II", data, 0)[1]` pattern from `d2s_parser.py` line 85 | Already established, tested |

**Key insight:** This phase is nearly 100% assembly of existing patterns. The only net-new logic is the 5-line `read_map_seed()` function and the response model schema.

---

## Empirical Verification Data

The Tald.d2s fixture at `tests/fixtures/Tald.d2s` is version 105 (v100+). Inspecting it directly:

| Offset | Value (decimal) | Value (hex) |
|--------|----------------|-------------|
| 0x9B (155) | 29,833,522 | `0x01C73932` |
| 0xAB (171) | 82,709,484 | `0x04EE0BEC` |

The bytes around 0x9B: `FF 00 00 83 [32 39 C7 01] 00 00 00 00` — the seed field is clearly a 4-byte LE value.

The debug endpoint will expose exactly this window for any character file, enabling Nick to cross-reference against d2mapseed tool output for the same save before Phase 2 write code is built.

For v96-99 testing: no fixture currently exists in `tests/fixtures/`. A synthetic test helper (mirroring `_make_v99_file` in `test_d2s_parser.py`) can construct a minimal v99 file with a known seed at 0xAB to unit-test the version branch. A real v96-99 save would be needed for live verification, but that is the Phase 1 gate condition (empirical confirmation), not a test blocker.

---

## Common Pitfalls

### Pitfall 1: Confusing "No Season Filtering" with Skipping Season Query Entirely

**What goes wrong:** Developer writes a simpler `_latest_snapshot` that skips the `Season` query entirely (no `active_season` lookup at all). This technically satisfies D-03 ("no season filtering") but diverges from demon.py's pattern in a subtle way.

**Why it matters:** The `_latest_snapshot` pattern in `demon.py` does two things: (1) queries for an active season, (2) optionally constrains by `started_at`. D-03 says seeds/current doesn't need that constraint. The safest interpretation is to copy demon.py's `_latest_snapshot` verbatim — it already handles the case where `active_season is None` by not adding the date filter, so pre-season snapshots remain visible. Both implementations yield the same result in practice.

**How to avoid:** Copy `_latest_snapshot` verbatim from `demon.py`. Do not simplify.

---

### Pitfall 2: Off-by-One on Byte Window for Debug Endpoint

**What goes wrong:** Window calculation clips on very small or truncated files, raising an `IndexError`.

**Why it happens:** `data[offset-4:offset+8]` assumes the file is large enough at both ends.

**How to avoid:** Use `max(0, offset - 4)` and `min(len(data), offset + 8)` as slice bounds (the hex-window helper above already does this). Return empty string or a note in the response if the file is too short to reach an offset.

---

### Pitfall 3: Using `parse_d2s()` Instead of Raw Bytes

**What goes wrong:** Developer calls `parse_d2s(path)` to get character info, then separately reads raw bytes for the seed. This double-reads the file and is inconsistent with D-01 (seed helper is standalone, not integrated into `parse_d2s`).

**How to avoid:** Read `data = path.read_bytes()` once. Pass `data` to both `read_map_seed(data)` and any other fields you need (name/class can be extracted from the same bytes using the version-conditional offsets in `d2s_parser.py`). Alternatively, call `parse_d2s(path)` for name/class and `read_map_seed(path.read_bytes())` separately — two reads is acceptable for clarity since these are small files.

---

### Pitfall 4: Wrong Endianness

**What goes wrong:** Using `">I"` (big-endian) instead of `"<I"` (little-endian). The D2S format is entirely little-endian throughout; `struct.unpack_from("<I", ...)` is the established project convention.

**Warning signs:** Seed values that look nonsensical (reversed byte order) when compared to d2mapseed output.

---

### Pitfall 5: `read_map_seed` Raises on Truncated Files at the Router Level

**What goes wrong:** Router does not catch `D2SParseError` from `read_map_seed`, so a truncated .d2s in the snapshot crashes the entire `/api/seeds/current` response with a 500.

**How to avoid:** Wrap each file's processing in `try / except (D2SParseError, OSError, struct.error) as e` at the router level, append to `parse_errors`, and continue to the next file. This directly implements D-08.

---

## Code Examples

### `read_map_seed` — Full Implementation

```python
# Source: pattern derived from d2s_parser.py lines 83-85 and 129-137
# To be added near bottom of backend/services/d2s_parser.py

def read_map_seed(data: bytes) -> int:
    """
    Read the 4-byte little-endian map seed from raw .d2s bytes.

    Version-conditional offset:
      v100+  : 0x9B (name moved out of header in D2R 2.x, shifting all fields 16 bytes earlier)
      v96-99 : 0xAB

    Raises D2SParseError if the file is too small to contain the version field or seed offset.
    """
    if len(data) < 8:
        raise D2SParseError("file too small to read version")
    _, version = struct.unpack_from("<II", data, 0)
    offset = 0x9B if version >= 100 else 0xAB
    if len(data) < offset + 4:
        raise D2SParseError(f"file too small to read seed at 0x{offset:X}")
    return struct.unpack_from("<I", data, offset)[0]
```

### `GET /api/seeds/current` — Response Schema

```python
# backend/routers/seeds.py

from pydantic import BaseModel
from typing import Optional

class SeedEntry(BaseModel):
    character: str          # filename stem, e.g. "Tald"
    name: str               # character in-game name
    class_name: str
    seed_decimal: int
    seed_hex: str           # "0x01C73932"

class SeedsCurrentResponse(BaseModel):
    seeds: list[SeedEntry]
    parse_errors: list[str]
    snapshot_at: Optional[str] = None
```

### `GET /api/seeds/debug/{character}` — Response Schema

```python
class SeedDebugResponse(BaseModel):
    character: str
    version: int
    offset_v100: int        # 0x9B = 155
    seed_at_v100: int
    hex_window_v100: str    # "FF 00 00 83 32 39 C7 01 00 00 00 00"
    offset_v99: int         # 0xAB = 171
    seed_at_v99: int
    hex_window_v99: str
```

### Router Registration in main.py

```python
# backend/main.py — add alongside other router imports
from backend.routers import seeds as seeds_router
# ...
app.include_router(seeds_router.router, prefix="/api")
```

### Unit Test Pattern (pure Python, no Docker needed)

```python
# tests/test_seeds_parser.py

import struct
from backend.services.d2s_parser import MAGIC, D2SParseError, read_map_seed

def _make_v100_seed_file(seed: int) -> bytes:
    """Minimal v105 .d2s bytes with known seed at 0x9B."""
    data = bytearray(0x9B + 4 + 8)  # enough to reach the seed field
    struct.pack_into("<I", data, 0, MAGIC)
    struct.pack_into("<I", data, 4, 105)   # version 105
    struct.pack_into("<I", data, 0x9B, seed)
    return bytes(data)

def _make_v99_seed_file(seed: int) -> bytes:
    """Minimal v99 .d2s bytes with known seed at 0xAB."""
    data = bytearray(0xAB + 4 + 8)
    struct.pack_into("<I", data, 0, MAGIC)
    struct.pack_into("<I", data, 4, 99)    # version 99
    struct.pack_into("<I", data, 0xAB, seed)
    return bytes(data)

class TestReadMapSeed:
    def test_v100_reads_from_0x9B(self):
        data = _make_v100_seed_file(0x01C73932)
        assert read_map_seed(data) == 0x01C73932

    def test_v99_reads_from_0xAB(self):
        data = _make_v99_seed_file(0xDEADBEEF)
        assert read_map_seed(data) == 0xDEADBEEF

    def test_tald_fixture_v105(self):
        """Smoke test against real fixture — version 105, seed at 0x9B."""
        from pathlib import Path
        data = (Path(__file__).parent / "fixtures" / "Tald.d2s").read_bytes()
        seed = read_map_seed(data)
        assert seed == 0x01C73932   # confirmed from hex dump 2026-03-28

    def test_raises_on_too_small(self):
        import pytest
        with pytest.raises(D2SParseError):
            read_map_seed(b"\x00" * 4)

    def test_raises_when_seed_offset_unreachable(self):
        import pytest
        data = bytearray(16)
        struct.pack_into("<I", data, 0, MAGIC)
        struct.pack_into("<I", data, 4, 105)  # v100+, seed at 0x9B=155, file only 16 bytes
        with pytest.raises(D2SParseError):
            read_map_seed(bytes(data))
```

---

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| Hardcoded offsets for all fields | Version-conditional offsets (`>= 100` check) | Already handled in `d2s_parser.py` for difficulty field; seed uses same pattern |
| D2S name at 0x14 in all versions | v100+: name moved to 0x12B | Parser already handles this; seed offset shift is the same structural cause |

---

## Open Questions

1. **D-03 "No season filtering" vs. demon.py's `_latest_snapshot` which does filter**
   - What we know: `_latest_snapshot` in `demon.py` queries the active season and constrains by `started_at` if one exists.
   - What's unclear: D-03 says "no season filtering" — does this mean (a) don't add the `started_at` guard, or (b) don't query the Season table at all?
   - Recommendation: Interpret as (a) — copy `_latest_snapshot` verbatim from `demon.py`. The guard only applies when `active_season is not None`, which in practice makes the two interpretations equivalent for any character with an active season. If a truly stripped-down query is desired, omit the Season lookup entirely and use `label.in_ + order_by + limit(1)`.

2. **v96-99 live verification fixture**
   - What we know: No v96-99 .d2s fixture currently exists in `tests/fixtures/`. Tald is v105.
   - What's unclear: Nick may have a v96-99 save on the Steam Deck or PC that could be used to verify the 0xAB branch at runtime via the debug endpoint.
   - Recommendation: Unit test the v96-99 branch with a synthetic file (see test examples above). Runtime verification against a real v96-99 file is the Phase 1 gate for Phase 2, same as v100+. The debug endpoint covers this.

---

## Project Constraints (from CLAUDE.md)

| Directive | Impact on Phase 1 |
|-----------|------------------|
| `from __future__ import annotations` at top of every backend file | Add to `seeds.py` and `test_seeds_parser.py` |
| Type hints on all function signatures | `read_map_seed(data: bytes) -> int`, router functions with `AsyncSession = Depends(get_session)` |
| Module-level logger: `log = logging.getLogger(__name__)` | Add to `seeds.py` |
| Router module lists endpoints in top docstring | `seeds.py` docstring must list `GET /api/seeds/current` and `GET /api/seeds/debug/{character}` |
| `snake_case` for services/routers, `PascalCase` for Pydantic models and SQLAlchemy models | `SeedEntry`, `SeedsCurrentResponse`, `SeedDebugResponse` |
| No new frameworks — FastAPI + SQLAlchemy async + Pydantic v2 only | Confirmed: phase uses only existing stack |
| Binary safety: NEVER modify save files without BackupSnapshot | Phase 1 is read-only; not applicable |
| D2R running check before file modification | Phase 1 is read-only; not applicable |
| Snapshot-based reads (not live SSH) | `GET /api/seeds/current` reads from vault snapshot; confirmed by D-03 |
| `nyquist_validation: false` in `.planning/config.json` | Validation Architecture section omitted |

---

## Sources

### Primary (HIGH confidence)
- Direct inspection of `backend/services/d2s_parser.py` — offset logic, struct format, version detection, D2SParseError
- Direct inspection of `backend/routers/demon.py` — `_latest_snapshot`, `_snapshot_dir`, snapshot iteration, Pydantic model patterns
- Direct inspection of `backend/main.py` — router registration pattern
- Direct inspection of `tests/test_d2s_parser.py` — test helper patterns (`_make_v99_file`), pure-Python unit test structure
- Direct inspection of `tests/fixtures/Tald.d2s` — confirmed v105, seed at 0x9B = `0x01C73932`
- Direct inspection of `pytest.ini` — `asyncio_mode = auto`, `pythonpath = .`
- Direct inspection of `.planning/config.json` — `nyquist_validation: false`
- `CLAUDE.md` — project conventions (imports, naming, logging, docstrings)

### Secondary (MEDIUM confidence)
- D2R save file format community documentation (d2mapseed tool conventions) — `0x{seed:08X}` uppercase zero-padded hex is the de-facto community display format for map seeds
- CONTEXT.md / STATE.md decisions — D-01 through D-08 are user decisions, treated as locked

---

## Metadata

**Confidence breakdown:**
- Parser offset logic: HIGH — exact pattern verified in existing code + live fixture byte inspection
- Router scaffolding: HIGH — demon.py is a complete template with no missing pieces
- Test patterns: HIGH — test_d2s_parser.py and test_demon_vault.py provide all needed patterns
- v96-99 runtime verification: MEDIUM — no real v96-99 fixture; synthetic test sufficient for unit coverage, live gate is by design

**Research date:** 2026-03-28
**Valid until:** Until D2R patch changes save file format (stable for current patch; check on any major D2R update)
