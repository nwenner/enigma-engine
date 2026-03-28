<!-- GSD:project-start source:PROJECT.md -->
## Project

**Enigma Engine — Map Seed Milestone**

Enigma Engine is a self-hosted web app (FastAPI + React, Dockerized) that bidirectionally syncs Diablo 2 Resurrected `.d2s` save files between a Windows PC and Steam Deck. It manages sync state, backups, character tracking, a Holy Grail tracker, an Item Vault, and a Demon Vault — all accessible from a local web UI.

This milestone adds **Map Seed management**: read the procedurally-generated map seed from any character's save file, save desirable seeds to a named library with notes, and apply any saved seed to any character to reproduce a known-good farming layout.

**Core Value:** Save and restore D2R map seeds so known-good farming layouts are never lost.

### Constraints

- **Tech stack**: FastAPI + SQLAlchemy async (backend), React + TypeScript + TanStack Query + Tailwind (frontend) — no new frameworks
- **Binary safety**: NEVER modify a save file without creating a BackupSnapshot first — non-negotiable per established protocol
- **D2R running check**: Must verify D2R is not running before any file modification
- **Snapshot-based reads**: Read operations use the local vault snapshot, not live SSH, for consistency and speed
<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->
## Technology Stack

## Languages
- Python 3.12 - Backend API and all business logic (`backend/`)
- TypeScript 5.7 - Frontend SPA (`frontend/src/`)
- CSS (Tailwind utility classes) - Styling (`frontend/src/index.css`, component files)
## Runtime
- Python 3.12-slim (Docker image: `python:3.12-slim`)
- Node 22-alpine (Docker image: `node:22-alpine`, build stage only)
- Python: pip (no lockfile — `requirements.txt` pins exact versions)
- Node: npm with lockfile (`frontend/package-lock.json` present)
## Frameworks
- FastAPI 0.115.6 - Async REST API framework + static file serving for SPA
- uvicorn[standard] 0.34.0 - ASGI server, runs on port 8080
- React 18.3.1 - UI component library
- react-router-dom 7.1.1 - Client-side routing (BrowserRouter)
- TanStack Query (@tanstack/react-query) 5.62.7 - Server state, caching, refetch
- Vite 6.0.7 - Frontend dev server + production bundler
- TypeScript compiler (tsc) - Type checking before build (`tsc && vite build`)
- postcss + autoprefixer - CSS processing for Tailwind
## Key Dependencies
- pydantic 2.10.4 - Request/response validation, settings management
- pydantic-settings 2.7.0 - `Settings` class loaded from `.env` (`backend/config.py`)
- SQLAlchemy 2.0.36 - ORM with async engine (`backend/database.py`)
- aiosqlite 0.20.0 - Async SQLite driver for SQLAlchemy
- greenlet 3.1.1 - Required by SQLAlchemy async
- paramiko 3.5.0 - SSH/SFTP client for remote save file operations (`backend/services/ssh_client.py`)
- cryptography 44.0.0 - Fernet symmetric encryption for SSH passwords at rest (`backend/routers/settings.py`)
- python-multipart 0.0.20 - Multipart form data (SSH key file uploads)
- boto3 1.36.4 - AWS SDK, used exclusively for SES email notifications (`backend/services/notify.py`)
- axios 1.7.9 - HTTP client, configured with `baseURL: "/api"` and 30s timeout (`frontend/src/api/client.ts`)
- sonner 1.7.4 - Toast notification library (sync events, conflict alerts)
- pytest 8.x - Test runner
- pytest-asyncio 0.24 - Async test support (`asyncio_mode = auto` in `pytest.ini`)
## Configuration
- Configured via `.env` file (see `.env.example`)
- Required: `SECRET_KEY` — 32-char hex string used to derive Fernet key for password encryption
- Optional: `DATABASE_URL` — defaults to `sqlite+aiosqlite:///app/data/db.sqlite`; overridable for local dev
- Optional: `BACKUP_RETENTION_COUNT` — defaults to `10`
- Notification settings (AWS profile, SES addresses) stored in DB KV table, configured via Settings UI
- Docker multi-stage: `frontend-builder` (Node 22) + `runtime` (Python 3.12-slim) — `Dockerfile`
- Frontend build output copied from stage 1 to `frontend/dist/` in stage 2
- `docker-compose.yml` mounts `./data:/app/data` (persistent) and `~/.aws:/root/.aws:ro` (AWS credentials)
- `frontend/vite.config.ts` — dev proxy: `/api` → `http://localhost:8080`
- `frontend/tsconfig.json` — strict mode enabled, target ES2020, no path aliases
- `strict: true`, `noUnusedLocals: true`, `noUnusedParameters: true`, `noFallthroughCasesInSwitch: true`
## Platform Requirements
- Docker + docker-compose (app runs in container; `./starth.sh` used to start)
- Node 22 not required locally — only needed inside Docker build stage
- Single Docker container on port 8080
- Persistent volume at `/app/data` (SQLite DB, backups, SSH keys, tmp files)
- AWS credentials at `~/.aws` (required only if SES notifications are enabled)
- LAN-accessible; no TLS termination built in
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

