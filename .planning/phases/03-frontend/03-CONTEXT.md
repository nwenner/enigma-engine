# Phase 3: Frontend - Context

**Gathered:** 2026-03-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 3 delivers the Map Seeds React page (`/seeds`) — a single-page UI with two sections:
1. **Current Seeds** — compact table of all characters from the latest vault snapshot with their seed values; each row has a [Save Seed] inline expand form
2. **Seed Library** — list of saved seed entries (tags/notes/apply/edit/delete)

No backend changes except one minor model rename (`name` → `label` on `SavedSeed`) to align with the tag-based UI pattern. All API endpoints are already live from Phase 2.

</domain>

<decisions>
## Implementation Decisions

### Page Layout

- **D-01:** Two sections, one page (no tabs). Current Seeds section on top, Seed Library section below. Max-w-3xl centered, same container as Demon Registry. User scrolls to see both.
- **D-02:** Nav entry: `{ to: "/seeds", label: "Map Seeds", icon: "🗺️" }` added to `NAV_ITEMS` in `App.tsx`. Route: `<Route path="/seeds" element={<Seeds />} />`.

### Current Seeds Section

- **D-03:** Layout: compact table rows (not cards). Each row: `Character · Class   0x7FB203B4 (muted/small)   [Save Seed]`. Hex value shown in small muted text for reference. Decimal value NOT shown — the label/tags are the useful identifiers.
- **D-04:** [Save Seed] button on each row triggers an inline form that expands below that row (not a modal, not a separate panel). Expanding hides the [Save Seed] button and shows [Cancel] inline.
- **D-05:** Inline save form contains: `TagInput` (for labels/tags), notes text input, [Save ✓] button. Collapses after successful save. Only one row can be expanded at a time.

### Seed Library Section

- **D-06:** Tags-first display — library cards use `TagInput`-style chips (`chip-d2`) for the label field, same visual pattern as Demon Registry's tag chips. The label field is the primary identifier; notes (if any) shown beneath in muted text.
- **D-07:** Each library card shows: tag chips (from `label`), optional notes, source character + saved date (muted), inline apply row (character dropdown + [Apply →] button), [edit] + [✕] buttons.
- **D-08:** Cards in a single-column list (full width), same as Demon Registry — not a 2-column grid.
- **D-09:** Character dropdown in apply row populates from the same current seeds data (all characters in latest snapshot). Disabled if no snapshot available.

### Save Flow

- **D-10:** Save form uses `TagInput` component (already exists at `frontend/src/components/TagInput.tsx`). Label is comma-separated tags stored in `SavedSeed.label` field.
- **D-11:** `POST /api/seeds/library` body becomes `{ character, label, notes }` — backend field rename from `name` to `label` required. Minor change to `SaveSeedRequest` Pydantic model + `SavedSeed` ORM column.
- **D-12:** Existing tag suggestions: pass all unique labels already in the library (split by comma) as suggestions to TagInput, same as Demon Registry pattern.

### Apply Flow

- **D-13:** Inline per card — exact Demon Registry inject pattern. Character dropdown (`select-d2`) + [Apply →] button (`btn-d2`). No modal.
- **D-14:** D2R running guard: disable [Apply →] button when `preflight.pc_running || preflight.deck_running`, with `title="D2R is running — close the game first"` tooltip.
- **D-15:** Success feedback: inline green text below the apply row (`"Applied to {character}. Sync to device when ready."`) — same pattern as Demon inject. Also a sonner toast from the response shape `{ seed_name, character, seed_hex }`.

### Edit Flow

- **D-16:** Edit button (pencil icon or text "edit") on each card. Clicking toggles the card into edit mode: replaces display with TagInput (pre-filled) + notes input (pre-filled) + [Save ✓] / [Cancel]. No modal.
- **D-17:** `PATCH /api/seeds/library/{id}` body: `{ label, notes }` — field rename from `name` to `label` applies here too.
- **D-18:** After successful save, card snaps back to display mode with updated values. TanStack Query `invalidateQueries` on the library list.

### Delete Flow

- **D-19:** [✕] delete button on each card. No confirmation dialog (same as Demon Registry). Optimistic removal via TanStack Query `onMutate` or immediate invalidation.

### Backend Field Rename

- **D-20:** `SavedSeed` model column `name` → `label`. Also update: `SaveSeedRequest.name` → `label`, `UpdateSeedRequest.name` → `label`, `SavedSeedRecord.name` → `label`, router logic in `seeds.py`. This is the only backend change in Phase 3.

### Empty States

- **D-21:** No snapshot available: `"No snapshot available. Check In from a device first."` (same wording as existing pages).
- **D-22:** No seeds in library: `"No seeds saved yet."` below the library heading.

