# Coding Conventions

**Analysis Date:** 2026-03-28

## Naming Patterns

**Python Files:**
- Services: `snake_case.py` — e.g., `backup_manager.py`, `grail_service.py`, `auto_sync.py`
- Routers: `snake_case.py` matching resource name — e.g., `grail.py`, `sync.py`, `seasons.py`
- Models: singular module `models.py` at `backend/models.py`
- Parser subpackage: `item_parsing/` with focused sub-modules (`bit_reader.py`, `item_fields.py`)

**TypeScript Files:**
- Pages: `PascalCase.tsx` — e.g., `Dashboard.tsx`, `BossPortals.tsx`, `Stash.tsx`
- Components: `PascalCase.tsx` — e.g., `SyncStatusModal.tsx`, `ConfirmDialog.tsx`
- API layer: `camelCase.ts` — `hooks.ts`, `client.ts`, `types.ts`, `useEventStream.ts`

**Python Functions:**
- Public functions: `snake_case` — e.g., `create_snapshot()`, `push_snapshot_to_machine()`
- Private helpers: `_snake_case` with leading underscore — e.g., `_prune_backups()`, `_sftp_download()`, `_get_conn_kwargs()`
- Async functions use same naming convention as sync functions

**Python Variables:**
- `snake_case` throughout — `conn_kwargs`, `snap_path`, `source_machine`
- Constants: `UPPER_SNAKE_CASE` — `PORTAL_TAB_INDEX`, `CONFLICT_THRESHOLD_SECONDS`, `PENDING_EXPIRY_DAYS`
- Module-level logger: always `log = logging.getLogger(__name__)`

**TypeScript Variables/Functions:**
- Variables and functions: `camelCase` — `fmtGold`, `fmtTimeRemaining`, `useCharacters`
- React hooks: `use` prefix + `PascalCase` — `usePreflight`, `useCheckIn`, `useSyncSummary`
- Constants: `UPPER_SNAKE_CASE` for configuration — `NAV_ITEMS`, `CLASS_ICONS`, `DIFF_LABEL`

**TypeScript Types/Interfaces:**
- Interfaces: `PascalCase` with descriptive suffix — `CharacterInfo`, `SyncStatusResponse`, `PreflightResponse`
- Type aliases: `PascalCase` — `Mode = Literal["sc", "hc"]`

**Python Classes:**
- SQLAlchemy models: `PascalCase` — `BackupSnapshot`, `SyncOperation`, `GrailCatalog`
- Pydantic models: `PascalCase` with `Request`/`Response` suffix — `CheckInRequest`, `SyncStatusResponse`
- Custom exceptions: `PascalCase` + `Error` suffix — `D2SParseError`, `SSHConnectionError`
- Test helper classes: `Test` prefix — `TestManualGameCloseRetention`, `TestPreSyncRetention`

## Code Style

**Formatting:**
- No formatter config detected (no `.prettierrc`, `biome.json`, or similar)
- Python: implicit 4-space indentation, PEP-8 style
- TypeScript: 2-space indentation in TSX/TS files

**TypeScript Compiler:**
- `strict: true` — all strict mode checks enabled
- `noUnusedLocals: true` and `noUnusedParameters: true` — unused code is a compile error
- `noFallthroughCasesInSwitch: true`
- Config: `frontend/tsconfig.json`

**Python Typing:**
- `from __future__ import annotations` at the top of every backend and test file
- Type hints on function signatures: `async def create_snapshot(session: AsyncSession, machine: str, ...) -> BackupSnapshot:`
- `| None` union syntax (Python 3.10+ style, enabled by `from __future__ import annotations`)
- `Optional[T]` still used in Pydantic models: `Optional[str]`, `Optional[datetime]`

## Import Organization

**Python order (observed in routers and services):**
1. `from __future__ import annotations` (always first if present)
2. Module docstring
3. Standard library: `asyncio`, `json`, `logging`, `shutil`, `datetime`, `pathlib`
4. Third-party: `fastapi`, `pydantic`, `sqlalchemy`
5. Internal: `backend.database`, `backend.models`, `backend.config`, `backend.services.*`, `backend.routers.*`

**Example from `backend/routers/sync.py`:**
```python
from __future__ import annotations

import asyncio
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.database import get_session, AsyncSessionLocal
from backend.models import SyncOperation, Character, Season, BackupSnapshot
from backend.services.backup_manager import run_sync, create_snapshot, push_snapshot_to_machine
```

**TypeScript imports:**
- React hooks first, then router imports, then internal API/component imports
- Types imported with `import type { ... }` when only used as types

**Path Aliases:**
- None — all imports use relative paths (`../api/hooks`, `./components/ConfirmDialog`)
- Backend uses absolute package paths (`backend.services.grail_service`)

## Module Documentation

**Docstrings at module level:**
- Service modules have a top-level docstring explaining purpose, called-by context, and sync/async notes
- Router modules list all endpoints with HTTP method + path in the docstring
- Example from `backend/services/backup_manager.py`:
  ```python
  """
  Backup manager: orchestrates the full download → backup → validate → upload → prune flow.

  Called by the sync router. Operations are async at the outer level (DB calls),
  but SFTP calls are synchronous (run via asyncio.to_thread).
  """
  ```

