# Feature Landscape: Map Seed Manager

**Domain:** D2R save file map seed management (addition to existing Enigma Engine app)
**Researched:** 2026-03-28
**Confidence:** HIGH for core features (directly analogous to existing Demon Vault pattern), MEDIUM for seed offset specifics (empirically confirmed by d2mapseed tool source at offset 171-174, needs in-app verification)

---

## Context

Map seeds in D2R single-player are 32-bit unsigned integers embedded in each `.d2s` file. They deterministically generate the entire map layout for a character. Players care about seeds because:

- Some seeds produce "short" layouts (e.g., Lower Kurast bonfires close together, Travincal Council tightly clustered, Mephisto reachable fast)
- Accidentally changing seed (difficulty change, joining multiplayer, rerolling) means losing a known-good layout forever without a backup
- PC/Steam Deck sync is the exact scenario where seeds get lost — syncing the "wrong direction" overwrites a curated map

The technical facts established by research:

- **Seed location**: bytes 171-174 (inclusive), 4 bytes, little-endian uint32 — confirmed via `d2mapseed.py` source (feored/d2mapseed on GitHub)
- **Existing parser**: `backend/services/d2s_parser.py` already reads the `.d2s` header; adding seed extraction is a small struct read extension
- **Write constraint**: seed can be read while D2R runs; writing requires D2R closed (same as all other write ops)
- **Checksum**: `.d2s` has a CRC-like checksum at offset 12 (uint32) that must be recalculated after any byte change — `d2mapseed.py` does this via rotate-left-1 accumulation (identical to the demon restore checksum algorithm already in `demon_service.py`)

---

## Table Stakes

Features that make this page useful at all. Missing any one makes the feature feel incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Read seed from each character's current snapshot | Core read operation — nothing works without this | Low | Struct read at offset 171-174; extend `d2s_parser.py`; reads from latest `manual`/`game_close` snapshot (no SSH) |
| Display all characters with their current seed | Players need to see what seeds they currently have before deciding to save any | Low | List view: character name, class, level, current seed (decimal + hex display) — same data already on Characters page |
| Save seed to named library entry | The entire point of the feature — capture a seed with a meaningful name | Low | Name (required) + optional notes field; seed value + source character recorded automatically; global across seasons |
| Delete a library entry | Obvious CRUD — seeds get stale or were saved by mistake | Low | Soft-confirmation modal, same pattern as demon vault delete |
| Apply (restore) a saved seed to any character | Core write operation — transfers the good map to any character | Medium | Read file from snapshot, patch bytes 171-174, recalculate checksum, write back to snapshot, create new snapshot record |
| Backup before restore (pre_seed_restore snapshot) | Non-negotiable per existing binary safety protocol | Low | `create_snapshot(..., label="pre_seed_restore")` — matches `pre_demon_restore` pattern exactly |
| D2R-not-running check before restore | Non-negotiable per existing write protocol | Low | Same `check_d2r_running()` check used in grail, demon vault, stash writes |
| Snapshot created after restore | Keeps vault consistent — modified file needs a new snapshot record | Low | Use `create_snapshot()` post-write or update the snapshot file in place |

---

## Differentiators

Features that add real value beyond the minimum, but are not needed for the page to be useful.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Show seed in both decimal and hex | Seeds are discussed both ways in community — decimal for sharing, hex for debugging | Low | Pure display formatting, zero backend work |
| Timestamp on library entry (saved_at) | Players want to know when they captured a seed — correlates to "that season with the great LK map" | Low | Auto-set at save time, no UI input needed |
| Source character recorded on library entry | Reminds player which character had this layout and why they saved it | Low | Store `character_filename` + `character_name` at save time |
| Seed in hex matches the `.d2s` raw bytes exactly | Power users debugging binary files want the raw bytes, not just decimal | Low | Display as `0xAB39C208` alongside decimal |
| Edit notes on an existing library entry | Players add notes after testing ("LK has two bonfires 3 screens apart, great Vex odds") | Low | PATCH endpoint for name/notes only — not the seed value |
| Confirm before overwrite warning | If applying seed A to a character that already has seed B in the library, warn user they are discarding B's layout | Medium | Query: does current seed exist in library? If not, show "This will change your map — current layout is not saved" warning |
| Current seed highlighted in library | If a character's current seed already matches a library entry, show that link clearly | Low | Frontend comparison: character seed === library entry seed |

---

## Anti-Features

