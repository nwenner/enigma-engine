# Domain Pitfalls: D2R Map Seed Binary Patching

**Domain:** Diablo 2 Resurrected .d2s save file — map seed read/write
**Researched:** 2026-03-28
**Scope:** Pitfalls specific to reading and writing the `MapId` field in .d2s files

---

## Critical Pitfalls

Mistakes in this category cause silent data corruption or character file destruction.

---

### Pitfall 1: Wrong Offset for v100+ Files

**What goes wrong:**
The map seed (`MapId`) sits immediately after the 3-byte difficulty/location block. That block moves 16 bytes earlier in v100+ files because the 16-byte character name field was removed from the early header area (name moved to `0x12B`). As a result, the map seed is at a different offset depending on file version:

| Version | Difficulty block | Map seed offset |
|---------|-----------------|-----------------|
| v96–99  | `0x00A8`        | `0x00AB` = 171  |
| v100+   | `0x0098`        | `0x009B` = 155  |

Community tools that hardcode offset `171` (e.g., `feored/d2mapseed`, `divineblade7/d2mapseed-sp`) were written for pre-v100 files and apply this offset to all versions without checking. On a v100+ file — which is every D2R file after the 2.x patch wave — offset 171 falls inside the `AssignedSkills` block, not the map seed. Reading from that offset produces a garbage value that looks like a plausible uint32. Writing to it silently corrupts the skill hotkey assignments.

**Why it happens:**
Public documentation (D2CE `d2s_File_Format.md`, D2SLib-D2R) records the v92+ canonical offset as `0xAB`. That is correct for v96–99. Tools implemented against the v96–99 spec do not account for the 16-byte shift introduced with v100. The shift is documented in the existing codebase at `d2s_parser.py` lines 129–135, which already handles it correctly for the difficulty block.

**Consequences:**
- Read: Returns wrong value; seed library stores garbage data silently
- Write: Overwrites skill hotkey bytes with seed bytes; character loads with corrupted skill assignments; no in-game error shown until the character tries to cast a skill

**Prevention:**
- Read the version field at offset `0x04` first
- Apply the same conditional already used for the difficulty offset: `seed_offset = 0x009B if version >= 100 else 0x00AB`
- Extend `d2s_parser.py` rather than hardcoding a fixed offset in a new service

**Detection:**
- Warning sign: Parsed seed value is very large or obviously wrong relative to the file's known origin
- Warning sign: Character loses skill hotkeys after a seed apply operation
- Unit test: Parse seed from a known v100+ fixture, verify against hex-dumped ground truth

**Phase:** Address in Phase 1 (seed read implementation). Must be resolved before any write path is built.

---

### Pitfall 2: Incorrect Checksum After Write

**What goes wrong:**
D2R validates the .d2s checksum on load. An invalid checksum causes the character to not appear in the character selection screen — the file is silently rejected without an error dialog. The checksum algorithm is a rotate-left-and-add over all bytes, with the checksum field (`0x0C`–`0x0F`) zeroed before the calculation.

Two common implementation errors:

1. **Not zeroing the checksum field first.** The existing value at `0x0C` must be set to zero before iterating. If the old checksum bytes remain, the result is wrong regardless of the byte order.

2. **Signed vs. unsigned integer overflow.** Python integers do not overflow. Without explicit masking, the running accumulator grows beyond 32 bits. The correct approach is to mask to 32 bits after every byte: `checksum = ((checksum << 1) | (checksum >> 31)) & 0xFFFFFFFF`. Using `ctypes.c_int32` as some community tools do works, but mixes signed and unsigned semantics unnecessarily and is harder to audit.

**Why it happens:**
The demon vault restore in `demon_service.py` already implements this correctly using `& 0xFFFFFFFF` masking. Implementors copying from community tools instead may copy the `ctypes` variant, which wraps differently and produces a wrong checksum for certain byte sequences.

**Consequences:**
- Character disappears from the character select screen
- D2R creates no error log; the rejection is silent
- The backup snapshot exists, so recovery is possible — but only if the backup protocol ran before the write

**Prevention:**
- Reuse `_calculate_checksum()` from `demon_service.py` exactly — it is verified correct
- Write a round-trip unit test: read a known file, modify seed bytes, recalculate checksum, reload the file and verify the checksum field matches what D2R would accept
- Do not use `ctypes` for this — the pure `& 0xFFFFFFFF` approach in `demon_service.py` is correct and readable

**Detection:**
- Warning sign: Character missing from character select after apply
- Warning sign: Test round-trip produces a checksum that differs from the original on an unmodified file

**Phase:** Address in Phase 1 (write implementation). Zero-tolerance — do not ship without a passing round-trip test.

---

### Pitfall 3: Updating the Filesize Field When It Should Not Change