**Function docstrings:**
- Public API functions have docstrings with Args: blocks
- Private helpers have single-line docstrings describing the return value
- Example:
  ```python
  def _sftp_download(sftp, remote_path: str, local_path: Path) -> int:
      """Download a file over SFTP and return bytes transferred."""
  ```

## Section Dividers

Files use visual section headers with `─` characters for organization:
```python
# ─── Helpers ─────────────────────────────────────────────────────────────────
# ─── Response schemas ─────────────────────────────────────────────────────────
# ─── Happy-path tests ─────────────────────────────────────────────────────────
```
This pattern is used in both source files and test files throughout the project.

Similarly in TypeScript:
```typescript
// ─── Helpers ──────────────────────────────────────────────────────────────────
// ─── Season overview ──────────────────────────────────────────────────────────
// ─── Characters ─────────────────────────────────────────────────────────────
```

## Error Handling

**Backend pattern — HTTP errors raised directly in routers:**
```python
raise HTTPException(400, "Uploaded file is empty")
raise HTTPException(404, "Reward not found")
raise HTTPException(409, "Item is not currently in the grail vault — deposit it first")
raise HTTPException(500, str(e))
```

**Service-level errors use RuntimeError or custom exceptions:**
```python
class D2SParseError(Exception):
    pass

raise RuntimeError(f"Source snapshot directory not found: {source_dir}")
raise RuntimeError(f"Validation failed for {item['filename']}: {e}") from e
```

**Background tasks isolate hook failures:**
```python
try:
    await _run_grail_hook(...)
except Exception as _grail_err:
    log.warning("grail hook failed: %s", _grail_err)

try:
    await _run_season_hook(...)
except Exception as _season_err:
    log.warning("season hook failed: %s", _season_err)
```

**SSH/network failures are swallowed in background/watcher contexts:**
```python
except SSHConnectionError:
    log.warning("conn to %s failed", machine)
    return
except Exception as e:
    log.exception("push to %s failed: %s", machine, e)
    return
```

## Logging

**Framework:** Standard library `logging`, not `print()`

**Setup pattern (every service/router module):**
```python
log = logging.getLogger(__name__)
```

**Usage levels:**
- `log.info(...)` — normal operations (sync started, file counts)
- `log.warning(...)` — recoverable issues (hook failures, SSH timeouts, unexpected states)
- `log.exception(...)` — unexpected exceptions in catch blocks
- `log.debug(...)` — parser-level detail (bit positions, item parsing steps)

## SQLAlchemy Patterns

**Session injection via FastAPI dependency:**
```python
from backend.database import get_session
router = APIRouter(tags=["grail"])

@router.get("/grail/{mode}")
async def get_grail(mode: Mode, session: AsyncSession = Depends(get_session)):
    ...
```

**Queries use `select()` with chained `.where()` and `.order_by()`:**
```python
q = (
    select(BackupSnapshot)
    .where(BackupSnapshot.label.in_(["manual", "game_close"]))
    .order_by(BackupSnapshot.created_at.desc())
    .limit(1)
)
result = await session.execute(q)
snapshot = result.scalar_one_or_none()
```

**Background tasks with their own sessions use `AsyncSessionLocal` directly:**
```python
async with AsyncSessionLocal() as session:
    return await _get_setting(session, key)
```

## Pydantic Response Models

All router endpoints use explicit Pydantic `BaseModel` classes for request and response bodies. Fields use `Optional[T]` for nullable fields. Models live in the same router file where they are used (not in a separate schemas file).

```python
class SyncStatusResponse(BaseModel):
    id: int
    direction: str
    status: str
    error_message: Optional[str]
    started_at: datetime
    completed_at: Optional[datetime]
    file_count: int
```

## Frontend Patterns

**Data fetching — all via TanStack Query hooks in `frontend/src/api/hooks.ts`:**
```typescript
export function useCharacters(refetchInterval?: number) {
  return useQuery<CharacterInfo[]>({
    queryKey: ["characters"],
    queryFn: () => api.get("/characters").then((r) => r.data),
    refetchInterval,
  });
}
```

**Mutations invalidate query cache on success:**
```typescript
return useMutation<CharacterInfo[], Error, void>({
  mutationFn: () => api.post("/characters/refresh").then((r) => r.data),
  onSuccess: () => qc.invalidateQueries({ queryKey: ["characters"] }),
});
```

**Axios client (`frontend/src/api/client.ts`):**
- Single shared instance with `baseURL: "/api"` and `timeout: 30_000`

**TypeScript types are centralized in `frontend/src/api/types.ts`** — all API response shapes as interfaces.

**Tailwind styling:**
- Custom design tokens defined in `frontend/tailwind.config.ts`: `d2gold`, `d2bg-*` color palette, `font-diablo`
- All styling via Tailwind utility classes; no CSS modules or separate stylesheets (except global `index.css`)
- Inline `style={}` only for complex gradients/shadows that Tailwind can't express

---

*Convention analysis: 2026-03-28*
