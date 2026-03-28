# Testing Patterns

**Analysis Date:** 2026-03-28

## Test Framework

**Runner:**
- pytest + pytest-asyncio
- Config: `pytest.ini` at project root
- `asyncio_mode = auto` — no `@pytest.mark.asyncio` decorator needed on any test
- `testpaths = tests`
- `pythonpath = .` — allows `from backend.services...` imports without install

**Assertion Library:**
- pytest built-in `assert` (no external assertion library)

**Run Commands:**
```bash
# Run all tests (must be inside Docker — SQLAlchemy/paramiko not installed locally)
docker run --rm -v $(pwd):/app -w /app enigma-engine-enigma-engine python3 -m pytest tests/ -v

# Quiet output (used by pre-commit hook)
docker run --rm -v $(pwd):/app -w /app enigma-engine-enigma-engine python3 -m pytest tests/ -q

# Specific file
docker run --rm -v $(pwd):/app -w /app enigma-engine-enigma-engine python3 -m pytest tests/test_backup_manager.py -v

# item_parsing tests only (pure Python — can run without Docker)
python3 -m pytest tests/item_parsing/ -v
```

## Test File Organization

**Location:** All tests live under `tests/` — no co-location with source files.

**Structure:**
```
tests/
├── __init__.py
├── fixtures/
│   └── Tald.d2s                        # Real .d2s fixture for d2s_parser tests
├── item_parsing/
│   ├── __init__.py
│   ├── conftest.py                      # session-scoped stash fixture
│   ├── fixtures/
│   │   ├── ModernSharedStashSoftCoreV2.d2i  # Real stash fixture
│   │   ├── ArsDulMephistos.d2i
│   │   ├── WarlockCodexSuperior.bin
│   │   └── ITEM_DESCRIPTIONS.md         # Hand-typed ground-truth guide
│   ├── test_item_parsing.py
│   ├── test_item_stats.py
│   ├── test_name_resolution.py
│   ├── test_stash_format.py
│   └── test_grail.py
├── quest_parsing/
│   ├── __init__.py
│   ├── fixtures/
│   │   └── Tald.d2s
│   └── test_quest_parsing.py
├── test_auto_sync.py
├── test_backup_manager.py
├── test_characters_upsert.py
├── test_claim_reward.py
├── test_d2s_parser.py
├── test_demon_vault.py
├── test_gold_milestone.py
├── test_integration_tald_season.py
├── test_item_extraction.py
├── test_milestone_edit.py
├── test_preflight.py
├── test_push_snapshot.py
├── test_seasons_router_helpers.py
├── test_seasons_service.py
├── test_start_season.py
├── test_stash_service.py
├── test_stash_vault.py
└── test_sync_router.py
```

**Naming:**
- Files: `test_<feature_or_module>.py`
- Test classes: `Test<FeatureOrBehavior>` (e.g., `TestManualGameCloseRetention`, `TestPreSyncRetention`)
- Test functions: `test_<behavior_description>` using descriptive snake_case

## Test Structure

**Suite Organization:**
```python
from __future__ import annotations

"""
Module-level docstring describing:
- What is under test
- Testing strategy (mock approach)
- How to run
"""

import pytest
pytest.importorskip("sqlalchemy", reason="SQLAlchemy not installed — run tests inside Docker")

from backend.services.backup_manager import _prune_backups

# ─── Helpers ─────────────────────────────────────────────────────────────────

def _snap(id: int, label: str = "manual", ...) -> MagicMock:
    """Create a minimal BackupSnapshot mock."""
    ...

def _session(snapshots: list[Any]) -> AsyncMock:
    """Return an AsyncSession mock whose execute().scalars().all() yields snapshots."""
    ...


# ─── Feature group 1 ──────────────────────────────────────────────────────────

class TestManualGameCloseRetention:
    async def test_deletes_excess_when_over_limit(self) -> None:
        """3 snapshots exist → keep newest 1, delete 2."""
        ...

    async def test_no_op_at_exact_limit(self) -> None:
        """Exactly 1 snapshot → nothing deleted."""
        ...
```

**Key structure rules:**
- Every test file starts with `from __future__ import annotations`
- Module docstring covers: what is tested, mock strategy, how to run
- Helper factory functions at module level (not inside test classes)
- Test classes group related behavior; no `setUp`/`tearDown` — state is per-test via helpers
- All async tests work without `@pytest.mark.asyncio` (covered by `asyncio_mode = auto`)
- Return type annotations on all test methods: `-> None`