**What goes wrong:**
The .d2s header at offset `0x08` stores the total file length. The demon vault restore updates this field because it splices bytes onto the end of the file (the `lf` section payload changes length). Map seed patching is a fixed-width, in-place write: 4 bytes at a fixed offset, replacing 4 existing bytes. The total file length does not change. If the filesize field is updated anyway — because the implementation copies the demon restore pattern wholesale — it writes the current file length as the new value (no change), which is harmless but misleading. The real risk is if the new implementation accidentally changes the file length (e.g., by truncating or padding), and the filesize field is not updated.

**Why it happens:**
`demon_service.py::restore_demon_to_d2s` rebuilds the bytearray as `d2s_data[:offset] + demon_bytes`, changing the file length, so updating the filesize field there is correct. A map seed patch does NOT change file length. Copying the demon pattern without thinking about this difference will either silently succeed (if no length change) or silently corrupt (if a length change sneaks in during development).

**Prevention:**
- Assert `len(patched_data) == len(original_data)` after the patch, before writing
- Do not update the filesize field in `patch_map_seed()` — comment explicitly why

**Detection:**
- Warning sign: File length changed after patch (filesystem size differs from stored size field)
- Warning sign: D2R fails to load the character even with a valid checksum

**Phase:** Phase 1 (write implementation). Add the assertion before the first real test.

---

## Moderate Pitfalls

Mistakes in this category cause incorrect behavior that is recoverable with backups.

---

### Pitfall 4: Patching While D2R is Running

**What goes wrong:**
D2R reads the .d2s file when a character is loaded. It also writes the file continuously during play and on game exit. If the map seed is patched in the vault snapshot while D2R is running, two separate failure modes exist:

1. **Write collision:** D2R overwrites the patched snapshot on its next save, restoring the old seed. The patch appears to work but is silently undone the moment the game saves. No error is shown.

2. **Partial read:** Less likely for a header field (D2R reads the header atomically at load time), but if D2R is mid-save when the patch is applied, the file may end up with a mixed header.

**Why it happens:**
The vault snapshot lives on the local filesystem, not on the machine D2R is running. D2R on the PC writes to `%UserProfile%/Saved Games/Diablo II Resurrected/` — not the vault. So patching the vault snapshot while D2R is running is safe for the file itself. However, if the user then immediately uses "Sync to Device," the patched snapshot pushes to the PC and D2R may be mid-session with an older version in memory. On next save, D2R writes its memory state (with the old seed) back to the file, overwriting the pushed patch.

**Prevention:**
- Document clearly in the UI: "After applying a seed, sync to your device, then restart D2R for the new seed to take effect"
- The existing D2R-running check (which guards grail and vault writes to live machines) does not apply here because the vault snapshot is local — but add a UI note, not a hard block
- Seed apply only patches the vault snapshot, never the live device file directly — consistent with existing grail/vault pattern

**Detection:**
- Warning sign: User reports the seed did not change in-game after apply + sync
- Pattern: User synced but did not restart D2R after sync

**Phase:** Phase 2 (UI). UI copy must include restart instruction. Not a code-level guard.

---

### Pitfall 5: Endianness Error — Reading Seed as Big-Endian

**What goes wrong:**
The map seed is a 32-bit little-endian unsigned integer (`<I` in Python struct notation), consistent with the rest of the .d2s header. If the seed is read or displayed as big-endian, the four bytes are reversed. The value is still a valid uint32, so no error is thrown. The library saves the wrong value. When that wrong value is applied to another character, the resulting map is different from the intended one.

**Example:** Bytes `AB 9C 34 08` little-endian = `0x08349CAB` (138,108,075 decimal). Big-endian misread = `0xAB9C3408` (2,879,128,584 decimal) — a completely different map.

**Why it happens:**
Community tools like `feored/d2mapseed` display the seed as a hex string by reading raw bytes with `.hex()` and presenting them in storage order (effectively big-endian display), not as a little-endian integer. If the implementation matches this display convention, the stored and applied values are consistent within the tool but wrong relative to what D2R shows in memory. If the implementation uses `struct.unpack("<I", ...)` and stores the integer, any future display or comparison must also unpack as little-endian.

**Prevention:**
- Always use `struct.unpack_from("<I", data, offset)` for reading — matches the existing parser convention
- Always use `struct.pack_into("<I", data, offset, value)` for writing
- Store the seed as an integer in the DB, not as a hex string
- Display as hex with a consistent format: `f"0x{seed:08X}"` which is the correct decoded little-endian value

**Detection:**
- Warning sign: Seed value stored does not match what D2R's `-seed` command line or community tools show for the same character
- Unit test: Apply a known seed, read it back, verify the integer value is identical

**Phase:** Phase 1 (read/write implementation). Establish the canonical representation before any UI work.

---

### Pitfall 6: Applying a Seed to a Hardcore Dead Character

**What goes wrong:**
The `status` field in the .d2s header has a `ever_died` bit (bit 3). For hardcore characters, this bit being set means the character is in the "dead" state and will be deleted by D2R on next load. Applying a seed to a hardcore dead character's file is a no-op from the game's perspective — D2R will delete the file on load. No data loss occurs beyond wasting the operation, but the user experience is confusing: the seed apply appears to succeed, then the character disappears.

