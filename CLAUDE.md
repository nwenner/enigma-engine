# Enigma Engine — Claude Instructions

## CRITICAL: Always work on Nick's branch

**Never make code changes in a git worktree.** Always write files to the canonical repo path: `/Users/nickwenner/Dev/repos/enigma-engine/`.

If the conversation was launched inside a worktree (the working directory path contains `.claude/worktrees/`), you MUST still write all code changes to the main repo path. Use absolute paths like `/Users/nickwenner/Dev/repos/enigma-engine/backend/...` — never relative paths that resolve into the worktree.

When spawning subagents, always pass the canonical repo path explicitly in the prompt. Do NOT pass `isolation: "worktree"` to the Agent tool.

Nick handles all git operations (commit, push, branch). Do not run any git commands unless explicitly asked.

## Docker

Never run `docker compose down/up/restart`. Nick uses `./starth.sh` to restart the stack. To run tests:
```
docker run --rm -v /Users/nickwenner/Dev/repos/enigma-engine:/app -w /app enigma-engine-enigma-engine python3 -m pytest tests/ -q
```
Verbose: same command with `-v`. Build image: `docker compose build`.

## What It Is

Dockerized web app (FastAPI + React) that bidirectionally syncs Diablo 2 Resurrected `.d2s` save files between a Windows PC and Steam Deck, managed via a local LAN web UI.

## Architecture

**Sync model — "Vault as Mothership"**: The app is the canonical source of truth. Auto-sync watcher polls both machines every 30s; on D2R game-close (True→False transition) it creates a `game_close` snapshot and pushes to the destination automatically.

**Router / Service split**:
- `backend/routers/` — HTTP only: request parsing, response serialization, `Depends` injection. No business logic.
- `backend/services/` — All business logic. No FastAPI imports. Accept `AsyncSession` as a parameter; never create sessions directly (background tasks use `AsyncSessionLocal`).

**Data layer**:
- All ORM models live in `backend/models.py` (single file, `Column()` style SQLAlchemy).
- SQLite at `data/db.sqlite` via SQLAlchemy async + aiosqlite.
- Schema migrations: manual `ALTER TABLE` blocks in `backend/database.py::init_db()`.

**Frontend**:
- All TanStack Query hooks in `frontend/src/api/hooks.ts`.
- All TypeScript interfaces in `frontend/src/api/types.ts`.
- All routes registered in `frontend/src/App.tsx`.

**SSE push**: `backend/services/event_bus.py::emit()` → `frontend/src/api/useEventStream.ts`.

## Critical Rules

These are non-negotiable. Never skip them.

1. **Binary safety**: NEVER modify a `.d2s` or `.d2i` file without first creating a `BackupSnapshot` via `backup_manager.create_snapshot()`. One violation caused permanent save data loss on 2026-02-21.

2. **D2R running check**: ALWAYS verify D2R is not running before any file write. Return `409` if it is. Use the existing `check_d2r_running()` pattern.

3. **No new frameworks**: FastAPI + React + SQLAlchemy only. Do not add new dependencies without an explicit ask.

4. **TypeScript strict**: `noUnusedLocals` and `noUnusedParameters` are compile errors. Every declared variable and parameter must be used.

## Code Conventions

### Python (backend)

- `from __future__ import annotations` at the top of every file.
- Module-level logger in every file: `log = logging.getLogger(__name__)`.
- paramiko SSH/SFTP calls are synchronous — always wrap in `asyncio.to_thread`.
- `pytest-asyncio` is configured with `asyncio_mode = auto` — never add `@pytest.mark.asyncio`.

### TypeScript (frontend)

- Explicit generics on TanStack Query: `useQuery<MyType>`, `useMutation<Resp, Error, Input>`.
- Nullable backend fields map to `T | null` in TypeScript, never `T | undefined`.
- New pages go in `frontend/src/pages/PascalCase.tsx`; shared components in `frontend/src/components/PascalCase.tsx`.

## Key Files

```
backend/main.py                        FastAPI app entry — registers all routers under /api
backend/models.py                      All ORM models (add new models here)
backend/database.py                    Async engine, init_db() + manual ALTER TABLE migrations
backend/config.py                      Pydantic-settings, reads .env

backend/services/backup_manager.py    create_snapshot(), push_snapshot_to_machine()
backend/services/auto_sync.py         guard_mothership_write(), trigger_mothership_push()
backend/services/d2s_utils.py         _calculate_checksum()
backend/services/item_parsing/        Binary .d2i stash parsing package (parse_stash, serialize_stash)

frontend/src/App.tsx                   Routes + nav (BrowserRouter)
frontend/src/api/client.ts             Axios instance (baseURL: "/api", timeout 30s)
frontend/src/api/hooks.ts              All TanStack Query hooks
frontend/src/api/types.ts              All TypeScript interfaces
frontend/src/api/useEventStream.ts     SSE listener
```

## Testing Notes

- SQLAlchemy tests require the Docker image. `item_parsing` tests are pure Python (no Docker needed).
- Session mocks: always `AsyncMock()`, never a real session. Use `side_effect=[_result(v1), _result(v2)]` for multiple `execute()` calls.
- Patch functions that are imported inside a function body at the **source module**, not the consumer.
- `call_args[0]` = positional args tuple; `call_args[1]` = kwargs dict.
- Known pre-existing failures (ignore): 12 tests in `test_start_season.py` + `test_sync_router::TestDoCheckin`.

## Testing Requirements

**Every code change must be accompanied by unit tests. No exceptions.**

- New service functions → test the function directly in `tests/`
- New router endpoints → test via `AsyncClient` or mock the service
- New parser logic → test with known byte fixtures in `tests/item_parsing/`
- Bug fixes → add a regression test that would have caught the bug

**Coverage target: 90% or higher** for any file touched in the PR.

Run coverage (requires `docker compose build` once to pick up `pytest-cov`):
```
docker run --rm -v /Users/nickwenner/Dev/repos/enigma-engine:/app -w /app enigma-engine-enigma-engine python3 -m pytest tests/ --cov=backend --cov-report=term-missing --cov-fail-under=90 -q
```

Run coverage for a specific module:
```
docker run --rm -v /Users/nickwenner/Dev/repos/enigma-engine:/app -w /app enigma-engine-enigma-engine python3 -m pytest tests/ --cov=backend/services/item_parsing/stash_format --cov-report=term-missing -q
```

## Agent System

Six specialist sub-agents are defined in `.claude/agents/` and carry persistent project memory. See `agents.md` for the full reference on when to invoke each one.
