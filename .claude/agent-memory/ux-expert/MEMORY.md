# UX Expert Memory — Enigma Engine

## Design Tokens (tailwind.config.ts)
Colors:
- d2gold/#c8a84b (accent), d2gold-light/#e6c96a (hover), d2gold-dark/#9a7a2e (subdued)
- d2bg/#0c0e12 (page bg), d2bg-surface/#111318 (cards), d2bg-elevated/#1a1e2a (modals), d2bg-border/#2d3347 (borders)

Typography:
- font-diablo (Cinzel) — headings only
- text-gray-100 primary, text-gray-300 secondary, text-gray-400 tertiary, text-gray-500 placeholder/disabled

Animations: fadeIn(0.25s), glowPulse(2.5s loop — use sparingly for "live" states), navSlide, shimmer(loading), stampIn(achievement unlock)

## Established UI Patterns
```
Page wrapper:    p-6 text-gray-100
Card:            bg-d2bg-surface border border-d2bg-border rounded-lg p-4
Modal/elevated:  bg-d2bg-elevated border border-d2bg-border rounded-xl p-6 shadow-xl
Section divider: border-t border-d2bg-border my-4
Empty state:     text-center py-12 text-gray-500
Primary btn:     bg-d2gold text-black font-semibold px-4 py-2 rounded hover:bg-d2gold-light transition-colors
Danger btn:      bg-red-800 text-white px-4 py-2 rounded hover:bg-red-700 transition-colors
Ghost btn:       border border-d2bg-border text-gray-300 px-4 py-2 rounded hover:bg-d2bg-elevated transition-colors
Gold heading:    font-diablo text-d2gold text-2xl
Status badge:    inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium
```

## Shared Components Available
- ConfirmDialog — destructive operations (always use, never inline delete)
- Collapsible — secondary/advanced content not needed by default
- InfoModal — contextual help or detail views
- SyncStatusModal — real-time progress
- CharacterCard — character display

## Target Platforms
1. Desktop browser (primary use — managing library, configuring sync)
2. Steam Deck browser (secondary — ~1280×800, touchpad + touch input)

Steam Deck requirements:
- Min touch target: 44×44px (min-h-[44px] min-w-[44px])
- Min interactive text: text-sm (never text-xs for interactive elements)
- Responsive: grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 for card grids
- Overflow: min-w-0 truncate for text in constrained columns
- Long lists: overflow-y-auto max-h-[...] not infinite page growth
- Modal width: w-full max-w-lg mx-4 (safe on all viewports)

## UX Principles
- Destructive actions: always behind ConfirmDialog, surface the consequence in the message
- Loading states: skeleton or spinner — never show stale data as current
- Empty states: two lines — what's empty + what to do about it
- Form errors: inline below field, text-red-400 text-sm
- Success: Sonner toast, not page reload
- Section spacing: space-y-6 between major sections
