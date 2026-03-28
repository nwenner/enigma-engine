# Roadmap: Enigma Engine — Map Seed Milestone

**Created:** 2026-03-28
**Granularity:** Coarse
**Coverage:** 11/11 requirements mapped

---

## Phases

- [ ] **Phase 1: Parser + Read Verification** - Read map seed from .d2s files and empirically verify correct offset before any write code is built
- [ ] **Phase 2: Write Path + Library** - Save seeds to named library, apply any seed to any character with full backup and checksum safety
- [ ] **Phase 3: Frontend** - Map Seeds page with character seed display, library management, and apply flow

---

## Phase Details

### Phase 1: Parser + Read Verification
**Goal**: The app can reliably read map seeds from vault snapshot files and the correct offset is empirically confirmed
**Depends on**: Nothing (first phase)
**Requirements**: SEED-01, SEED-02
**Success Criteria** (what must be TRUE):
  1. Calling `GET /api/seeds/current` returns each character's seed as both decimal and hex values
  2. Seed values returned for v100+ saves match a known-correct value from a hex dump or `d2mapseed` tool comparison
  3. Seed values returned for v96-99 saves use the `0xAB` offset and also match known-correct values
**Plans:** 1 plan
Plans:
- [ ] 01-01-PLAN.md — Parser helper, seeds router, and empirical verification checkpoint

### Phase 2: Write Path + Library
**Goal**: Users can save seeds to a named library and apply any saved seed to any character's vault snapshot
**Depends on**: Phase 1
**Requirements**: SEED-04, SEED-05, SEED-06, SEED-07, SEED-08, SEED-09, SEED-10, SEED-11
**Success Criteria** (what must be TRUE):
  1. User can save a character's current seed to the library with a name and optional notes, and it persists across app restarts
  2. User can edit the name and notes of an existing library entry via the API
  3. User can delete a seed from the library and it no longer appears
  4. Applying a seed to a character creates a `pre_seed_restore` backup snapshot before any file is touched
  5. Apply operation returns an error when D2R is detected as running; the file is not modified
  6. After a successful apply, reading the seed back from the modified vault snapshot returns the applied seed value
**Plans:** 4 plans
Plans:
- [x] 02-01-PLAN.md — SavedSeed model + d2s_utils.py checksum extraction (Wave 1)
- [x] 02-02-PLAN.md — write_map_seed() helper + seed_service.py apply orchestration (Wave 2)
- [x] 02-03-PLAN.md — Library CRUD endpoints (save/list/edit/delete) in seeds.py (Wave 2)
- [x] 02-04-PLAN.md — Apply endpoint in seeds.py + test_seed_service.py (Wave 3)

### Phase 3: Frontend
**Goal**: Users can view all character seeds, manage their seed library, and apply seeds entirely from the web UI
**Depends on**: Phase 2
**Requirements**: SEED-03
**Success Criteria** (what must be TRUE):
  1. The Map Seeds page loads and shows every character from the latest vault snapshot with their seed in hex
  2. User can click Save on a character row, enter a name and optional notes, and see the entry appear in the library panel
  3. User can click Apply on a library entry, select a target character, confirm, and receive visual confirmation of success or a clear error if D2R is running
  4. User can edit a library entry's name or notes inline and see the updated values without a page reload
  5. User can delete a library entry and it disappears from the list immediately
**Plans:** 1/2 plans executed
Plans:
- [x] 03-01-PLAN.md — Backend field rename (name to label) + TypeScript types + TanStack Query hooks (Wave 1)
- [ ] 03-02-PLAN.md — Seeds.tsx page component + App.tsx wiring + visual verification (Wave 2)

---

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Parser + Read Verification | 0/1 | Not started | - |
| 2. Write Path + Library | 0/4 | Not started | - |
| 3. Frontend | 1/2 | In Progress|  |
