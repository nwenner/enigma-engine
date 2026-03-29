# Feature Planner Memory — Enigma Engine

## Implemented Features (complete as of 2026-03-29)
1. Bidirectional sync — manual check-in + push, conflict detection
2. Auto-sync watcher — game-close → auto snapshot + push; device-online → auto push
3. Backup/snapshot system — 14 label types, per-group retention rules
4. Character tracking — season-scoped, soft-archived on season end, class_id 0-7
5. SSH/SFTP settings — Fernet-encrypted passwords, key file upload, KV store
6. Holy Grail tracker — deposit/retrieve via tab 5, catalog seeding
7. Item Vault — snapshot-based stash view, gold vault (bypasses 12.5M cap), item save/retrieve
8. Seasons — CRUD, milestone types, achievement evaluation, stats tracking
9. Season Rewards — stash-based reward item extraction + claim flow
10. Demon Vault — Warlock bound demon save/restore (empirically discovered `lf` section)
11. Map Seeds — read seed from .d2s, named library with tags, apply to any character
12. Boss Portal tracking — per-difficulty portal unlock state

## Key Architectural Decisions to Respect
- Global vs season-scoped: Seeds, Settings, GrailCatalog are global; Characters, VaultItems, Milestones are season-scoped
- Snapshot reads: read operations use local vault snapshot, NOT live SSH
- Snapshot only after write: after applying a seed/demon/item, take new snapshot — no auto-push
- Binary safety: BackupSnapshot ALWAYS before any .d2s/.d2i write
- No new frameworks: FastAPI + React + SQLAlchemy + existing deps only
- Single container: backend serves React SPA + API — no separate frontend server

## Analogous Features (use as templates when planning new ones)
- New single-resource domain library (save/restore pattern): → seeds.py + seed_service.py + Seeds.tsx
- Binary section read/write (empirical format): → demon_service.py + demon.py + Demon.tsx
- Tracked item library with deposit/retrieve: → grail_service.py + grail.py + Grail.tsx
- Snapshot-based view + write operations: → stash_service.py + stash.py + Stash.tsx
- Season-scoped tracking with milestones: → seasons_service.py + seasons.py + Seasons.tsx

## Scoping Questions to Always Ask
1. Season-scoped or global (persists across seasons)?
2. Read-only or does it write to save files?
3. Which machines involved (PC, Steam Deck, both, vault-only)?
4. Triggered manually or automatically (on sync/game-close)?
5. What does "done" look like in the UI?
