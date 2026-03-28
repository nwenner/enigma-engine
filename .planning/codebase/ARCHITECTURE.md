# Architecture

**Analysis Date:** 2026-03-28

## Pattern Overview

**Overall:** Monolithic containerized web app — FastAPI backend serving a React SPA from the same process, with a long-running background watcher task for auto-sync.

**Key Characteristics:**
- Single Docker container exposes port 8080; FastAPI serves both `/api/*` routes and React SPA static assets
- Async Python backend (asyncio + SQLAlchemy async) with synchronous SFTP calls offloaded to `asyncio.to_thread`
- Frontend communicates exclusively via REST (`/api/*`) plus one SSE stream (`/api/events/stream`) for real-time push
- All persistent state lives in SQLite at `data/db.sqlite` (volume-mounted); binary save files on disk at `data/backups/`
- "Vault as Mothership" model: the app is the canonical source of truth for save files between two remote machines

## Layers

**HTTP Routers (`backend/routers/`):**
- Purpose: Request validation, auth-agnostic endpoint definitions, response serialization
- Location: `backend/routers/`
- Contains: FastAPI `APIRouter` instances, Pydantic request/response models, thin orchestration calls
- Depends on: Services layer, `backend/database.py` (via `Depends(get_session)`), `backend/models.py`
- Used by: `backend/main.py` (registered at startup)

**Services (`backend/services/`):**
- Purpose: All business logic — sync orchestration, binary file parsing, stash manipulation, season rules
- Location: `backend/services/`
- Contains: Domain logic functions and async helpers; no FastAPI-specific code
- Depends on: `backend/models.py`, `backend/config.py`, `backend/database.py` (direct `AsyncSessionLocal` for background tasks)
- Used by: Routers, `auto_sync.py` background watcher

**Data Models (`backend/models.py`):**
- Purpose: SQLAlchemy ORM definitions — single source of truth for DB schema
- Location: `backend/models.py`
- Contains: All ORM classes (14 tables), no logic
- Depends on: SQLAlchemy base only
- Used by: All services and routers

**Item Parsing Package (`backend/services/item_parsing/`):**
- Purpose: Pure-Python deterministic bit-level parser for D2R Modern `.d2i` stash files
- Location: `backend/services/item_parsing/`
- Contains: `BitReader`/`BitWriter`, Huffman decoder, item field readers, stash format serializer, lookup tables
- Depends on: Nothing outside this package (self-contained)
- Used by: `grail_service.py`, `stash_service.py`, `item_export.py`

**Frontend (`frontend/src/`):**
- Purpose: React SPA — displays state from API, triggers mutations
- Location: `frontend/src/`
- Contains: Pages, shared components, API hooks (TanStack Query), TypeScript types
- Depends on: `/api` REST endpoints via axios, `/api/events/stream` SSE
- Used by: Served as static files by FastAPI after `npm run build`

**Background Watcher (`backend/services/auto_sync.py`):**
- Purpose: Long-running asyncio task polling both machines every 30s for D2R state transitions
- Location: `backend/services/auto_sync.py`
- Contains: Poll loop, conflict detection, device-online push logic, state persistence in Settings KV table
- Depends on: `ssh_client.py`, `backup_manager.py`, `event_bus.py`, Settings KV store
- Used by: `backend/main.py` lifespan (spawned as `asyncio.create_task` at startup)

## Data Flow

**Auto-Sync (game close detection):**

1. `auto_sync.py` poll loop fires every 30s via `asyncio.sleep`
2. `_check_d2r(machine)` → `asyncio.to_thread` → `paramiko` SSH → `check_d2r_running()` returns bool
3. On True→False transition (D2R just closed): checks for mtime conflicts via `_has_new_saves()`
4. No conflict → calls `create_snapshot()` in `backup_manager.py` → SFTP download + DB record
5. Then calls `push_snapshot_to_machine()` → SFTP upload to dest machine
6. On completion: `event_bus.emit("sync_complete")` → all SSE subscribers notified
7. Frontend `useEventStream()` hook receives SSE event → `queryClient.invalidateQueries()` → UI refresh

**Manual Check In (`POST /api/checkin`):**

1. Router `sync.py` → acquires `sync_lock` (module-level `asyncio.Lock`)
2. Calls `create_snapshot(session, machine, conn_kwargs, save_dir, label="manual")`
3. `backup_manager.py` → `asyncio.to_thread(_download_all)` → SFTP downloads all save files
4. Parses each `.d2s` via `d2s_parser.parse_d2s()` → upserts `Character` rows
5. Triggers grail hook (`grail_service.run_grail_hook()`) — reads tab 5 of `.d2i` stash
6. Triggers season milestones hook (`seasons_service.check_season_milestones()`)
7. Prunes old snapshots to retention limits per label type
8. Returns `BackupSnapshot` DB record as response

**Stash Read (local, no SSH):**

