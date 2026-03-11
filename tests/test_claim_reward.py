from __future__ import annotations

"""
Unit tests for claim_reward() in backend.services.seasons_service.

The function is tested directly (not via HTTP) with mocked sessions and
patched file-system / parsing dependencies.  No Docker / real DB required
for the pure-mock tests; the item_parsing tests that need real fixtures
still live in tests/item_parsing/.

Coverage matrix
---------------
Preconditions (fail before any I/O):
  - achievement not found
  - reward already claimed
  - milestone has no reward bytes
  - no snapshot found
  - stash file missing (backup never attempted)

Safety protocol (backup → validate → write → commit ordering):
  - backup is created before the stash write
  - stash NOT written if backup fails
  - DB NOT committed if backup fails
  - stash NOT written if tab 5 validation fails
  - stash NOT written if stash has < 5 tabs
  - stash NOT written if round-trip item count mismatches
  - DB NOT committed if write_bytes raises (OSError)
  - achievement.claimed_at stays None if write fails

Happy path:
  - achievement.claimed_at is set
  - claimed_at is a recent UTC datetime
  - DB committed after successful write
  - backup called with correct label
  - stash written exactly once
  - parse_stash called twice (initial + round-trip)
  - serialize_stash called once
  - function returns the achievement object

To run (inside Docker):
  docker run --rm -v $(pwd):/app -w /app enigma-engine-enigma-engine \\
      python3 -m pytest tests/test_claim_reward.py -v
"""

from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("sqlalchemy", reason="SQLAlchemy not installed — run tests inside Docker")

from backend.services.seasons_service import claim_reward


# ─── Model factories ──────────────────────────────────────────────────────────

_REWARD_BYTES = b"\x10\x0f\x00\x00" + b"\xab" * 40  # plausible fake item bytes


def _achievement(id: int = 1, milestone_id: int = 10, claimed_at=None) -> MagicMock:
    a = MagicMock()
    a.id = id
    a.milestone_id = milestone_id
    a.claimed_at = claimed_at
    return a


def _milestone(id: int = 10, reward_item_bytes: bytes | None = _REWARD_BYTES) -> MagicMock:
    ms = MagicMock()
    ms.id = id
    ms.reward_item_bytes = reward_item_bytes
    return ms


def _snap(
    snapshot_path: str = "backups/pc/20260311T120000Z_manual",
    source_machine: str = "pc",
) -> MagicMock:
    s = MagicMock()
    s.snapshot_path = snapshot_path
    s.source_machine = source_machine
    s.file_count = 3
    s.characters = []
    s.created_at = datetime(2026, 3, 11, 12, 0, 0, tzinfo=timezone.utc)
    return s


def _page(item_count: int = 0) -> MagicMock:
    p = MagicMock()
    p.items = [MagicMock() for _ in range(item_count)]
    p.jm_item_count = item_count
    return p


def _stash(tab5_item_count: int = 0, page_count: int = 5) -> MagicMock:
    stash = MagicMock()
    stash.pages = [_page() for _ in range(page_count)]
    if page_count > 4:
        stash.pages[4] = _page(tab5_item_count)
    return stash


def _session(achievement_obj, milestone_obj, snap_obj) -> AsyncMock:
    s = AsyncMock()
    s.get = AsyncMock(side_effect=[achievement_obj, milestone_obj])
    snap_result = MagicMock()
    snap_result.scalar_one_or_none.return_value = snap_obj
    s.execute = AsyncMock(return_value=snap_result)
    s.commit = AsyncMock()
    return s


def _mock_cfg(tmp_path: Path) -> MagicMock:
    cfg = MagicMock()
    cfg.data_dir = tmp_path
    return cfg


# ─── Patch stack ──────────────────────────────────────────────────────────────