**Prevention:**
- Check `D2SCharacter.hardcore and D2SCharacter.ever_died` before allowing a seed apply to that character
- Display a warning (not a hard block, since the user might be restoring a backup anyway) in the UI

**Detection:**
- Warning sign: Character disappears after seed apply + sync
- `D2SCharacter.hardcore == True and D2SCharacter.ever_died == True` in the parsed character data

**Phase:** Phase 2 (UI). Surface the warning on the seed apply confirmation dialog.

---

## Minor Pitfalls

---

### Pitfall 7: Seed Library Not Globally Accessible (Season Scoping Creep)

**What goes wrong:**
The project spec states the seed library is global (not season-scoped). If the DB model is accidentally given a `season_id` foreign key — copying the pattern from `Character` or `GrailEntry` — seeds become invisible outside the season they were saved in. The bug is invisible until the user starts a new season and their saved seeds are gone.

**Prevention:**
- The `SavedSeed` model must have no `season_id` column and no season-aware query filter
- Add a comment to the model: `# NOT season-scoped — seeds are globally valid`

**Detection:**
- Warning sign: Seed library appears empty after starting a new season

**Phase:** Phase 1 (DB model). No season FK. Explicit comment.

---

### Pitfall 8: Cross-Character Seed Apply — Wrong File Targeted

**What goes wrong:**
The core use case is applying a seed saved from Character A to Character B. If the implementation accidentally reads the seed value but writes it to the source character's file (character A) rather than the target, the target character is unchanged. This produces a confusing UX where the operation appears to succeed but the target is unaffected.

**Prevention:**
- The apply endpoint must take both `source_seed_id` (from library) and `target_character_filename` as explicit parameters
- The service function signature should be `apply_seed(seed: int, target_filename: str, snapshot_path: Path)` — no implicit "current character" default
- Write a unit test with source != target

**Detection:**
- Warning sign: User reports target character's map did not change after apply + sync
- Integration test failure if the target path is not parameterized

**Phase:** Phase 1 (service layer). Catch in design review before coding.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Seed read implementation | Wrong offset for v100+ files (Pitfall 1) | Check version field; use `0x9B` for v100+, `0xAB` for v96-99 |
| Seed write implementation | Invalid checksum corrupts character (Pitfall 2) | Reuse `_calculate_checksum()` from `demon_service.py`; add round-trip test |
| Seed write implementation | Filesize field incorrectly updated (Pitfall 3) | Assert `len(patched) == len(original)` before write |
| Seed write implementation | Endianness mismatch silently stores wrong seed (Pitfall 5) | Always use `struct.pack/unpack` with `<I` format |
| DB model | Accidental season scoping (Pitfall 7) | No `season_id` FK; explicit comment in model |
| UI | D2R running confusion (Pitfall 4) | Document restart requirement; no hard block needed |
| UI | Hardcore dead character apply (Pitfall 6) | Show warning if `hardcore and ever_died` |
| Service layer | Cross-character apply targets wrong file (Pitfall 8) | Explicit `target_filename` parameter; no implicit default |

---

## Confidence Notes

| Finding | Confidence | Source |
|---------|------------|--------|
| Map seed offset v96-99 = `0xAB` (171) | HIGH | D2CE format doc; D2SLib-D2R `D2S.cs`; two independent Python tools |
| Map seed offset v100+ = `0x9B` (155) | HIGH | Derived from codebase's own v100+ difficulty-block shift (documented in `d2s_parser.py:129–135`); consistent with the -16 byte rule applied across all post-0x14 fields |
| Checksum algorithm: rotate-left + add, zero checksum field first | HIGH | Multiple community implementations; `demon_service.py` in codebase is already correct |
| Filesize field unchanged for in-place 4-byte patch | HIGH | Direct inspection of `demon_service.py` pattern; in-place patch does not alter file length |
| D2R running: vault snapshot is local, risk is at push time not patch time | MEDIUM | Derived from existing sync architecture; not explicitly documented in public D2R resources |
| Checksum algorithm: unsigned `& 0xFFFFFFFF` preferred over `ctypes.c_int32` | MEDIUM | Code review of community tools; `demon_service.py` uses the correct approach |

---

## Sources

- D2CE `d2s_File_Format.md`: https://github.com/WalterCouto/D2CE/blob/main/d2s_File_Format.md
- D2SLib-D2R (locbones fork): https://github.com/locbones/D2SLib-D2R
- feored/d2mapseed Python tool: https://github.com/feored/d2mapseed
- divineblade7/d2mapseed-sp Python tool: https://github.com/divineblade7/d2mapseed-sp
- Daancoppens D2 save format series (checksum algorithm): https://daancoppens.wordpress.com/2017/03/18/understanding-the-diablo-2-save-file-format-part-3/
- Enigma Engine codebase: `backend/services/demon_service.py`, `backend/services/d2s_parser.py`
- noobient "Finding the Map Seed in D2R" (2025-11): https://noobient.com/2025/11/21/finding-the-map-seed-in-diablo-ii-resurrected/