## Docker Dependency Guard

Every test file that imports SQLAlchemy, paramiko, or other Docker-only deps uses:

```python
pytest.importorskip("sqlalchemy", reason="SQLAlchemy not installed — run tests inside Docker")
pytest.importorskip("paramiko", reason="paramiko not installed — run tests inside Docker")
```

This allows the test suite to be imported anywhere without import errors — tests are simply skipped when run outside Docker.

**Exception:** `tests/item_parsing/` and `tests/test_d2s_parser.py` are pure Python and can run locally.

## Mocking

**Framework:** `unittest.mock` — `AsyncMock`, `MagicMock`, `patch`, `call`

**Session mocking — always `AsyncMock`, never a real session:**

```python
# Single execute call returning scalar
def _session_returning(scalar_value) -> AsyncMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar_value
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result)
    session.add = MagicMock()   # session.add is synchronous
    return session

# Multiple execute calls (ordered side_effect)
def _multi_session() -> AsyncMock:
    result1 = MagicMock()
    result1.scalar_one_or_none.return_value = None   # first query: no season

    result2 = MagicMock()
    result2.scalar_one_or_none.return_value = None   # second query: no snapshot

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[result1, result2])
    return session

# scalars().all() pattern (list results)
def _session(snapshots: list) -> AsyncMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = snapshots
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result)
    return session
```

**Service/function patching with `patch` context manager:**
```python
with patch("backend.services.backup_manager.create_snapshot", mock_create), \
     patch("backend.services.backup_manager.asyncio.to_thread", AsyncMock(return_value=(0, 2))):
    await push_snapshot_to_machine(session, "deck", {}, "/saves", False)
```

**Rule:** Patch at the module where the function is imported/used, not the source module. Example: patch `backend.services.backup_manager.create_snapshot` when testing `push_snapshot_to_machine`, not `backend.services.backup_manager.create_snapshot` from its own module.

**SSH/SFTP mocking:**
```python
with patch("backend.services.backup_manager.ssh_mod.get_sftp") as mock_get_sftp, \
     patch("backend.services.backup_manager.ssh_mod.list_all_files", return_value=remote_files), \
     patch("backend.services.backup_manager.asyncio.to_thread",
           AsyncMock(side_effect=lambda fn, *a, **kw: fn())):
    mock_get_sftp.return_value.__enter__ = MagicMock(return_value=(MagicMock(), mock_sftp))
    mock_get_sftp.return_value.__exit__ = MagicMock(return_value=False)
```

**What to Mock:**
- DB session (`AsyncMock`)
- SSH/SFTP calls (patch `ssh_mod.get_sftp`, `ssh_mod.list_all_files`, `asyncio.to_thread`)
- Service functions called by the function under test
- `get_settings()` config when filesystem access is needed

**What NOT to Mock:**
- The function under test itself
- `pathlib.Path` operations — use `tmp_path` pytest fixture for real filesystem tests
- Pure logic in item_parsing package (no mocking needed — pure Python)

## Fixtures and Factories

**conftest.py (`tests/item_parsing/conftest.py`):**
```python
FIXTURE_SC = Path(__file__).parent / "fixtures" / "ModernSharedStashSoftCoreV2.d2i"

@pytest.fixture(scope="session")
def stash() -> ParsedStash:
    return parse_stash(FIXTURE_SC, hardcore=False)
```

The `session`-scoped stash fixture parses the fixture file once and shares it across all `item_parsing` tests.

**Module-level factory functions (preferred over fixtures for unit tests):**
```python
def _snap(id: int, label: str = "manual", source_machine: str = "pc") -> MagicMock:
    """Create a minimal BackupSnapshot mock."""
    s = MagicMock()
    s.id = id
    s.label = label
    s.source_machine = source_machine
    s.snapshot_path = f"backups/{source_machine}/snap_{id}"
    return s

def _char(level: int = 1, difficulty_active: int = 0, hardcore: bool = False, ...) -> MagicMock:
    """Return a mock object resembling a D2SCharacter."""
    c = MagicMock()
    c.level = level
    ...
    return c
```

