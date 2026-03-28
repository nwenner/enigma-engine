# Phase 1: Parser + Read Verification - Context

**Gathered:** 2026-03-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 1 is **read-only**. It delivers:
1. A `read_map_seed(data: bytes) -> int` helper in `d2s_parser.py`
2. A `GET /api/seeds/current` endpoint returning all characters + their seeds (hex + decimal)
3. A `GET /api/seeds/debug/{character}` endpoint returning raw bytes at both candidate offsets for empirical verification

No write code, no DB model, no frontend. The only deliverable beyond the parser function is the API surface needed to verify the offset is correct before Phase 2 is built.

</domain>

<decisions>
## Implementation Decisions

### Parser Integration

- **D-01:** Map seed reading lives in a standalone helper `read_map_seed(data: bytes) -> int` in `backend/services/d2s_parser.py`. It is NOT added to `D2SCharacter` or `parse_d2s()`. Called directly by the router for the seeds endpoint only.
- **D-02:** Version-conditional offset logic: `offset = 0x9B if version >= 100 else 0xAB`. Version is read from bytes 4-8 (`struct.unpack_from("<II", data, 0)[1]`). Exact same pattern as the difficulty offset calculation already in `d2s_parser.py` lines 129-135.

### API Endpoints

- **D-03:** `GET /api/seeds/current` — returns all `.d2s` files found in the latest vault snapshot. No season filtering — this is a read-only endpoint and all snapshot characters are valid to show.
- **D-04:** Each character entry in the response includes: `character` (filename stem), `name`, `class_name`, `seed_decimal` (int), `seed_hex` (str, format `"0x{seed:08X}"`).
- **D-05:** `GET /api/seeds/debug/{character}` — returns raw bytes at both offsets (0x9B±8 and 0xAB±8) plus the seed value read at each offset. Intended for empirical verification before Phase 2. Can be a developer endpoint, no auth needed.

### Verification Gate

- **D-06:** Empirical verification uses the debug endpoint. After Phase 1 ships, Nick reads `GET /api/seeds/debug/{character}` output and compares the seed at `0x9B` against d2mapseed tool output for the same character. Phase 2 does NOT start until this comparison confirms correctness.
- **D-07:** The debug endpoint is left in permanently (not removed after verification) — it's a useful diagnostic tool.

### Error Handling

- **D-08:** If a `.d2s` file in the snapshot fails to parse (corrupt, too small, etc.), skip that character and include it in a `parse_errors` list in the response. Never fail the whole request because one character is broken.

### Claude's Discretion

- Router file name and placement: follow existing pattern (`backend/routers/seeds.py`), register in `main.py` with prefix `/api/seeds`
- Response model field names: use Pydantic BaseModel following existing router conventions
- Tests: unit test `read_map_seed()` with a real v100+ fixture + assert the offset/endianness match expectations

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Parser patterns
- `backend/services/d2s_parser.py` — version detection, conditional offset logic (lines 80-135), `D2SParseError`

### Router patterns (exact template)
- `backend/routers/demon.py` — `_latest_snapshot()`, `_snapshot_dir()`, iterating .d2s files from snapshot dir, error handling, Pydantic response models

### App wiring
- `backend/main.py` — how routers are registered with `app.include_router()`

### Project constraints
- `CLAUDE.md` — project-specific guidelines

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_latest_snapshot(session)` in `demon.py:42` — copy this helper into `seeds.py` (or extract to shared util)
- `_snapshot_dir(snap)` in `demon.py:59` — same
- `struct.unpack_from("<II", data, 0)` pattern for reading magic+version — already in `d2s_parser.py`
- `D2SParseError` exception class — use for parse failures in `read_map_seed()`

### Established Patterns
- All routers use `Depends(get_session)` for async DB session
- Response models are inline Pydantic `BaseModel` subclasses defined in the router file
- Snapshot iteration: `glob("*.d2s")` on `_snapshot_dir(snap)`

### Integration Points
- `backend/main.py` — add `app.include_router(seeds.router, prefix="/api")`
- `backend/services/d2s_parser.py` — add `read_map_seed(data: bytes) -> int` near the bottom

</code_context>

<specifics>
## Specific Ideas

- Debug endpoint should show window of bytes: `data[offset-4:offset+8]` for both offsets, formatted as hex string — makes it easy to eyeball in a browser
- `seed_hex` format: `f"0x{seed:08X}"` — uppercase hex, zero-padded to 8 digits, matches community tool conventions

</specifics>

<deferred>
## Deferred Ideas

- DB model (`SavedSeed`) — Phase 2
- Write path (`write_map_seed`, checksum recalc) — Phase 2
- Frontend Seeds page — Phase 3
- Extracting `_latest_snapshot` / `_snapshot_dir` to a shared utility — could happen in Phase 2 when it's needed in a second router

</deferred>

---

*Phase: 01-parser-read-verification*
*Context gathered: 2026-03-28*
