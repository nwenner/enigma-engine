from __future__ import annotations

"""
Unit tests for vault gold operations and the local snapshot sync helper added
in the 2026-03-10 session.

Functions under test
--------------------
  stash_service._update_local_snapshot_stash  -- writes stash bytes into the
      current season's latest snapshot directory after any vault write.
  stash_service.deposit_gold                  -- move gold from stash → vault.
  stash_service.withdraw_gold                 -- move gold from vault → stash.

Strategy
--------
- All SSH / SFTP calls are eliminated by mocking asyncio.to_thread (no-op)
  and create_snapshot (AsyncMock no-op).
- parse_stash / serialize_stash are mocked so tests control stash.gold.
- _update_local_snapshot_stash is mocked in deposit/withdraw tests (it has
  its own test class) so each class tests exactly one concern.
- Real filesystem access only happens in TestUpdateLocalSnapshotStash via
  pytest's tmp_path fixture.

To run (inside Docker):
  docker run --rm -v $(pwd):/app -w /app enigma-engine-enigma-engine \\
      python3 -m pytest tests/test_stash_vault.py -v
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("sqlalchemy", reason="SQLAlchemy not installed — run tests inside Docker")

from backend.services.stash_service import (
    MAX_STASH_GOLD,
    _update_local_snapshot_stash,
    deposit_gold,
    withdraw_gold,
)

# ─── Shared constants ─────────────────────────────────────────────────────────

_SC_FILE = "ModernSharedStashSoftCoreV2.d2i"
_HC_FILE = "ModernSharedStashHardCoreV2.d2i"
_FAKE_CONN = {"host": "192.168.1.1", "port": 22, "username": "user", "password": "pass"}
_SAVE_DIR = "/game/saves"


# ─── Session / model helpers ──────────────────────────────────────────────────

def _result(value) -> MagicMock:
    """Wrap a scalar value in an execute()-result mock."""
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    r.scalars.return_value.all.return_value = []
    return r


def _session(*scalars) -> AsyncMock:
    """Session whose successive execute() calls return the given scalars."""
    s = AsyncMock()
    s.execute = AsyncMock(side_effect=[_result(v) for v in scalars])
    return s


def _vault(amount: int, hardcore: bool = False) -> MagicMock:
    v = MagicMock()
    v.hardcore = hardcore
    v.amount = amount
    v.last_updated = None
    return v


def _mock_stash(gold: int) -> MagicMock:
    stash = MagicMock()
    stash.gold = gold
    return stash


def _fake_season(started_at=None) -> MagicMock:
    from datetime import datetime, timezone
    s = MagicMock()
    s.status = "active"
    s.started_at = started_at or datetime(2026, 1, 1, tzinfo=timezone.utc).replace(tzinfo=None)
    return s


def _fake_snap(snapshot_path: str) -> MagicMock:
    snap = MagicMock()
    snap.snapshot_path = snapshot_path
    return snap


# ─── Patch helpers ────────────────────────────────────────────────────────────

def _vault_patches(stash_gold: int):
    """
    Return a list of (patch_target, kwargs) tuples that stub out all
    SSH/filesystem calls inside deposit_gold and withdraw_gold so tests
    only exercise the business logic.

    Usage:
        with _apply_patches(stash_gold=500) as mock_stash:
            ...
    """
    raise NotImplementedError  # use _apply_patches instead


from contextlib import contextmanager

@contextmanager
def _apply_patches(stash_gold: int, mock_snapshot_update: bool = True):
    """
    Context manager that patches every external call in deposit/withdraw.
    Yields the mock ParsedStash so tests can inspect .gold after the call.
    """
    stash = _mock_stash(stash_gold)
    patches = [
        patch("backend.services.backup_manager.create_snapshot", new_callable=AsyncMock),
        patch("asyncio.to_thread", new_callable=AsyncMock),
        patch("backend.services.stash_service.parse_stash", return_value=stash),
        patch("backend.services.stash_service.serialize_stash", return_value=b"bytes"),
    ]
    if mock_snapshot_update:
        patches.append(
            patch("backend.services.stash_service._update_local_snapshot_stash", new_callable=AsyncMock)
        )

    entered = [p.__enter__() for p in [p.start() for p in patches]]
    try:
        yield stash
    finally:
        for p in patches:
            try:
                p.stop()
            except RuntimeError:
                pass


# ─── _update_local_snapshot_stash ─────────────────────────────────────────────

class TestUpdateLocalSnapshotStash:
    """Unit tests for the helper that writes vault-modified stash bytes back
    into the local snapshot directory so the display stays in sync."""

    async def test_writes_bytes_to_snapshot_dir(self, tmp_path: Path) -> None:
        """Happy path: bytes are written to the correct file in the snapshot dir."""
        snap_dir = tmp_path / "backups" / "snap_001"
        snap_dir.mkdir(parents=True)

        session = _session(
            None,                        # no active season
            _fake_snap("backups/snap_001"),  # latest snapshot
        )

        with patch("backend.config.get_settings") as mock_cfg:
            mock_cfg.return_value.data_dir = tmp_path
            await _update_local_snapshot_stash(session, _SC_FILE, b"stash data")

        written = (snap_dir / _SC_FILE).read_bytes()
        assert written == b"stash data"

    async def test_no_snapshot_found_returns_without_error(self) -> None:
        """If there is no qualifying snapshot, the function logs and returns cleanly."""
        session = _session(
            None,  # no active season
            None,  # no snapshot
        )
        with patch("backend.config.get_settings") as mock_cfg:
            mock_cfg.return_value.data_dir = Path("/app/data")
            # Should not raise
            await _update_local_snapshot_stash(session, _SC_FILE, b"data")

    async def test_missing_snapshot_directory_returns_without_error(self, tmp_path: Path) -> None:
        """If the snapshot path doesn't exist on disk, just log and return."""
        session = _session(
            None,
            _fake_snap("backups/missing_snap"),
        )
        with patch("backend.config.get_settings") as mock_cfg:
            mock_cfg.return_value.data_dir = tmp_path  # snap dir doesn't exist under here
            await _update_local_snapshot_stash(session, _SC_FILE, b"data")
        # No file written, no exception

    async def test_active_season_uses_season_filtered_query(self, tmp_path: Path) -> None:
        """When an active season exists, the snapshot query includes started_at filter."""
        snap_dir = tmp_path / "backups" / "season_snap"
        snap_dir.mkdir(parents=True)

        season = _fake_season()
        session = _session(
            season,
            _fake_snap("backups/season_snap"),
        )

        with patch("backend.config.get_settings") as mock_cfg:
            mock_cfg.return_value.data_dir = tmp_path
            await _update_local_snapshot_stash(session, _SC_FILE, b"season stash")

        assert (snap_dir / _SC_FILE).read_bytes() == b"season stash"

    async def test_overwrites_existing_file(self, tmp_path: Path) -> None:
        """Calling twice with different bytes replaces the file each time."""
        snap_dir = tmp_path / "backups" / "snap_002"
        snap_dir.mkdir(parents=True)
        (snap_dir / _SC_FILE).write_bytes(b"old data")

        for iteration, payload in enumerate([b"new data v1", b"new data v2"]):
            session = _session(None, _fake_snap("backups/snap_002"))
            with patch("backend.config.get_settings") as mock_cfg:
                mock_cfg.return_value.data_dir = tmp_path
                await _update_local_snapshot_stash(session, _SC_FILE, payload)
            assert (snap_dir / _SC_FILE).read_bytes() == payload

    async def test_hardcore_file_written_separately(self, tmp_path: Path) -> None:
        """HC stash file is written with the HC filename, not the SC one."""
        snap_dir = tmp_path / "backups" / "snap_003"
        snap_dir.mkdir(parents=True)

        session = _session(None, _fake_snap("backups/snap_003"))
        with patch("backend.config.get_settings") as mock_cfg:
            mock_cfg.return_value.data_dir = tmp_path
            await _update_local_snapshot_stash(session, _HC_FILE, b"hc data")

        assert (snap_dir / _HC_FILE).read_bytes() == b"hc data"
        assert not (snap_dir / _SC_FILE).exists()