class _Patches:
    """
    Context manager that activates all patches needed to exercise claim_reward()
    without touching the real file system or parser.

    Yields a dict of mock objects so individual tests can inspect calls.
    """

    def __init__(
        self,
        tmp_path: Path,
        *,
        stash_exists: bool = True,
        initial_stash=None,
        rt_stash=None,
        backup_raises: Exception | None = None,
        validate_result: bool = True,
        serialize_returns: bytes = b"serialized_stash_bytes",
        write_raises: Exception | None = None,
    ):
        self._tmp = tmp_path
        self._stash_exists = stash_exists
        self._initial_stash = initial_stash or _stash(tab5_item_count=0)
        self._rt_stash = rt_stash or _stash(tab5_item_count=1)
        self._backup_raises = backup_raises
        self._validate_result = validate_result
        self._serialize_returns = serialize_returns
        self._write_raises = write_raises
        self._stack = ExitStack()
        self.mocks: dict = {}

    def __enter__(self):
        s = self._stack
        initial = self._initial_stash
        rt = self._rt_stash

        # inserted page has original_count + 1 items
        # (initial may have < 5 pages in some tests — default to 0)
        try:
            initial_tab5_count = len(initial.pages[4].items)
        except (IndexError, TypeError):
            initial_tab5_count = 0
        inserted_page = _page(item_count=initial_tab5_count + 1)

        self.mocks["settings"] = s.enter_context(
            patch("backend.config.get_settings", return_value=_mock_cfg(self._tmp))
        )
        self.mocks["exists"] = s.enter_context(
            patch.object(Path, "exists", return_value=self._stash_exists)
        )

        backup_kwargs: dict = {"new_callable": AsyncMock}
        if self._backup_raises is not None:
            backup_kwargs["side_effect"] = self._backup_raises
        self.mocks["backup"] = s.enter_context(
            patch("backend.services.backup_manager.create_local_snapshot", **backup_kwargs)
        )

        self.mocks["validate"] = s.enter_context(
            patch(
                "backend.services.item_parsing.stash_format.validate_page_items",
                return_value=self._validate_result,
            )
        )
        self.mocks["parse"] = s.enter_context(
            patch(
                "backend.services.item_parsing.parse_stash",
                side_effect=[initial, rt],
            )
        )
        self.mocks["insert"] = s.enter_context(
            patch(
                "backend.services.item_parsing.stash_format.insert_item_into_page",
                return_value=inserted_page,
            )
        )
        self.mocks["serialize"] = s.enter_context(
            patch(
                "backend.services.item_parsing.serialize_stash",
                return_value=self._serialize_returns,
            )
        )

        write_kwargs: dict = {}
        if self._write_raises is not None:
            write_kwargs["side_effect"] = self._write_raises
        self.mocks["write"] = s.enter_context(
            patch.object(Path, "write_bytes", **write_kwargs)
        )

        return self.mocks

    def __exit__(self, *args):
        self._stack.__exit__(*args)


# ─── Precondition tests ───────────────────────────────────────────────────────

class TestClaimRewardPreconditions:
    """Guards that fire before any file I/O or backup is attempted."""

    async def test_raises_if_achievement_not_found(self, tmp_path) -> None:
        s = AsyncMock()
        s.get = AsyncMock(return_value=None)
        s.commit = AsyncMock()

        with pytest.raises(ValueError, match="not found"):
            await claim_reward(s, achievement_id=99)

        s.commit.assert_not_awaited()

    async def test_raises_if_already_claimed(self, tmp_path) -> None:
        ach = _achievement(claimed_at=datetime(2026, 3, 10, tzinfo=timezone.utc))
        s = _session(ach, None, None)

        with pytest.raises(ValueError, match="already claimed"):
            await claim_reward(s, achievement_id=1)

        s.commit.assert_not_awaited()

    async def test_raises_if_milestone_has_no_reward_bytes(self, tmp_path) -> None:
        ach = _achievement()
        ms = _milestone(reward_item_bytes=None)
        s = _session(ach, ms, None)

        with pytest.raises(ValueError, match="No reward item"):
            await claim_reward(s, achievement_id=1)

        s.commit.assert_not_awaited()

    async def test_raises_if_no_snapshot_available(self, tmp_path) -> None:
        ach = _achievement()
        ms = _milestone()
        s = _session(ach, ms, snap_obj=None)

        with pytest.raises(ValueError, match="No snapshot"):
            await claim_reward(s, achievement_id=1)

        s.commit.assert_not_awaited()

    async def test_raises_if_stash_file_missing(self, tmp_path) -> None:
        ach = _achievement()
        ms = _milestone()
        snap = _snap()
        s = _session(ach, ms, snap)

        with _Patches(tmp_path, stash_exists=False) as mocks:
            with pytest.raises(ValueError, match="Stash file not found"):
                await claim_reward(s, achievement_id=1)

            # Backup must never be attempted if stash file doesn't exist
            mocks["backup"].assert_not_awaited()

        s.commit.assert_not_awaited()


# ─── Safety protocol tests ────────────────────────────────────────────────────

