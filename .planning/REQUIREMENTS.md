# Requirements: Enigma Engine — Map Seed Milestone

**Defined:** 2026-03-28
**Core Value:** Save and restore D2R map seeds so known-good farming layouts are never lost.

## v1 Requirements

### Seed Reading

- [ ] **SEED-01**: App reads the map seed from each character's .d2s file in the latest vault snapshot
- [ ] **SEED-02**: App handles version-conditional offset (v96-99 at 0xAB, v100+ at 0x9B) correctly
- [x] **SEED-03**: Map Seeds page displays all characters with their current seed (hex + decimal)

### Seed Library

- [x] **SEED-04**: User can save a seed to the library with a name and optional notes
- [x] **SEED-05**: User can edit the name and notes of a saved seed
- [x] **SEED-06**: User can delete a seed from the library

### Seed Restore

- [x] **SEED-07**: User can apply any saved seed to any character's .d2s file
- [x] **SEED-08**: Apply operation creates a `pre_seed_restore` backup snapshot before modifying any file
- [x] **SEED-09**: Apply operation is blocked when D2R is detected as running
- [x] **SEED-10**: Apply operation creates a new vault snapshot from the modified file
- [x] **SEED-11**: Checksum is recalculated correctly after patching the seed bytes

## v2 Requirements

### Enhancements

- **SEED-V2-01**: Auto-push to device after seed restore (user opted for snapshot-only in v1)
- **SEED-V2-02**: Seed sharing — export/import seed entries between instances
- **SEED-V2-03**: Map area notes — tag seeds with which specific farming areas are good
- **SEED-V2-04**: Seed history — track which seeds have been applied to which characters

## Out of Scope

| Feature | Reason |
|---------|--------|
| Manual seed entry | Seeds come from save files only — no typed input needed |
| Map previews / screenshots | Requires D2R map generation tooling — separate scope entirely |
| Season-scoped seed library | Seeds are valuable across seasons; global library is sufficient |
| Auto-push to device after restore | User controls sync timing via existing Sync to Device |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| SEED-01 | Phase 1 | Pending |
| SEED-02 | Phase 1 | Pending |
| SEED-03 | Phase 3 | Complete |
| SEED-04 | Phase 2 | Complete |
| SEED-05 | Phase 2 | Complete |
| SEED-06 | Phase 2 | Complete |
| SEED-07 | Phase 2 | Complete |
| SEED-08 | Phase 2 | Complete |
| SEED-09 | Phase 2 | Complete |
| SEED-10 | Phase 2 | Complete |
| SEED-11 | Phase 2 | Complete |

**Coverage:**
- v1 requirements: 11 total
- Mapped to phases: 11
- Unmapped: 0 ✓

---
*Requirements defined: 2026-03-28*
*Last updated: 2026-03-28 after roadmap creation*
