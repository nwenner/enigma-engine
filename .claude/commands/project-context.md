Enigma Engine project context — load this for a full project briefing.

## What It Is
Dockerized web app (FastAPI + React, single Docker container on port 8080) that bidirectionally syncs Diablo 2 Resurrected `.d2s` save files between a Windows PC and Steam Deck. Manages sync state, backups, character tracking, Holy Grail, Item Vault, Demon Vault, Map Seeds, and Seasons — all via a local LAN web UI.

## Stack
- Backend: Python 3.12 + FastAPI + SQLAlchemy async + aiosqlite (SQLite at data/db.sqlite)
- Frontend: React 18 + TypeScript strict + Vite + Tailwind + TanStack Query v5 + axios
- SSH/SFTP: paramiko (sync calls, always wrapped in asyncio.to_thread)
- Container: Docker multi-stage build, docker-compose, persistent volume at /app/data

## Architecture
- "Vault as Mothership": app is canonical source of truth between two remote machines (PC + Steam Deck)
- Router layer (backend/routers/): thin HTTP — request parsing, response serialization, Depends injection only
- Service layer (backend/services/): all business logic, no FastAPI imports
- All models in backend/models.py (single file, Column() style SQLAlchemy)
- All frontend hooks in frontend/src/api/hooks.ts (TanStack Query), all types in types.ts
- SSE push via backend/services/event_bus.py::emit() → frontend useEventStream hook

## Features Implemented
1. Bidirectional sync (manual check-in + push, auto-sync watcher)
2. Auto-sync watcher (game-close detection → auto snapshot + push to dest)
3. Backup/snapshot system (14 label types, per-group retention)
4. Character tracking (season-scoped, soft-archived on season end)
5. SSH/SFTP settings (Fernet-encrypted passwords, key file upload)
6. Holy Grail tracker (deposit/retrieve via stash tab 5)
7. Item Vault (snapshot-based stash view, gold vault bypass, item save/retrieve)
8. Seasons (CRUD, milestone tracking, achievement evaluation)
9. Season Rewards (stash-based reward item claim flow)
10. Demon Vault (Warlock bound demon — empirically discovered `lf` section)
11. Map Seeds (read seed from .d2s, named library, apply to any character)
12. Boss Portal tracking

## Critical Constraints
- **Binary safety**: NEVER modify .d2s or .d2i without creating a BackupSnapshot first (non-negotiable)
- **D2R running check**: ALWAYS verify D2R is not running before any file write → 409 if running
- **No new frameworks**: FastAPI + React + SQLAlchemy only
- **TypeScript strict**: noUnusedLocals + noUnusedParameters are compile errors

## Key File Paths
- backend/main.py — FastAPI entry, registers all routers under /api
- backend/models.py — all 14+ ORM models
- backend/database.py — async engine, init_db() with manual ALTER TABLE migrations
- backend/services/backup_manager.py — create_snapshot(), push_snapshot_to_machine()
- backend/services/auto_sync.py — guard_mothership_write(), trigger_mothership_push()
- backend/services/d2s_utils.py — _calculate_checksum()
- frontend/src/api/hooks.ts — all TanStack Query hooks
- frontend/src/api/types.ts — all TypeScript interfaces
- frontend/src/App.tsx — routes + nav (BrowserRouter)
- .claude/agents/ — custom specialist agents
- .claude/agent-memory/ — persistent agent memories (project-scoped)