class TestClaimRewardSafetyProtocol:
    """Backup-before-write, round-trip validation, and transaction rollback."""

    async def test_backup_created_before_stash_write(self, tmp_path) -> None:
        """Backup must be called strictly before write_bytes."""
        call_order: list[str] = []

        ach = _achievement()
        ms = _milestone()
        snap = _snap()
        s = _session(ach, ms, snap)

        initial = _stash(tab5_item_count=0)
        rt = _stash(tab5_item_count=1)
        inserted = _page(item_count=1)

        async def _track_backup(*args, **kwargs):
            call_order.append("backup")

        def _track_write(_data):
            call_order.append("write")

        with ExitStack() as stack:
            stack.enter_context(patch("backend.config.get_settings", return_value=_mock_cfg(tmp_path)))
            stack.enter_context(patch.object(Path, "exists", return_value=True))
            stack.enter_context(patch("backend.services.backup_manager.create_local_snapshot", side_effect=_track_backup))
            stack.enter_context(patch("backend.services.item_parsing.stash_format.validate_page_items", return_value=True))
            stack.enter_context(patch("backend.services.item_parsing.parse_stash", side_effect=[initial, rt]))
            stack.enter_context(patch("backend.services.item_parsing.stash_format.insert_item_into_page", return_value=inserted))
            stack.enter_context(patch("backend.services.item_parsing.serialize_stash", return_value=b"bytes"))
            stack.enter_context(patch.object(Path, "write_bytes", side_effect=_track_write))

            await claim_reward(s, achievement_id=1)

        # call_order includes the rt temp write AND the stash write.
        # The only guarantee we need: backup happens before any write.
        assert "backup" in call_order, "Backup was never called"
        assert "write" in call_order, "Stash write was never called"
        assert call_order.index("backup") < call_order.index("write"), (
            f"Expected backup before any write, got: {call_order}"
        )

    async def test_stash_not_written_if_backup_fails(self, tmp_path) -> None:
        ach = _achievement()
        ms = _milestone()
        snap = _snap()
        s = _session(ach, ms, snap)

        with _Patches(tmp_path, backup_raises=RuntimeError("disk full")) as mocks:
            with pytest.raises(RuntimeError, match="Pre-claim backup failed"):
                await claim_reward(s, achievement_id=1)

            mocks["write"].assert_not_called()

    async def test_db_not_committed_if_backup_fails(self, tmp_path) -> None:
        ach = _achievement()
        ms = _milestone()
        snap = _snap()
        s = _session(ach, ms, snap)

        with _Patches(tmp_path, backup_raises=RuntimeError("backup error")):
            with pytest.raises(RuntimeError):
                await claim_reward(s, achievement_id=1)

        s.commit.assert_not_awaited()

    async def test_stash_not_written_if_tab5_validation_fails(self, tmp_path) -> None:
        ach = _achievement()
        ms = _milestone()
        snap = _snap()
        s = _session(ach, ms, snap)

        with _Patches(tmp_path, validate_result=False) as mocks:
            with pytest.raises(RuntimeError, match="Tab 5 failed item validation"):
                await claim_reward(s, achievement_id=1)

            mocks["write"].assert_not_called()

    async def test_stash_not_written_if_fewer_than_5_tabs(self, tmp_path) -> None:
        ach = _achievement()
        ms = _milestone()
        snap = _snap()
        s = _session(ach, ms, snap)

        four_tab_stash = _stash(page_count=4)
        rt = _stash(tab5_item_count=1)

        with _Patches(tmp_path, initial_stash=four_tab_stash, rt_stash=rt) as mocks:
            with pytest.raises(ValueError, match="fewer than 5 tabs"):
                await claim_reward(s, achievement_id=1)

            mocks["write"].assert_not_called()

    async def test_stash_not_written_if_roundtrip_count_mismatch(self, tmp_path) -> None:
        """Abort write when re-parsed item count doesn't match expected."""
        ach = _achievement()
        ms = _milestone()
        snap = _snap()
        s = _session(ach, ms, snap)

        initial = _stash(tab5_item_count=0)
        rt_bad = _stash(tab5_item_count=0)  # should be 1 after insert, but reports 0

        with _Patches(tmp_path, initial_stash=initial, rt_stash=rt_bad) as mocks:
            with pytest.raises(RuntimeError, match="Round-trip validation failed"):
                await claim_reward(s, achievement_id=1)

            # The rt temp file IS written (1 call) before the count mismatch is detected.
            # The actual stash file must NOT be written (would be the 2nd call).
            assert mocks["write"].call_count == 1

    async def test_db_not_committed_if_write_raises(self, tmp_path) -> None:
        ach = _achievement()
        ms = _milestone()
        snap = _snap()
        s = _session(ach, ms, snap)

        with _Patches(tmp_path, write_raises=OSError("Disk full")):
            with pytest.raises(OSError):
                await claim_reward(s, achievement_id=1)

        s.commit.assert_not_awaited()

    async def test_claimed_at_stays_none_if_write_raises(self, tmp_path) -> None:
        ach = _achievement(claimed_at=None)
        ms = _milestone()
        snap = _snap()
        s = _session(ach, ms, snap)

        with _Patches(tmp_path, write_raises=OSError("Disk full")):
            with pytest.raises(OSError):
                await claim_reward(s, achievement_id=1)

        assert ach.claimed_at is None


