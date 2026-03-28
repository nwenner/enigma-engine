# Phase 3: Frontend — Discussion Log

**Date:** 2026-03-28
**Status:** Complete

## Q&A Transcript

### Area Selection
**Q:** Which areas do you want to discuss for Phase 3?
**A:** All four — Current Seeds display, Save flow, Apply flow, Edit name/notes

---

### Area 1: Page Layout
**Q:** How should the Map Seeds page be structured?
**A:** Two sections, one page (Current Seeds on top, Seed Library below — Demon Registry pattern)

---

### Area 2: Current Seeds Display
**Q:** How should each character row look?
**A:** Compact table row (name · class · hex small/muted · [Save Seed])
*User note: "I don't want seed hex or dec, I want labels/tags like the demon vault — I'll provide a screenshot with the labels I want"*

**Q:** Should decimal value be shown?
**A:** See notes — hex/decimal are useless values as long as they're correct. Labels/tags are the useful identifiers.
*Resolved: hex shown small/muted for reference; decimal hidden; labels/tags are primary display in library*

**Q:** What's most useful to show per character in Current Seeds (no labels exist yet)?
**A:** Name + class + hex (small/muted) — for reference when saving

**Q:** Tags like Demon Vault or single name + notes for library?
**A:** Tags like Demon Vault — TagInput, comma-separated. Rename `name` → `label` in SavedSeed model.

---

### Area 3: Save Flow
**Q:** When [Save Seed] is clicked, how should the form appear?
**A:** Inline expand below the row — TagInput + notes + [Save ✓]. Collapses after save.

---

### Area 4: Apply Flow
**Q:** How should applying a library seed to a character work?
**A:** Inline per card — character dropdown + [Apply →] button. Exact Demon Registry inject pattern.

---

### Area 5: Edit Flow
**Q:** How should editing tags/notes work?
**A:** Edit button → card toggles to edit form (TagInput + notes pre-filled + [Save ✓] / [Cancel])

---

### Completion
**Q:** Ready to create context?
**A:** Create context