**Real binary fixtures:**
- `tests/fixtures/Tald.d2s` — real D2R save file for d2s_parser tests
- `tests/item_parsing/fixtures/ModernSharedStashSoftCoreV2.d2i` — real stash (used by multiple test modules)
- `tests/item_parsing/fixtures/WarlockCodexSuperior.bin` — single item binary
- `tests/item_parsing/fixtures/ITEM_DESCRIPTIONS.md` — hand-typed ground-truth guide for what items should parse to
- `tests/quest_parsing/fixtures/Tald.d2s` — real save for quest parsing tests

**tmp_path fixture** (from pytest) used for filesystem tests that need writable directories.

## Coverage

**Requirements:** None enforced. No coverage threshold configured.

**No coverage tool configured** (`pytest-cov` not in dependencies).

## Test Types

**Unit Tests (majority):**
- Scope: single function or class method
- All external I/O mocked
- No real DB, no real SSH, no real file system (except `tmp_path` for deletion tests)
- Located in `tests/*.py` and `tests/item_parsing/*.py`

**Integration Tests (light):**
- `tests/test_integration_tald_season.py` — end-to-end season flow using real `.d2s` fixture
- `tests/item_parsing/test_stash_format.py::test_round_trip_identity` — real binary parse → serialize → compare

**Pure Binary Tests:**
- `tests/item_parsing/` — no DB dependency; test the `item_parsing` package against real `.d2i` fixtures
- Can run outside Docker: `python3 -m pytest tests/item_parsing/ -v`

**No E2E/browser tests.** No frontend tests (no vitest/jest configured in `frontend/package.json`).

## Common Patterns

**Async Testing:**
```python
async def test_pre_sync_snapshot_taken_before_push_thread(self) -> None:
    """create_snapshot must be called before asyncio.to_thread(_push) — strict ordering."""
    call_order: list[str] = []

    async def _track_create(**kwargs):
        call_order.append("create_snapshot")
        return MagicMock()

    async def _track_thread(fn):
        call_order.append("push_thread")
        return (0, 0)

    with patch("backend.services.backup_manager.create_snapshot", side_effect=_track_create), \
         patch("backend.services.backup_manager.asyncio.to_thread", side_effect=_track_thread):
        await push_snapshot_to_machine(session, "deck", {}, "/saves", False)

    assert call_order == ["create_snapshot", "push_thread"]
```

**Error/Exception Testing:**
```python
async def test_push_aborted_if_pre_sync_snapshot_fails(self) -> None:
    push_thread_called = False

    async def _track_thread(fn):
        nonlocal push_thread_called
        push_thread_called = True
        return (0, 0)

    with patch("backend.services.backup_manager.create_snapshot",
               AsyncMock(side_effect=RuntimeError("SFTP error during snapshot"))), \
         patch("backend.services.backup_manager.asyncio.to_thread", side_effect=_track_thread):
        with pytest.raises(RuntimeError, match="SFTP error during snapshot"):
            await push_snapshot_to_machine(session, "deck", {}, "/saves", False)

    assert not push_thread_called
```

**Asserting call kwargs:**
```python
mock_create.assert_awaited_once()
assert mock_create.call_args.kwargs["label"] == "pre_sync"
assert mock_create.call_args.kwargs["machine"] == "deck"

# For positional args (e.g., paramiko connect):
args, _ = mock_make.call_args
assert args[6] == 5
```

**Binary file tests (item_parsing):**
```python
def test_round_trip_identity(stash: ParsedStash) -> None:
    """Serialize → parse must give bit-for-bit identical bytes."""
    original = FIXTURE_SC.read_bytes()
    serialized = serialize_stash(stash)
    assert serialized == original, (
        f"Round-trip mismatch: original={len(original)} bytes, "
        f"serialized={len(serialized)} bytes"
    )
```

**Inline assertion messages:**
All non-trivial assertions include a message explaining what failed and why it matters:
```python
assert call_order == ["create_snapshot", "push_thread"], (
    "pre_sync snapshot must be taken BEFORE the push runs — "
    "if this fails the safety backup was removed or reordered"
)
```

## Automation

**Pre-commit hook:** `.git/hooks/pre-commit` runs the full test suite before each commit.

**Claude Code stop hook:** `.claude/settings.json` runs `tail -3` of the test suite after each Claude response — failures surface automatically.

---

*Testing analysis: 2026-03-28*