# ─── Happy path tests ─────────────────────────────────────────────────────────

class TestClaimRewardHappyPath:
    """Full success flow."""

    async def test_marks_achievement_claimed(self, tmp_path) -> None:
        ach = _achievement()
        ms = _milestone()
        snap = _snap()
        s = _session(ach, ms, snap)

        with _Patches(tmp_path):
            await claim_reward(s, achievement_id=1)

        assert ach.claimed_at is not None

    async def test_claimed_at_is_recent_utc(self, tmp_path) -> None:
        ach = _achievement()
        ms = _milestone()
        snap = _snap()
        s = _session(ach, ms, snap)

        with _Patches(tmp_path):
            await claim_reward(s, achievement_id=1)

        now = datetime.now(timezone.utc)
        assert abs((now - ach.claimed_at).total_seconds()) < 5

    async def test_commits_db_after_successful_write(self, tmp_path) -> None:
        ach = _achievement()
        ms = _milestone()
        snap = _snap()
        s = _session(ach, ms, snap)

        with _Patches(tmp_path):
            await claim_reward(s, achievement_id=1)

        s.commit.assert_awaited()

    async def test_backup_called_with_pre_season_reward_label(self, tmp_path) -> None:
        ach = _achievement()
        ms = _milestone()
        snap = _snap()
        s = _session(ach, ms, snap)

        with _Patches(tmp_path) as mocks:
            await claim_reward(s, achievement_id=1)

        mocks["backup"].assert_awaited_once()
        _, kwargs = mocks["backup"].await_args
        assert kwargs["label"] == "pre_season_reward"

    async def test_stash_written_after_roundtrip_validation(self, tmp_path) -> None:
        """write_bytes is called twice: once for the rt temp file, once for the stash."""
        ach = _achievement()
        ms = _milestone()
        snap = _snap()
        s = _session(ach, ms, snap)

        with _Patches(tmp_path) as mocks:
            await claim_reward(s, achievement_id=1)

        assert mocks["write"].call_count == 2

    async def test_parse_stash_called_twice(self, tmp_path) -> None:
        """First call: initial parse. Second call: round-trip validation."""
        ach = _achievement()
        ms = _milestone()
        snap = _snap()
        s = _session(ach, ms, snap)

        with _Patches(tmp_path) as mocks:
            await claim_reward(s, achievement_id=1)

        assert mocks["parse"].call_count == 2

    async def test_serialize_stash_called_once(self, tmp_path) -> None:
        ach = _achievement()
        ms = _milestone()
        snap = _snap()
        s = _session(ach, ms, snap)

        with _Patches(tmp_path) as mocks:
            await claim_reward(s, achievement_id=1)

        mocks["serialize"].assert_called_once()

    async def test_returns_achievement_object(self, tmp_path) -> None:
        ach = _achievement()
        ms = _milestone()
        snap = _snap()
        s = _session(ach, ms, snap)

        with _Patches(tmp_path):
            result = await claim_reward(s, achievement_id=1)

        assert result is ach

    async def test_tab5_with_existing_items_increments_by_one(self, tmp_path) -> None:
        """Tab 5 already has 2 items; round-trip should show 3."""
        ach = _achievement()
        ms = _milestone()
        snap = _snap()
        s = _session(ach, ms, snap)

        initial = _stash(tab5_item_count=2)
        rt = _stash(tab5_item_count=3)  # 2 + 1 inserted

        with _Patches(tmp_path, initial_stash=initial, rt_stash=rt) as mocks:
            await claim_reward(s, achievement_id=1)

        # rt temp write + stash write = 2 calls
        assert mocks["write"].call_count == 2
        assert ach.claimed_at is not None
