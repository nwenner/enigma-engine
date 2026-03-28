# Codebase Structure

**Analysis Date:** 2026-03-28

## Directory Layout

```
enigma-engine/
├── backend/                    # FastAPI Python backend
│   ├── main.py                 # App entry point — router registration + lifespan
│   ├── config.py               # Pydantic settings (data_dir, secret_key, etc.)
│   ├── database.py             # SQLAlchemy async engine, session factory, init_db()
│   ├── models.py               # All SQLAlchemy ORM models (14 tables)
│   ├── requirements.txt        # Python dependencies
│   ├── routers/                # FastAPI APIRouter modules (one per domain)
│   └── services/               # Business logic modules
│       └── item_parsing/       # Self-contained D2R .d2i binary parser package
│           └── tables/         # Static lookup tables (Huffman, item types, stats)
├── frontend/                   # React TypeScript SPA
│   ├── src/
│   │   ├── App.tsx             # Root component — sidebar, routing, SSE hook mount
│   │   ├── main.tsx            # React entry point
│   │   ├── index.css           # Tailwind + custom D2 theme styles
│   │   ├── pages/              # Full-page route components
│   │   ├── components/         # Shared UI components
│   │   ├── api/
│   │   │   ├── client.ts       # Axios instance (baseURL: /api)
│   │   │   ├── hooks.ts        # All TanStack Query hooks
│   │   │   ├── types.ts        # TypeScript API response types
│   │   │   └── useEventStream.ts  # SSE listener hook
│   │   └── utils/
│   │       └── dates.ts        # Date formatting helpers
│   ├── dist/                   # Built output (served by FastAPI in production)
│   └── package.json
├── data/                       # Docker volume mount — all persistent runtime data
│   ├── backups/
│   │   ├── pc/                 # Snapshots from Windows PC
│   │   ├── deck/               # Snapshots from Steam Deck
│   │   └── mothership/         # Snapshots from the app vault itself (grail/stash ops)
│   ├── keys/                   # SSH private key files (uploaded via UI)
│   ├── staging/                # Temporary staging for reward item injection
│   └── tmp/                    # Scratch space for SFTP downloads
├── tests/                      # pytest test suite
│   ├── fixtures/               # Shared test fixture files (real .d2s/.d2i binaries)
│   ├── item_parsing/           # Unit tests for the item_parsing package
│   │   └── fixtures/           # Binary stash fixtures + ITEM_DESCRIPTIONS.md
│   └── quest_parsing/          # Unit tests for quest section parsing
├── scripts/                    # One-off developer scripts (analysis, generation)
├── Dockerfile                  # Multi-stage build (node:22-alpine → python:3.12-slim)
├── docker-compose.yml          # Single-service compose; mounts ./data and ~/.aws
├── pytest.ini                  # asyncio_mode = auto
└── .planning/                  # GSD planning documents (not committed as source)
    └── codebase/
```

## Directory Purposes

**`backend/routers/`:**
- Purpose: One file per feature domain; each file defines a FastAPI `APIRouter` and all request/response Pydantic models for that domain
- Contains: `sync.py`, `settings.py`, `characters.py`, `backups.py`, `history.py`, `grail.py`, `stash.py`, `seasons.py`, `rewards.py`, `demon.py`, `boss_summon.py`, `autosync.py`, `notifications.py`, `events.py`
- Key files: `sync.py` (largest, most complex — check-in + push + compare), `seasons.py` (30KB — full season CRUD + milestone eval), `stash.py` (21KB — vault operations)

**`backend/services/`:**
- Purpose: Domain logic decoupled from HTTP concerns; called by routers
- Contains: `auto_sync.py` (background watcher), `backup_manager.py` (snapshot + SFTP orchestration), `ssh_client.py` (paramiko wrapper), `d2s_parser.py` (.d2s character file parser), `grail_service.py`, `stash_service.py`, `seasons_service.py`, `demon_service.py`, `boss_summon_service.py`, `notify.py` (AWS SES), `event_bus.py` (SSE pub/sub), `catalog_lookup.py`, `item_export.py`
- Key files: `auto_sync.py` (29KB), `backup_manager.py` (20KB), `stash_service.py` (25KB)

**`backend/services/item_parsing/`:**
- Purpose: Self-contained binary parser for D2R Modern `.d2i` shared stash files
- Contains: `__init__.py` (public API), `models.py` (dataclasses), `bit_reader.py`, `huffman.py`, `item_flags.py`, `item_fields.py`, `item_names.py`, `item_stats.py`, `stash_format.py`
- Key files: `stash_format.py` (16KB — parse + serialize + item manipulation), `item_stats.py` (23KB — stat parsing), `item_fields.py` (7KB — bit-level field parsing)

**`backend/services/item_parsing/tables/`:**
- Purpose: Static lookup data for the parser — never contains logic
- Contains: `huffman_codes.py`, `item_types.py` (21KB), `affixes.py` (32KB), `rare_names.py`, `stat_widths.py` (18KB), `runewords.py`, `rune_effects.py` (17KB)

**`frontend/src/pages/`:**
- Purpose: One file per navigation route; each page manages its own data fetching via hooks
- Contains: `Dashboard.tsx` (26KB — main sync UI), `Seasons.tsx` (74KB — largest), `Stash.tsx` (45KB), `Grail.tsx` (26KB), `Settings.tsx` (27KB), `Rewards.tsx` (20KB), `BossPortals.tsx` (11KB), `Backups.tsx` (11KB), `Characters.tsx` (7KB), `History.tsx` (5KB), `Demon.tsx` (9KB)

