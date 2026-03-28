---
phase: 03-frontend
plan: "02"
subsystem: frontend
tags: [react, seeds, ui, typescript]
dependency_graph:
  requires: [03-01]
  provides: [Seeds.tsx, /seeds route]
  affects: [App.tsx]
tech_stack:
  added: []
  patterns: [TanStack Query mutations, inline expand/collapse form, tag-based editing]
key_files:
  created:
    - frontend/src/pages/Seeds.tsx
  modified:
    - frontend/src/App.tsx
decisions:
  - Seeds page follows Demon.tsx structure exactly for consistency
  - Auto-approved checkpoint:human-verify (auto_advance=true)
metrics:
  duration: "~2min"
  completed_date: "2026-03-28"
  tasks_completed: 3
  files_changed: 2
---

# Phase 03 Plan 02: Map Seeds Frontend Page Summary

**One-liner:** React Seeds page with inline save/edit/delete/apply flows, TagInput, D2R guard, and sidebar nav wired at /seeds.

## What Was Built

Complete `Seeds.tsx` page component and App.tsx routing wired for the Map Seeds feature (SEED-03).

### Seeds.tsx (388 lines)

Two-section layout on a single scrollable page:

**Section 1 — Current Seeds (`CurrentSeedsSection`):**
- Renders all characters from the latest snapshot with name, class, and hex seed value
- Click [Save Seed] to expand an inline form for that row (one row at a time)
- Inline form: TagInput with existing-tag suggestions + optional notes field
- Save button disabled when tags empty, mutation pending, or D2R running
- D2R guard tooltip: "D2R is running — close the game first"
- Empty states: loading spinner text, "No snapshot available. Check In from a device first."

**Section 2 — Seed Library (`SeedLibraryCard`):**
- Tag chips display, notes, source character + saved date metadata
- Apply dropdown: select any character from Current Seeds, click [Apply →]
- Apply success: inline message "Applied to {char}. Sync to device when ready." + sonner toast
- Edit mode: click "edit" → TagInput pre-filled with existing tags, notes field, Save/Cancel
- Delete: ✕ button removes card immediately (no confirmation)
- Apply and Save buttons disabled when D2R running

**Shared:**
- `existingTags` derived from all library labels — passed to both sections for TagInput suggestions
- "How it works" blurb at bottom

### App.tsx changes

- Import: `import Seeds from "./pages/Seeds"`
- NAV_ITEMS: `{ to: "/seeds", label: "Map Seeds", icon: "🗺️" }` between Demon Registry and Boss Portals
- Route: `<Route path="/seeds" element={<Seeds />} />`

## Verification

- `npx tsc --noEmit` — no errors (both tasks)
- 655 backend tests pass, 7 skipped (pre-existing)
- Task 3 checkpoint:human-verify auto-approved (auto_advance=true)

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — all hooks (`useSeedsCurrentQuery`, `useSeedLibrary`, `useSaveSeed`, `useApplySeed`, `useUpdateSeed`, `useDeleteSeed`) were implemented in Plan 01 and are fully wired. The `useApplySeed` response shape uses `data.seed_name`, `data.character`, `data.seed_hex` matching the backend contract from Plan 02-04.

## Self-Check: PASSED