## Naming Patterns
- Services: `snake_case.py` — e.g., `backup_manager.py`, `grail_service.py`, `auto_sync.py`
- Routers: `snake_case.py` matching resource name — e.g., `grail.py`, `sync.py`, `seasons.py`
- Models: singular module `models.py` at `backend/models.py`
- Parser subpackage: `item_parsing/` with focused sub-modules (`bit_reader.py`, `item_fields.py`)
- Pages: `PascalCase.tsx` — e.g., `Dashboard.tsx`, `BossPortals.tsx`, `Stash.tsx`
- Components: `PascalCase.tsx` — e.g., `SyncStatusModal.tsx`, `ConfirmDialog.tsx`
- API layer: `camelCase.ts` — `hooks.ts`, `client.ts`, `types.ts`, `useEventStream.ts`
- Public functions: `snake_case` — e.g., `create_snapshot()`, `push_snapshot_to_machine()`
- Private helpers: `_snake_case` with leading underscore — e.g., `_prune_backups()`, `_sftp_download()`, `_get_conn_kwargs()`
- Async functions use same naming convention as sync functions
- `snake_case` throughout — `conn_kwargs`, `snap_path`, `source_machine`
- Constants: `UPPER_SNAKE_CASE` — `PORTAL_TAB_INDEX`, `CONFLICT_THRESHOLD_SECONDS`, `PENDING_EXPIRY_DAYS`
- Module-level logger: always `log = logging.getLogger(__name__)`
- Variables and functions: `camelCase` — `fmtGold`, `fmtTimeRemaining`, `useCharacters`
- React hooks: `use` prefix + `PascalCase` — `usePreflight`, `useCheckIn`, `useSyncSummary`
- Constants: `UPPER_SNAKE_CASE` for configuration — `NAV_ITEMS`, `CLASS_ICONS`, `DIFF_LABEL`
- Interfaces: `PascalCase` with descriptive suffix — `CharacterInfo`, `SyncStatusResponse`, `PreflightResponse`
- Type aliases: `PascalCase` — `Mode = Literal["sc", "hc"]`
- SQLAlchemy models: `PascalCase` — `BackupSnapshot`, `SyncOperation`, `GrailCatalog`
- Pydantic models: `PascalCase` with `Request`/`Response` suffix — `CheckInRequest`, `SyncStatusResponse`
- Custom exceptions: `PascalCase` + `Error` suffix — `D2SParseError`, `SSHConnectionError`
- Test helper classes: `Test` prefix — `TestManualGameCloseRetention`, `TestPreSyncRetention`
## Code Style
- No formatter config detected (no `.prettierrc`, `biome.json`, or similar)
- Python: implicit 4-space indentation, PEP-8 style
- TypeScript: 2-space indentation in TSX/TS files
- `strict: true` — all strict mode checks enabled
- `noUnusedLocals: true` and `noUnusedParameters: true` — unused code is a compile error
- `noFallthroughCasesInSwitch: true`
- Config: `frontend/tsconfig.json`
- `from __future__ import annotations` at the top of every backend and test file
- Type hints on function signatures: `async def create_snapshot(session: AsyncSession, machine: str, ...) -> BackupSnapshot:`
- `| None` union syntax (Python 3.10+ style, enabled by `from __future__ import annotations`)
- `Optional[T]` still used in Pydantic models: `Optional[str]`, `Optional[datetime]`
## Import Organization
- React hooks first, then router imports, then internal API/component imports
- Types imported with `import type { ... }` when only used as types
- None — all imports use relative paths (`../api/hooks`, `./components/ConfirmDialog`)
- Backend uses absolute package paths (`backend.services.grail_service`)
## Module Documentation
- Service modules have a top-level docstring explaining purpose, called-by context, and sync/async notes
- Router modules list all endpoints with HTTP method + path in the docstring
- Example from `backend/services/backup_manager.py`:
- Public API functions have docstrings with Args: blocks
- Private helpers have single-line docstrings describing the return value
- Example:
## Section Dividers
## Error Handling
## Logging
- `log.info(...)` — normal operations (sync started, file counts)
- `log.warning(...)` — recoverable issues (hook failures, SSH timeouts, unexpected states)
- `log.exception(...)` — unexpected exceptions in catch blocks
- `log.debug(...)` — parser-level detail (bit positions, item parsing steps)
## SQLAlchemy Patterns
## Pydantic Response Models
## Frontend Patterns
- Single shared instance with `baseURL: "/api"` and `timeout: 30_000`
- Custom design tokens defined in `frontend/tailwind.config.ts`: `d2gold`, `d2bg-*` color palette, `font-diablo`
- All styling via Tailwind utility classes; no CSS modules or separate stylesheets (except global `index.css`)
- Inline `style={}` only for complex gradients/shadows that Tailwind can't express
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

