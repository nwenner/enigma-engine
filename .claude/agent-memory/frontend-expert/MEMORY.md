# Frontend Expert Memory — Enigma Engine

## Critical Rule: Working Directory
ALWAYS write files to the canonical repo path `/Users/nickwenner/Dev/repos/enigma-engine/frontend/...`. If launched from a worktree (path contains `.claude/worktrees/`), use absolute paths to the main repo. Never write code into a worktree.

## Pages (frontend/src/pages/) — 12 total
- Dashboard.tsx (26KB) — sync UI, device status cards, recent activity feed
- Seasons.tsx (74KB) — LARGEST FILE — season CRUD, milestone management, rewards flow
- Stash.tsx (45KB) — item vault view, search/filter, gold vault, item store/retrieve
- Settings.tsx (27KB) — SSH config, key upload, machine settings, auto-sync toggle
- Grail.tsx (26KB) — holy grail tracker, deposit/retrieve UI, progress display
- Rewards.tsx (20KB) — season reward claim flow with stash integration
- Characters.tsx (7KB) — character list with class icons and level display
- Demon.tsx (9KB) — demon registry save/restore, character selection
- Seeds.tsx — map seeds: current character seed display, library management, apply flow
- BossPortals.tsx (11KB) — boss portal unlock tracking per difficulty
- Backups.tsx (11KB) — snapshot browsing, restore, label filtering
- History.tsx (5KB) — sync event log with direction labels

## Shared Components (frontend/src/components/)
- ConfirmDialog.tsx — `{ isOpen, title, message, onConfirm, onCancel }` — always use for destructive ops
- Collapsible.tsx — expandable section with title prop
- InfoModal.tsx — information display modal
- SyncStatusModal.tsx (4KB) — real-time sync progress with SSE
- CharacterCard.tsx — character display widget
- TagInput.tsx — multi-tag input for seed library tags

## API Layer
- hooks.ts (33KB) — ALL TanStack Query hooks; section dividers `// ─── Name ───`
- types.ts (10KB) — ALL TypeScript interfaces for API responses
- client.ts — axios instance, baseURL: "/api", timeout: 30_000
- useEventStream.ts — SSE listener, fires at app root in App.tsx

## Key TypeScript Rules (ALL are compile errors, not warnings)
- noUnusedLocals: every declared variable must be used
- noUnusedParameters: prefix intentionally unused params with `_`
- noFallthroughCasesInSwitch: must break/return in every case
- Import types only: `import type { Foo }` when used only as type

## Hook Patterns
```typescript
// Query: explicit generic, section divider comment above
export function useMyResource() {
  return useQuery<MyResourceResponse>({
    queryKey: ["myResource"],
    queryFn: () => api.get("/my-resource").then((r) => r.data),
  });
}
// Mutation: explicit TData/TError/TVariables generics
export function useDeleteMyResource() {
  const qc = useQueryClient();
  return useMutation<void, Error, number>({
    mutationFn: (id) => api.delete(`/my-resource/${id}`).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["myResourceList"] }),
  });
}
```

## No Frontend Tests Exist Yet
First-time setup requires bootstrapping Vitest:
1. Install: vitest, @testing-library/react, @testing-library/user-event, @testing-library/jest-dom, jsdom
2. Create frontend/vitest.config.ts with jsdom environment
3. Create frontend/src/test/setup.ts importing @testing-library/jest-dom
4. Add "test": "vitest", "test:run": "vitest run" to package.json scripts

## App.tsx
- Routes registered as `<Route path="/page" element={<Page />} />`
- Nav items in NAV_ITEMS array: `{ path, label, icon }`
- SSE: useEventStream() + useSyncToasts() mounted at root

## Custom Tailwind Tokens
d2gold/#c8a84b, d2gold-light/#e6c96a, d2gold-dark/#9a7a2e
d2bg/#0c0e12, d2bg-surface/#111318, d2bg-elevated/#1a1e2a, d2bg-border/#2d3347
font-diablo: Cinzel, Georgia, serif
Animations: fadeIn, glowPulse, navSlide, shimmer, stampIn