### Claude's Discretion

- Hook naming: `useSeedsCurrentQuery`, `useSeedLibrary`, `useSaveSeed`, `useApplySeed`, `useUpdateSeed`, `useDeleteSeed` — follow existing hook naming conventions in `hooks.ts`
- Pydantic field rename: decide whether a DB migration is needed (SQLite column rename). If the column was just created in Phase 2 and no data exists, a fresh `init_db()` handles it. If data exists, a migration script or `ALTER TABLE` may be needed.
- TypeScript type names: `SeedEntry`, `SavedSeedRecord` (update `label` field in types), `ApplySeedRequest`

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Closest UI template (most important)
- `frontend/src/pages/Demon.tsx` — exact page structure to mirror: register panel → card list → info blurb. TagInput usage, chip rendering, inject flow, preflight D2R check, inline feedback pattern.
- `frontend/src/components/TagInput.tsx` — existing tag input component; reuse directly

### App wiring
- `frontend/src/App.tsx` — `NAV_ITEMS` array + `<Routes>` block for adding the new page

### API hooks pattern
- `frontend/src/api/hooks.ts` — TanStack Query hook patterns; all new hooks go here
- `frontend/src/api/types.ts` — TypeScript interfaces; add `SeedEntry`, `SavedSeedRecord` (with `label` field)
- `frontend/src/api/client.ts` — axios client configured with `baseURL: "/api"` and 30s timeout

### Phase 2 endpoints (already implemented)
- `backend/routers/seeds.py` — all endpoints live; note field rename `name` → `label` needed in `SaveSeedRequest`, `UpdateSeedRequest`, `SavedSeedRecord`
- `backend/models.py` — `SavedSeed` ORM class; rename `name` column → `label`

### Design system
- `frontend/src/index.css` — `card-d2`, `btn-d2`, `select-d2`, `input-d2`, `chip-d2` class definitions
- `frontend/tailwind.config.ts` — `d2gold`, `d2bg-*` color tokens, `font-diablo`

### Project constraints
- `CLAUDE.md` — naming conventions, TypeScript strict mode, no unused locals/params

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `TagInput` component (`frontend/src/components/TagInput.tsx`) — drop-in for save and edit forms; accepts `tags`, `onChange`, `suggestions`, `placeholder`
- `usePreflight()` hook — already used in Demon.tsx for D2R running check; reuse directly
- `chip-d2` CSS class — renders individual tag chips with `text-d2gold/70 border-d2gold/30` styling
- `fmt()` date formatter pattern from Demon.tsx — copy for "saved Mar 28" display

### Established Patterns
- D2R running guard: `const d2rRunning = preflight?.pc_running === true || preflight?.deck_running === true` — disable mutation buttons, add title tooltip
- Inline feedback: `{msg && <p className="text-emerald-400 text-xs">{msg}</p>}` + `{err && <p className="text-red-400 text-xs">{err}</p>}`
- Card structure: `<div className="card-d2 p-4">` with header row (content + ✕ button) and action row below
- Section headings: `<h2 className="text-slate-400 text-xs uppercase tracking-widest mb-2">Section Name</h2>`
- Page wrapper: `<div className="p-4 sm:p-6 max-w-3xl mx-auto animate-fadeIn space-y-6">`

### Integration Points
- `frontend/src/App.tsx` — add `import Seeds from "./pages/Seeds"`, add to `NAV_ITEMS`, add `<Route path="/seeds" element={<Seeds />} />`
- `frontend/src/api/hooks.ts` — add all seed hooks
- `frontend/src/api/types.ts` — add `SeedEntry`, `SavedSeedRecord` interfaces
- `backend/routers/seeds.py` + `backend/models.py` — rename `name` → `label` (only backend change this phase)

</code_context>

<specifics>
## Specific Ideas

- Apply success toast text: `"Applied '{seed_name}' to {character} ({seed_hex})"` — response shape from Phase 2 CONTEXT.md supports this exactly
- Inline save expand: only one row expanded at a time — clicking Save Seed on a second row should collapse any open row first
- Tag suggestions for save form: split all existing `SavedSeed.label` values by comma, deduplicate, pass as `suggestions` prop to TagInput

</specifics>

<deferred>
## Deferred Ideas

- Seed hex copy-to-clipboard button — nice to have, not needed for v1 functionality
- "Last applied" metadata on library cards — requires tracking apply history (SEED-V2-04)
- Filter/search the seed library — useful once it grows beyond ~10 entries
- Auto-push to device after apply — SEED-V2-01, explicitly out of v1 scope

</deferred>

---

*Phase: 03-frontend*
*Context gathered: 2026-03-28*
