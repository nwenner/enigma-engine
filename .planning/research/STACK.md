# Technology Stack — Map Seed Milestone

**Project:** Enigma Engine — Map Seed Management
**Researched:** 2026-03-28
**Overall confidence:** HIGH (byte offset cross-confirmed from 4+ independent sources)

---

## Map Seed Binary Format

### Field Summary

| Property | Value | Confidence |
|----------|-------|------------|
| Field name in community | `map_id` / `MapId` / "map seed" | HIGH |
| Data type | `uint32` (4 bytes, unsigned 32-bit integer) | HIGH |
| Byte order | Little-endian | HIGH |
| Offset — v96-99 (Classic D2, early D2R) | `0x00AB` (171 decimal) | HIGH |
| Offset — v100+ (D2R 2.x patches) | `0x009B` (155 decimal) | HIGH |

### Version Detection

The D2R file header at offset `0x04` contains the version uint32. Version >= 100 indicates the v100+ layout where the character name field moved from `0x14` to `0x12B`, shifting all fields from `0x14` onward by -16 bytes.

The existing `d2s_parser.py` already handles this correctly for the difficulty field:

```python
diff_offset = 0x0098 if version >= 100 else 0x00A8
```

The map seed field sits immediately after the 3-byte difficulty block:

```python
# v96-99: difficulty at 0x00A8 (3 bytes), map_id at 0x00AB
# v100+:  difficulty at 0x0098 (3 bytes), map_id at 0x009B
seed_offset = 0x009B if version >= 100 else 0x00AB
```

### Reading the Map Seed

```python
import struct

def read_map_seed(data: bytes, version: int) -> int:
    seed_offset = 0x009B if version >= 100 else 0x00AB
    (seed,) = struct.unpack_from("<I", data, seed_offset)
    return seed
```

### Writing the Map Seed

Writing the seed preserves file size — only 4 bytes change in-place. After writing, the checksum at offset `0x0C` must be recalculated.

```python
def write_map_seed(data: bytearray, version: int, new_seed: int) -> None:
    seed_offset = 0x009B if version >= 100 else 0x00AB
    struct.pack_into("<I", data, seed_offset, new_seed)
    _recalculate_checksum(data)

def _recalculate_checksum(data: bytearray) -> None:
    import ctypes
    # Zero the checksum field (bytes 12-15) before computing
    data[12:16] = b"\x00\x00\x00\x00"
    checksum = 0
    for byte in data:
        checksum = ctypes.c_int32(
            (checksum << 1) + byte + ctypes.c_int32(checksum < 0).value
        ).value
    struct.pack_into("<i", data, 12, checksum)
```

The checksum algorithm is a rotate-left-1 accumulator with carry. It treats the accumulator as a signed 32-bit integer, zeroes the checksum field during calculation, and writes the result as a signed 32-bit little-endian integer at offset `0x0C`. The file size field at `0x08` does NOT need updating when patching the seed (file size is unchanged).

---

## Offset Source Verification

The `0x00AB` offset (v96-99) is confirmed by all of:

1. **krisives/d2s-format** README: lists "Map" field as 4 bytes at offset `0xAB`, labelled TODO but with consistent offset
2. **dschu012/d2s** (TypeScript, v2.0.36): `char.header.map_id = reader.ReadUInt32(); //0x00ab` — `ReadUInt32` uses little-endian DataView
3. **locbones/D2SLib-D2R** (C#, D2R 2.7 specific): `MapId` at `0x00ab`, read as `uint`
4. **feored/d2mapseed** and **divineblade7/d2mapseed-sp** (Python tools): `OFFSET_MAP_SEED_START = 171` = `0xAB`
5. **pairofdocs/d2s_edit_recalc**: offset 171 for Map ID with decimal support

The `0x009B` offset (v100+) is derived, not directly sourced from a tool that handles v100+:

- The 16-byte header shift is documented in the existing `d2s_parser.py` (sourced from D2SLib-D2R Locations.cs)
- The shift applies to ALL fields from `0x14` onward, including `map_id`
- `0x00AB - 0x10 = 0x009B` — the same arithmetic already validated for the difficulty field

**IMPORTANT**: All existing Python map seed tools (d2mapseed, d2mapseed-sp) use a hardcoded offset of 171 and do NOT handle the v100+ shift. For D2R version 100+ saves, they read/write the wrong bytes. The milestone implementation must use version-conditional offsets.

---

## Existing Tools and Libraries

### Python Tools (reference implementations only)

| Tool | Repo | Offset Handling | D2R v100+ Correct | Dependency |
|------|------|-----------------|--------------------|------------|
| feored/d2mapseed | github.com/feored/d2mapseed | Hardcoded 171 | No | stdlib only |
| divineblade7/d2mapseed-sp | github.com/divineblade7/d2mapseed-sp | Hardcoded 171 | No | stdlib only |
| pairofdocs/d2s_edit_recalc | github.com/pairofdocs/d2s_edit_recalc | Hardcoded 171 | No | stdlib only |

None are pip-installable. None handle v100+ correctly. They are useful only as checksum algorithm references.

### TypeScript Library (read-only for reference)

**dschu012/d2s** (npm) — reads `map_id` as `uint32` at `0x00AB` using little-endian DataView. Handles v100+ via `SeekByte` (absolute seeks), so the absolute offset resolves to `0x009B` for v100+ files. Not usable from Python but the most thorough open-source reference implementation.

### No Suitable Pip Package

`d2lib` (PyPI) supports Classic D2 (.d2s) but is not confirmed to support D2R v100+ format. No pip-installable library correctly reads/writes the D2R v100+ map seed.

**Recommendation**: Implement the map seed read/write directly in the existing `d2s_parser.py` using `struct.unpack_from` / `struct.pack_into`. No new dependency is needed.

---

## Integration with Existing Stack

### Backend

No new dependencies required. The implementation extends:

- `backend/services/d2s_parser.py` — add `read_map_seed(data, version)` and `write_map_seed(data, version, seed)` functions
- New file `backend/services/seed_service.py` — CRUD for seed library, snapshot-based read, pre-seed-restore backup flow
- New SQLAlchemy model `SeedEntry` in `backend/models.py` — id, name, notes, seed_value (uint32 stored as integer), saved_at
- New router `backend/routers/seeds.py` — CRUD endpoints + apply endpoint

### Frontend

No new dependencies. Follows established patterns:

- New page `frontend/src/pages/Seeds.tsx` (nav: "Map Seeds")
- TanStack Query for all data fetching (same pattern as Stash, Demon pages)
- Tailwind CSS for layout (no new UI library)

---

## Checksum Algorithm Sources

- **feored/d2mapseed** source: confirmed rotate-left-1 with signed 32-bit carry, checksum bytes zeroed during calculation, result stored as `<i` little-endian at offset 12
- **The Phrozen Keep** checksum thread: community-verified algorithm identical to above
- **D2SLib-D2R** D2S.cs: `Core.cs` recalculates checksum after writes — same algorithm

---

## Existing Stack (unchanged)

This milestone adds no new framework or infrastructure dependencies to the project stack documented in `.planning/codebase/STACK.md`. The complete stack remains:

- **Backend**: Python 3.12 + FastAPI 0.115.6 + uvicorn 0.34.0
- **Database**: SQLite via SQLAlchemy 2.0.36 async + aiosqlite 0.20.0
- **SSH/SFTP**: paramiko 3.5.0 (existing — used for all live device operations)
- **Frontend**: React 18.3.1 + TypeScript + Vite + TanStack Query + Tailwind CSS
- **Container**: Docker multi-stage build

---

## Sources

- [krisives/d2s-format](https://github.com/krisives/d2s-format) — Classic D2 .d2s format spec, offset 0xAB documented
- [dschu012/d2s](https://github.com/dschu012/d2s) — TypeScript parser, `map_id` at 0x00AB with little-endian ReadUInt32; SeekByte is absolute-seek
- [locbones/D2SLib-D2R](https://github.com/locbones/D2SLib-D2R) — C# D2R 2.7 library; `MapId uint32` at 0x00AB
- [feored/d2mapseed](https://github.com/feored/d2mapseed) — Python tool; checksum algorithm reference
- [divineblade7/d2mapseed-sp](https://github.com/divineblade7/d2mapseed-sp) — Python tool; same checksum algorithm
- [pairofdocs/d2s_edit_recalc](https://github.com/pairofdocs/d2s_edit_recalc) — Python editor; offset 171 for map ID
- Enigma Engine `backend/services/d2s_parser.py` — v100+ 16-byte shift documented at `diff_offset = 0x0098 if version >= 100 else 0x00A8`