Things to deliberately NOT build in v1.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Auto-push to device after seed restore | Adds SSH dependency and complexity to what is a local vault operation; user already knows how to use Sync to Device | Let user trigger sync manually from Dashboard after restore — same as grail/demon vault pattern |
| Manual seed entry (type in a seed number) | Seeds should always come from a real `.d2s` file in the vault — typed seeds could be invalid values, waste of UX work | Only ever read seeds from actual save files |
| Map screenshots or visual area previews | Rendering D2R map layouts requires a separate map renderer (d2mapapi or similar) — enormous scope, separate project | Seeds are identified by player-written notes, not rendered previews |
| Seed sharing / export / import | This is a personal local tool; seed sharing is a community/multiplayer feature not relevant to solo sync | Players share seed numbers out-of-band via text if they want |
| Per-season seed scoping | A good map is a good map; seeds are valid across seasons; scoping adds DB complexity for no real benefit | Library is global — same seed works in any season |
| Seed search or filtering | Library will contain at most a handful of seeds (one or two per farming goal); a list is sufficient | Ship a flat list; add search only if it becomes a problem |
| Automated "find good seed" scanning | Would require running D2R headlessly or integrating map generation logic — completely out of scope | Player finds a good seed through gameplay, saves it here |
| Seed validation (checking if seed is "good") | No reliable fast way to validate map quality without generating the full map; out of scope | Trust the player's judgment — they run the map, they decide |

---

## Feature Dependencies

```
Read seed from snapshot
  └── Display characters + seeds          (requires read)
  └── Save seed to library                (requires read — seed comes from a character's current value)

Save seed to library
  └── Apply seed to character             (library entry must exist)
  └── Edit notes on library entry         (library entry must exist)
  └── Delete library entry                (library entry must exist)

Backup before restore
  └── Apply seed to character             (backup is a prerequisite, not a sequential step)

D2R-not-running check
  └── Apply seed to character             (check must pass before write proceeds)

Snapshot after restore
  └── Apply seed to character             (snapshot records the new state)
```

---

## MVP Recommendation

Build in this order — each step is shippable and the list is complete in one phase.

**Backend:**
1. Extend `d2s_parser.py` to extract `map_seed` (uint32 at offset 171 for v96-99, verify offset for v100+ since name-block shift may affect it)
2. Add `SeedLibraryEntry` model (id, name, notes, seed_value, source_character_name, source_character_filename, saved_at)
3. Add `GET /api/seeds/characters` — all characters from latest snapshot with their current seed
4. Add `POST /api/seeds/library` — save seed to library (name + notes + auto-captured seed + source)
5. Add `GET /api/seeds/library` — list all entries
6. Add `DELETE /api/seeds/library/{id}` — remove entry
7. Add `PATCH /api/seeds/library/{id}` — edit name/notes
8. Add `POST /api/seeds/restore` — apply saved seed to a target character: backup → check D2R closed → patch bytes → recalculate checksum → write → new snapshot
9. Add `backend/routers/seeds.py` wiring all of the above

**Frontend:**
1. New page `/seeds` → `frontend/src/pages/Seeds.tsx` with nav entry "Map Seeds"
2. Left panel: character list with current seed (decimal + hex)
3. Right panel: seed library with save/delete/edit/apply controls
4. Apply confirmation modal with "current layout not saved" warning when applicable

**Defer:**
- Edit notes: defer if time-constrained — delete + re-save accomplishes the same thing
- Overwrite warning: defer to v2 — it is a nice safety net but not blocking

---

## Seed Offset Verification Note (MEDIUM confidence)

The `d2mapseed.py` source confirms offset 171-174 for the map seed. However, the Enigma Engine parser already handles two header layouts (v96-99 and v100+) where the v100+ format shifts fields by 16 bytes due to the name field moving. The seed offset may or may not shift similarly.

**Recommended approach for Phase 1**: Read the seed offset from a known `.d2s` file empirically (compare `d2mapseed.py` output against manual struct read), then lock in the correct offset for each version. This is the same empirical approach used to find the `lf` demon section.

---

## Sources

- [feored/d2mapseed source — confirmed offset 171-174, checksum algorithm](https://github.com/feored/d2mapseed)
- [divineblade7/d2mapseed-sp — D2R single-player fork](https://github.com/divineblade7/d2mapseed-sp)
- [Karyoplasma/D2-MapID-Finder — community seed sharing tool](https://github.com/Karyoplasma/D2-MapID-Finder)
- [WalterCouto/D2CE d2s_File_Format.md — field at offset 179, "Merc seed?" for v92+](https://github.com/WalterCouto/D2CE/blob/main/d2s_File_Format.md) (LOW confidence on description — label is speculative)
- [D2R LK farming seed discussion — diablo2.io](https://diablo2.io/forums/d2r-vs-lod-seeds-lk-farming-single-player-t1574525.html)
- [D2JSP good LK map seed thread — community usage patterns](https://forums.d2jsp.org/topic.php?t=84656529&f=161)