1. `GET /api/stash?mode=sc|hc` → `stash.py` router
2. `stash_service.fetch_stash_local()` → finds latest `manual`/`game_close` snapshot on disk
3. Reads `.d2i` file from local snapshot path
4. `item_parsing.parse_stash(bytes, hardcore)` → `ParsedStash` dataclass
5. Returns JSON response with items per tab

**Stash Write (live SFTP):**

1. Write operation (gold deposit/item store/retrieve) → creates `pre_*` backup snapshot first
2. Downloads live stash file via SFTP → parses → modifies in memory
3. `serialize_stash(stash)` → bytes → uploads via SFTP
4. Updates local snapshot file to reflect new state

**State Management:**
- Backend state: SQLite DB for structured data; `data/backups/{machine}/{timestamp}_{label}/` for binary snapshots
- Auto-sync state: persisted as JSON in `Settings` KV table under key `autosync_state`
- Frontend state: TanStack Query cache; invalidated by SSE events or mutation `onSuccess` callbacks

## Key Abstractions

**BackupSnapshot:**
- Purpose: Immutable record of a downloaded save directory at a point in time
- Examples: `backend/models.py` `BackupSnapshot`, snapshot dirs at `data/backups/pc/20260328T103730Z_manual/`
- Pattern: Created before every mutation as safety record; labeled (`manual`, `game_close`, `pre_sync`, `pre_grail_*`, `pre_vault_*`, `season_archive`) for retention-group pruning

**create_snapshot():**
- Purpose: Central function for downloading + recording any machine's save state
- Examples: `backend/services/backup_manager.py::create_snapshot()`
- Pattern: Accepts `session`, `machine`, `conn_kwargs`, `save_dir`, `label`; SFTP downloads run in `asyncio.to_thread`; always parses `.d2s` files and upserts Characters (unless `update_characters=False`)

**Settings KV Store:**
- Purpose: Generic key/value table storing SSH credentials (Fernet-encrypted), auto-sync state, notification config, and feature flags
- Examples: `backend/models.py::Settings`, `backend/routers/settings.py::_get_setting()`, `_get_conn_kwargs()`
- Pattern: All settings read via `_get_setting(session, key)` helper; passwords encrypted via Fernet derived from `SECRET_KEY`

**ParsedStash / ParsedItem:**
- Purpose: Immutable dataclass tree representing a parsed `.d2i` file
- Examples: `backend/services/item_parsing/models.py`
- Pattern: Created by `parse_stash()`, modified by `remove_items_from_page()` / `insert_item_into_page()`, serialized back to bytes by `serialize_stash()`

**Event Bus:**
- Purpose: In-process pub/sub for SSE push to connected browsers
- Examples: `backend/services/event_bus.py`
- Pattern: `emit(event_type, **data)` from any service; `subscribe()` called by SSE endpoint per connection; fire-and-forget (QueueFull silently dropped)

## Entry Points

**FastAPI App:**
- Location: `backend/main.py`
- Triggers: `uvicorn backend.main:app --host 0.0.0.0 --port 8080`
- Responsibilities: Registers all routers under `/api`, mounts React SPA static files, runs `init_db()` and spawns `run_auto_sync_watcher()` in lifespan

**React App:**
- Location: `frontend/src/main.tsx`
- Triggers: Browser loads `/` (served by SPA fallback route in `main.py`)
- Responsibilities: Mounts `<App>`, sets up React Router, TanStack Query client; `useEventStream()` and `useSyncToasts()` are mounted at app root

**Auto-Sync Watcher:**
- Location: `backend/services/auto_sync.py::run_auto_sync_watcher()`
- Triggers: `asyncio.create_task()` at app lifespan start
- Responsibilities: Polls machines, fires check-ins and pushes automatically, writes state to DB, emits SSE events

## Error Handling

**Strategy:** Surface errors to API callers via HTTP exceptions; background tasks log and continue; binary file operations backed by mandatory pre-operation snapshots.

**Patterns:**
- Router layer raises `HTTPException(status_code=..., detail=...)` for user-facing errors
- SFTP errors wrapped in `SSHConnectionError`; caught in routers and converted to 503/400 responses
- `D2SParseError` caught at sync time; logged as warning; that character skipped
- `sync_lock` (`asyncio.Lock`) in sync router prevents concurrent sync operations from corrupting state
- All stash/grail write operations: create `pre_*` backup → verify D2R not running → then modify

## Cross-Cutting Concerns

**Logging:** Standard Python `logging` module; each module gets `log = logging.getLogger(__name__)`; no centralized log aggregation

**Validation:** Pydantic models on all router request/response shapes; input validated at HTTP boundary

**Authentication:** None — app is designed for LAN use; no auth on any endpoint; paramiko uses `AutoAddPolicy` (accepts all host keys)

**Concurrency:** SFTP calls are synchronous (paramiko); always run via `asyncio.to_thread()` to avoid blocking the event loop; `sync_lock` prevents concurrent sync ops; sessions opened via `AsyncSessionLocal()` context managers (no shared session across requests)