## Pattern Overview
- Single Docker container exposes port 8080; FastAPI serves both `/api/*` routes and React SPA static assets
- Async Python backend (asyncio + SQLAlchemy async) with synchronous SFTP calls offloaded to `asyncio.to_thread`
- Frontend communicates exclusively via REST (`/api/*`) plus one SSE stream (`/api/events/stream`) for real-time push
- All persistent state lives in SQLite at `data/db.sqlite` (volume-mounted); binary save files on disk at `data/backups/`
- "Vault as Mothership" model: the app is the canonical source of truth for save files between two remote machines
## Layers
- Purpose: Request validation, auth-agnostic endpoint definitions, response serialization
- Location: `backend/routers/`
- Contains: FastAPI `APIRouter` instances, Pydantic request/response models, thin orchestration calls
- Depends on: Services layer, `backend/database.py` (via `Depends(get_session)`), `backend/models.py`
- Used by: `backend/main.py` (registered at startup)
- Purpose: All business logic — sync orchestration, binary file parsing, stash manipulation, season rules
- Location: `backend/services/`
- Contains: Domain logic functions and async helpers; no FastAPI-specific code
- Depends on: `backend/models.py`, `backend/config.py`, `backend/database.py` (direct `AsyncSessionLocal` for background tasks)
- Used by: Routers, `auto_sync.py` background watcher
- Purpose: SQLAlchemy ORM definitions — single source of truth for DB schema
- Location: `backend/models.py`
- Contains: All ORM classes (14 tables), no logic
- Depends on: SQLAlchemy base only
- Used by: All services and routers
- Purpose: Pure-Python deterministic bit-level parser for D2R Modern `.d2i` stash files
- Location: `backend/services/item_parsing/`
- Contains: `BitReader`/`BitWriter`, Huffman decoder, item field readers, stash format serializer, lookup tables
- Depends on: Nothing outside this package (self-contained)
- Used by: `grail_service.py`, `stash_service.py`, `item_export.py`
- Purpose: React SPA — displays state from API, triggers mutations
- Location: `frontend/src/`
- Contains: Pages, shared components, API hooks (TanStack Query), TypeScript types
- Depends on: `/api` REST endpoints via axios, `/api/events/stream` SSE
- Used by: Served as static files by FastAPI after `npm run build`
- Purpose: Long-running asyncio task polling both machines every 30s for D2R state transitions
- Location: `backend/services/auto_sync.py`
- Contains: Poll loop, conflict detection, device-online push logic, state persistence in Settings KV table
- Depends on: `ssh_client.py`, `backup_manager.py`, `event_bus.py`, Settings KV store
- Used by: `backend/main.py` lifespan (spawned as `asyncio.create_task` at startup)
## Data Flow
- Backend state: SQLite DB for structured data; `data/backups/{machine}/{timestamp}_{label}/` for binary snapshots
- Auto-sync state: persisted as JSON in `Settings` KV table under key `autosync_state`
- Frontend state: TanStack Query cache; invalidated by SSE events or mutation `onSuccess` callbacks
## Key Abstractions
- Purpose: Immutable record of a downloaded save directory at a point in time
- Examples: `backend/models.py` `BackupSnapshot`, snapshot dirs at `data/backups/pc/20260328T103730Z_manual/`
- Pattern: Created before every mutation as safety record; labeled (`manual`, `game_close`, `pre_sync`, `pre_grail_*`, `pre_vault_*`, `season_archive`) for retention-group pruning
- Purpose: Central function for downloading + recording any machine's save state
- Examples: `backend/services/backup_manager.py::create_snapshot()`
- Pattern: Accepts `session`, `machine`, `conn_kwargs`, `save_dir`, `label`; SFTP downloads run in `asyncio.to_thread`; always parses `.d2s` files and upserts Characters (unless `update_characters=False`)
- Purpose: Generic key/value table storing SSH credentials (Fernet-encrypted), auto-sync state, notification config, and feature flags
- Examples: `backend/models.py::Settings`, `backend/routers/settings.py::_get_setting()`, `_get_conn_kwargs()`
- Pattern: All settings read via `_get_setting(session, key)` helper; passwords encrypted via Fernet derived from `SECRET_KEY`
- Purpose: Immutable dataclass tree representing a parsed `.d2i` file
- Examples: `backend/services/item_parsing/models.py`
- Pattern: Created by `parse_stash()`, modified by `remove_items_from_page()` / `insert_item_into_page()`, serialized back to bytes by `serialize_stash()`
- Purpose: In-process pub/sub for SSE push to connected browsers
- Examples: `backend/services/event_bus.py`
- Pattern: `emit(event_type, **data)` from any service; `subscribe()` called by SSE endpoint per connection; fire-and-forget (QueueFull silently dropped)
## Entry Points
- Location: `backend/main.py`
- Triggers: `uvicorn backend.main:app --host 0.0.0.0 --port 8080`
- Responsibilities: Registers all routers under `/api`, mounts React SPA static files, runs `init_db()` and spawns `run_auto_sync_watcher()` in lifespan
- Location: `frontend/src/main.tsx`
- Triggers: Browser loads `/` (served by SPA fallback route in `main.py`)
- Responsibilities: Mounts `<App>`, sets up React Router, TanStack Query client; `useEventStream()` and `useSyncToasts()` are mounted at app root
- Location: `backend/services/auto_sync.py::run_auto_sync_watcher()`
- Triggers: `asyncio.create_task()` at app lifespan start
- Responsibilities: Polls machines, fires check-ins and pushes automatically, writes state to DB, emits SSE events
## Error Handling
- Router layer raises `HTTPException(status_code=..., detail=...)` for user-facing errors
- SFTP errors wrapped in `SSHConnectionError`; caught in routers and converted to 503/400 responses
- `D2SParseError` caught at sync time; logged as warning; that character skipped
- `sync_lock` (`asyncio.Lock`) in sync router prevents concurrent sync operations from corrupting state
- All stash/grail write operations: create `pre_*` backup → verify D2R not running → then modify
## Cross-Cutting Concerns
<!-- GSD:architecture-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd:quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd:debug` for investigation and bug fixing
- `/gsd:execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd:profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