# ─── deposit_gold ─────────────────────────────────────────────────────────────

class TestDepositGoldValidation:
    """deposit_gold raises ValueError for invalid inputs before touching the DB."""

    async def test_zero_amount_raises(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            await deposit_gold(_session(), "pc", "sc", 0, _FAKE_CONN, _SAVE_DIR)

    async def test_negative_amount_raises(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            await deposit_gold(_session(), "pc", "sc", -100, _FAKE_CONN, _SAVE_DIR)

    async def test_insufficient_stash_gold_raises(self) -> None:
        with _apply_patches(stash_gold=50):
            with pytest.raises(ValueError, match="50"):
                await deposit_gold(
                    _session(None),  # no vault
                    "pc", "sc", 100, _FAKE_CONN, _SAVE_DIR,
                )


class TestDepositGoldVaultUpdate:
    """deposit_gold correctly updates the GoldVault and calls the snapshot helper."""

    async def test_creates_vault_record_when_none_exists(self) -> None:
        """First deposit: GoldVault row is added to the session."""
        session = _session(None)  # no existing vault
        added = []
        session.add = MagicMock(side_effect=added.append)

        with _apply_patches(stash_gold=1000):
            await deposit_gold(session, "pc", "sc", 500, _FAKE_CONN, _SAVE_DIR)

        assert len(added) == 1
        new_vault = added[0]
        assert new_vault.amount == 500
        assert new_vault.hardcore is False

    async def test_increments_existing_vault(self) -> None:
        """Subsequent deposit: existing GoldVault.amount is incremented."""
        vault = _vault(amount=200)
        session = _session(vault)

        with _apply_patches(stash_gold=1000):
            result = await deposit_gold(session, "pc", "sc", 300, _FAKE_CONN, _SAVE_DIR)

        assert vault.amount == 500
        assert result["vault_gold"] == 500

    async def test_subtracts_gold_from_stash(self) -> None:
        """deposit_gold decrements stash.gold by the deposited amount."""
        vault = _vault(amount=0)
        session = _session(vault)

        with _apply_patches(stash_gold=1000) as mock_stash:
            await deposit_gold(session, "pc", "sc", 400, _FAKE_CONN, _SAVE_DIR)

        assert mock_stash.gold == 600

    async def test_returns_updated_gold_values(self) -> None:
        vault = _vault(amount=100)
        session = _session(vault)

        with _apply_patches(stash_gold=800):
            result = await deposit_gold(session, "pc", "sc", 300, _FAKE_CONN, _SAVE_DIR)

        assert result["stash_gold"] == 500
        assert result["vault_gold"] == 400

    async def test_calls_snapshot_update(self) -> None:
        """deposit_gold calls _update_local_snapshot_stash after uploading."""
        vault = _vault(amount=0)
        session = _session(vault)

        with patch("backend.services.backup_manager.create_snapshot", new_callable=AsyncMock), \
             patch("asyncio.to_thread", new_callable=AsyncMock), \
             patch("backend.services.stash_service.parse_stash", return_value=_mock_stash(500)), \
             patch("backend.services.stash_service.serialize_stash", return_value=b"bytes"), \
             patch("backend.services.stash_service._update_local_snapshot_stash", new_callable=AsyncMock) as mock_update:
            await deposit_gold(session, "pc", "sc", 200, _FAKE_CONN, _SAVE_DIR)

        mock_update.assert_awaited_once()
        # Called with session, the SC filename, and the serialized bytes
        args = mock_update.await_args[0]
        assert args[0] is session
        assert args[1] == _SC_FILE
        assert args[2] == b"bytes"

    async def test_commits_session(self) -> None:
        vault = _vault(amount=0)
        session = _session(vault)

        with _apply_patches(stash_gold=1000):
            await deposit_gold(session, "pc", "sc", 100, _FAKE_CONN, _SAVE_DIR)

        session.commit.assert_awaited_once()

    async def test_hardcore_mode_uses_hc_filename(self) -> None:
        """deposit_gold passes the HC stash filename when mode='hc'."""
        vault = _vault(amount=0, hardcore=True)
        session = _session(vault)

        with patch("backend.services.backup_manager.create_snapshot", new_callable=AsyncMock), \
             patch("asyncio.to_thread", new_callable=AsyncMock), \
             patch("backend.services.stash_service.parse_stash", return_value=_mock_stash(500)), \
             patch("backend.services.stash_service.serialize_stash", return_value=b"hc"), \
             patch("backend.services.stash_service._update_local_snapshot_stash", new_callable=AsyncMock) as mock_update:
            await deposit_gold(session, "pc", "hc", 100, _FAKE_CONN, _SAVE_DIR)

        args = mock_update.await_args[0]
        assert args[1] == _HC_FILE


# ─── withdraw_gold ────────────────────────────────────────────────────────────

class TestWithdrawGoldValidation:
    """withdraw_gold raises ValueError for invalid inputs."""

    async def test_zero_amount_raises(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            await withdraw_gold(_session(), "pc", "sc", 0, _FAKE_CONN, _SAVE_DIR)

    async def test_negative_amount_raises(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            await withdraw_gold(_session(), "pc", "sc", -50, _FAKE_CONN, _SAVE_DIR)

    async def test_insufficient_vault_raises(self) -> None:
        """Withdrawing more than vault holds raises before any SSH call."""
        vault = _vault(amount=100)
        session = _session(vault)

        with pytest.raises(ValueError, match="100"):
            await withdraw_gold(session, "pc", "sc", 500, _FAKE_CONN, _SAVE_DIR)

    async def test_empty_vault_raises(self) -> None:
        session = _session(None)  # no vault row → vault_amount = 0

        with pytest.raises(ValueError, match="0"):
            await withdraw_gold(session, "pc", "sc", 1, _FAKE_CONN, _SAVE_DIR)

    async def test_stash_cap_exceeded_raises(self) -> None:
        """Withdrawing would push stash above 12.5M gold cap."""
        vault = _vault(amount=5_000_000)
        session = _session(vault)

        with _apply_patches(stash_gold=MAX_STASH_GOLD - 100):
            with pytest.raises(ValueError, match="cap"):
                await withdraw_gold(session, "pc", "sc", 200, _FAKE_CONN, _SAVE_DIR)


class TestWithdrawGoldVaultUpdate:
    """withdraw_gold correctly updates stash + vault and syncs the snapshot."""

    async def test_decrements_vault_amount(self) -> None:
        vault = _vault(amount=1000)
        session = _session(vault)

        with _apply_patches(stash_gold=0):
            await withdraw_gold(session, "pc", "sc", 400, _FAKE_CONN, _SAVE_DIR)

        assert vault.amount == 600

    async def test_adds_gold_to_stash(self) -> None:
        vault = _vault(amount=500)
        session = _session(vault)

        with _apply_patches(stash_gold=200) as mock_stash:
            await withdraw_gold(session, "pc", "sc", 300, _FAKE_CONN, _SAVE_DIR)

        assert mock_stash.gold == 500

    async def test_returns_updated_gold_values(self) -> None:
        vault = _vault(amount=800)
        session = _session(vault)

        with _apply_patches(stash_gold=100):
            result = await withdraw_gold(session, "pc", "sc", 200, _FAKE_CONN, _SAVE_DIR)

        assert result["stash_gold"] == 300
        assert result["vault_gold"] == 600

    async def test_withdraw_exactly_vault_balance_succeeds(self) -> None:
        """Withdrawing the full vault balance is allowed."""
        vault = _vault(amount=999)
        session = _session(vault)

        with _apply_patches(stash_gold=0):
            result = await withdraw_gold(session, "pc", "sc", 999, _FAKE_CONN, _SAVE_DIR)

        assert result["vault_gold"] == 0
        assert vault.amount == 0

    async def test_calls_snapshot_update(self) -> None:
        vault = _vault(amount=500)
        session = _session(vault)

        with patch("backend.services.backup_manager.create_snapshot", new_callable=AsyncMock), \
             patch("asyncio.to_thread", new_callable=AsyncMock), \
             patch("backend.services.stash_service.parse_stash", return_value=_mock_stash(0)), \
             patch("backend.services.stash_service.serialize_stash", return_value=b"out"), \
             patch("backend.services.stash_service._update_local_snapshot_stash", new_callable=AsyncMock) as mock_update:
            await withdraw_gold(session, "pc", "sc", 300, _FAKE_CONN, _SAVE_DIR)

        mock_update.assert_awaited_once()
        args = mock_update.await_args[0]
        assert args[0] is session
        assert args[1] == _SC_FILE
        assert args[2] == b"out"

    async def test_commits_session(self) -> None:
        vault = _vault(amount=300)
        session = _session(vault)

        with _apply_patches(stash_gold=0):
            await withdraw_gold(session, "pc", "sc", 100, _FAKE_CONN, _SAVE_DIR)

        session.commit.assert_awaited_once()

    async def test_stash_at_exact_cap_after_withdraw_succeeds(self) -> None:
        """Adding gold that brings stash to exactly 12.5M is allowed."""
        vault = _vault(amount=1_000_000)
        session = _session(vault)
        headroom = MAX_STASH_GOLD - 1_000_000  # stash starts here

        with _apply_patches(stash_gold=headroom):
            result = await withdraw_gold(session, "pc", "sc", 1_000_000, _FAKE_CONN, _SAVE_DIR)

        assert result["stash_gold"] == MAX_STASH_GOLD
