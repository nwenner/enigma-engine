# Backend Expert Memory — Enigma Engine

## Routers (backend/routers/) — 16 total, all registered in main.py under /api
- sync.py — checkin, push, compare, preflight, sync status; has module-level sync_lock (asyncio.Lock)
- characters.py — list, refresh, delete
- backups.py — list snapshots, restore
- history.py — sync event logs
- settings.py — SSH config, key upload; exports _get_conn_kwargs(), _get_setting()
- autosync.py — enable/disable/status of background watcher
- notifications.py — notification queue and delivery
- grail.py — deposit, retrieve, reset, catalog management
- stash.py (21KB) — stash view, gold vault deposit/withdraw, item vault store/retrieve
- seasons.py (30KB) — season CRUD, milestone eval, stats, largest router
- rewards.py — reward claim flow (extract-from-stash, assign, claim)
- demon.py — save/restore Warlock bound demon
- seeds.py — read current seed, library CRUD, apply seed to character
- boss_summon.py — portal unlock tracking
- events.py — SSE stream endpoint

## Key Services and Their Exports
- backup_manager.py: `create_snapshot(session, machine, conn_kwargs, save_dir, label)`, `get_latest_snapshot(session)`, `push_snapshot_to_machine()`
- ssh_client.py: `sftp_connect(conn_kwargs)` context manager, `check_d2r_running(conn_kwargs) → bool`
- auto_sync.py: `run_auto_sync_watcher()`, `guard_mothership_write(session)`, `trigger_mothership_push(session, bg)`
- d2s_parser.py: `parse_character(path)`, `read_map_seed(data) → int`, `write_map_seed(data, seed) → bytes`
- d2s_utils.py: `_calculate_checksum(data) → int`
- seed_service.py: `apply_seed_to_snapshot(session, saved_seed, character, bg)`
- demon_service.py: `read_demon(path)`, `save_demon(session, ...)`, `restore_demon_to_d2s(session, ...)`
- grail_service.py: `deposit_tab5(session, ...)`, `retrieve_item_to_tab5(session, ...)`
- stash_service.py: `fetch_stash_local(session, mode)`, gold ops, item vault ops
- seasons_service.py: milestone evaluation, season state transitions
- event_bus.py: `emit(event_type, **data)` — SSE push to connected browsers
- item_parsing/: `parse_stash(path, hardcore)`, `serialize_stash(stash)`, `insert_item_into_page(page, item)`

## Critical Rules
- **Working directory**: ALWAYS write files to the canonical repo path `/Users/nickwenner/Dev/repos/enigma-engine/`. If launched from a worktree (path contains `.claude/worktrees/`), use absolute paths to the main repo. Never write code into a worktree.
- Binary safety: `create_snapshot()` BEFORE any .d2s/.d2i write — always
- D2R check: `check_d2r_running(conn_kwargs)` before file writes → raise HTTPException(409) if True
- SFTP: always `await asyncio.to_thread(sftp_func, ...)` — paramiko is synchronous
- BackupSnapshot labels: use `pre_<feature>_<operation>` (e.g., `pre_seed_restore`, `pre_demon_restore`)

## Test Patterns (pytest + pytest-asyncio, asyncio_mode=auto)
```python
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
pytest.importorskip("sqlalchemy", reason="run inside Docker")

def _result(value):
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    r.scalars.return_value.all.return_value = value if isinstance(value, list) else [value]
    return r

# Single execute:  session.execute = AsyncMock(return_value=_result(obj))
# Multiple:        session.execute = AsyncMock(side_effect=[_result(v1), _result(v2)])
# Patch at source: patch("backend.services.foo.bar_func")
# SFTP mock:       patch("asyncio.to_thread", new_callable=AsyncMock)
# Multi-context:   with (patch("a") as x, patch("b") as y, patch("c") as z):
```
Run: `docker run --rm -v $(pwd):/app -w /app enigma-engine-enigma-engine python3 -m pytest tests/ -q`

## Pydantic Conventions
- Request: `MyResourceCreateRequest(BaseModel)` with Optional[str] fields
- Response: `MyResourceResponse(BaseModel)` with `model_config = {"from_attributes": True}`
- Always `Optional[T]` not `T | None` in Pydantic models
- `from __future__ import annotations` in every file
- Module logger: `log = logging.getLogger(__name__)`