**`frontend/src/components/`:**
- Purpose: Shared UI primitives used across pages
- Contains: `CharacterCard.tsx`, `Collapsible.tsx`, `ConfirmDialog.tsx`, `InfoModal.tsx`, `SyncStatusModal.tsx`, `TagInput.tsx`

**`frontend/src/api/`:**
- Purpose: All server communication — hooks encapsulate queries and mutations; types define the API contract
- Key files: `hooks.ts` (33KB — all TanStack Query hooks), `types.ts` (10KB — all API response types), `client.ts` (axios instance), `useEventStream.ts` (SSE listener)

**`data/backups/`:**
- Purpose: On-disk immutable snapshots; one subdirectory per snapshot, named `{timestamp}_{label}/`
- Generated: Yes — by `create_snapshot()` and pre-operation backup helpers
- Committed: No — `.gitignore` excludes runtime data

**`data/keys/`:**
- Purpose: SSH private key files uploaded via the Settings UI
- Generated: Yes — via `POST /api/settings/upload-key/{machine}`
- Committed: No

## Key File Locations

**Entry Points:**
- `backend/main.py`: FastAPI app, router registration, DB init, watcher task spawn
- `frontend/src/main.tsx`: React root mount
- `frontend/src/App.tsx`: Router setup, sidebar, SSE + toast hooks

**Configuration:**
- `backend/config.py`: `Settings` class (data_dir, secret_key, derived paths)
- `backend/database.py`: DB URL, engine, session factory, `init_db()` with inline migrations
- `docker-compose.yml`: Port mapping, volume mounts, env_file

**Core Logic:**
- `backend/services/backup_manager.py`: `create_snapshot()`, `push_snapshot_to_machine()`, `run_sync()`
- `backend/services/auto_sync.py`: `run_auto_sync_watcher()` — the poll loop
- `backend/services/ssh_client.py`: `get_sftp()` context manager, `check_d2r_running()`
- `backend/services/item_parsing/stash_format.py`: `parse_stash()`, `serialize_stash()`, `insert_item_into_page()`
- `backend/services/d2s_parser.py`: `parse_d2s()` for character `.d2s` files

**Domain Services:**
- `backend/services/grail_service.py`: Grail hook, deposit/retrieve
- `backend/services/stash_service.py`: Stash view, gold vault, item vault
- `backend/services/seasons_service.py`: Milestone detection, season start/end
- `backend/services/demon_service.py`: Demon bind/restore
- `backend/services/boss_summon_service.py`: Boss portal unlock tracking

**Testing:**
- `tests/` — all pytest tests
- `tests/item_parsing/` — pure-Python tests (no Docker needed)
- `tests/fixtures/` — real binary `.d2s` and `.d2i` files used by integration tests
- `pytest.ini` — `asyncio_mode = auto`

## Naming Conventions

**Files:**
- Backend Python: `snake_case.py` — service files named `{domain}_service.py`, router files named `{domain}.py`
- Frontend TypeScript: `PascalCase.tsx` for pages/components, `camelCase.ts` for utilities and API files

**Directories:**
- Backend: `snake_case/` (all lowercase)
- Frontend: `camelCase/` for `api/`, `utils/`; no convention enforced on `pages/` and `components/` (both are PascalCase files in lowercase dirs)

## Where to Add New Code

**New backend feature domain:**
- Router: create `backend/routers/{domain}.py` with an `APIRouter`; register in `backend/main.py`
- Service: create `backend/services/{domain}_service.py` for business logic
- Models: add ORM class to `backend/models.py`; add migration in `backend/database.py::init_db()`

**New frontend page:**
- Page component: `frontend/src/pages/{PageName}.tsx`
- Add route in `frontend/src/App.tsx` `<Routes>` block
- Add nav entry in `NAV_ITEMS` array in `frontend/src/App.tsx`
- API hooks: add to `frontend/src/api/hooks.ts`
- Types: add to `frontend/src/api/types.ts`

**New API hook:**
- Add `useXxx()` query or mutation to `frontend/src/api/hooks.ts`
- Add response type to `frontend/src/api/types.ts`

**New item parser table:**
- Add to `backend/services/item_parsing/tables/` as a `.py` file with a module-level dict/list
- Import in the appropriate parser module (`item_fields.py`, `item_names.py`, etc.)

**New snapshot backup label:**
- Add label string constant to the relevant service
- Add retention logic in `backup_manager.py` prune helpers (group by label type)

**New DB model:**
- Add ORM class to `backend/models.py`
- Add `CREATE TABLE` migration block in `backend/database.py::init_db()` using try/except ALTER TABLE pattern

**Shared UI component:**
- Add to `frontend/src/components/{ComponentName}.tsx`

**Utilities:**
- Backend: add to relevant service module or create `backend/services/{name}.py`
- Frontend: add to `frontend/src/utils/{name}.ts`

## Special Directories

**`data/`:**
- Purpose: All persistent runtime data — SQLite DB, binary snapshots, SSH keys
- Generated: Yes (by running app)
- Committed: No (`.gitignore`)
- Volume mounted at `/app/data` inside Docker

**`frontend/dist/`:**
- Purpose: Production build output from `npm run build`
- Generated: Yes (by Dockerfile stage 1)
- Committed: No

**`scripts/`:**
- Purpose: Developer analysis and one-off generation scripts (not run in production)
- Generated: No
- Committed: Yes

**`.planning/`:**
- Purpose: GSD planning documents — codebase analysis, phase plans
- Generated: By Claude GSD commands
- Committed: Up to developer discretion
