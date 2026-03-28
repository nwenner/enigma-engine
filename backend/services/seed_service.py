from __future__ import annotations

"""
Map Seed service — write a seed value into a character's .d2s in the vault snapshot.

Called by: backend/routers/seeds.py (apply endpoint)
Pattern: guard_mothership_write → _create_local_backup_snapshot → write_map_seed → write_bytes

Operations:
  apply_seed_to_snapshot(session, seed, character) → dict
"""
import logging
import shutil
from datetime import datetime, timezone

from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.models import BackupSnapshot, SavedSeed, Season
from backend.services.d2s_parser import D2SParseError, write_map_seed

log = logging.getLogger(__name__)


# ─── Snapshot helpers ─────────────────────────────────────────────────────────

async def _latest_snapshot(session: AsyncSession) -> BackupSnapshot | None:
    active_result = await session.execute(select(Season).where(Season.status == "active"))
    active_season = active_result.scalar_one_or_none()

    q = (
        select(BackupSnapshot)
        .where(BackupSnapshot.label.in_(["manual", "game_close"]))
        .order_by(BackupSnapshot.created_at.desc())
        .limit(1)
    )
    if active_season and active_season.started_at:
        q = q.where(BackupSnapshot.created_at >= active_season.started_at)

    result = await session.execute(q)
    return result.scalar_one_or_none()


async def _create_local_backup_snapshot(
    session: AsyncSession,
    source_snap: BackupSnapshot,
    label: str,
) -> BackupSnapshot:
    """Copy the local snapshot directory to create a new backup record."""
    cfg = get_settings()
    source_dir = cfg.data_dir / source_snap.snapshot_path
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest_dir = cfg.backups_dir / f"mothership/{timestamp}_{label}"
    shutil.copytree(str(source_dir), str(dest_dir))

    snap = BackupSnapshot(
        label=label,
        snapshot_path=str(dest_dir.relative_to(cfg.data_dir)),
        source_machine="mothership",
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    session.add(snap)
    await session.commit()
    await session.refresh(snap)
    log.info("BACKUP: Created local backup snapshot '%s' at %s", label, dest_dir)
    return snap


# ─── Public API ───────────────────────────────────────────────────────────────

async def apply_seed_to_snapshot(
    session: AsyncSession,
    saved_seed: SavedSeed,
    character: str,
    background_tasks: BackgroundTasks,
) -> dict:
    """Apply a saved seed to a character's .d2s in the latest vault snapshot.

    Sequence (per D-11):
      1. guard_mothership_write — raises 409 if D2R running
      2. _create_local_backup_snapshot with label "pre_seed_restore"
      3. write_map_seed on target .d2s file
      4. assert file size unchanged
      5. write patched bytes back to snapshot dir
      6. trigger_mothership_push (background)

    Returns dict: { "success": True, "seed_name": str, "character": str, "seed_hex": str }
    """
    snap = await _latest_snapshot(session)
    if snap is None:
        raise HTTPException(404, "No snapshot available. Check In from a device first.")

    snap_dir = get_settings().data_dir / snap.snapshot_path
    d2s_path = snap_dir / f"{character}.d2s"
    if not d2s_path.exists():
        raise HTTPException(404, f"{character}.d2s not found in latest snapshot.")

    from backend.services.auto_sync import guard_mothership_write, trigger_mothership_push
    await guard_mothership_write(session)

    log.info("BACKUP: Creating pre-seed-restore backup before patching %s.d2s", character)
    try:
        await _create_local_backup_snapshot(session, snap, "pre_seed_restore")
    except Exception as e:
        log.error("BACKUP FAILED: Cannot proceed with seed restore: %s", e)
        raise HTTPException(500, f"Pre-seed backup failed: {e}") from e

    original = d2s_path.read_bytes()
    try:
        patched = write_map_seed(original, saved_seed.seed_value)
    except D2SParseError as e:
        raise HTTPException(400, f"Cannot patch {character}.d2s: {e}") from e

    assert len(patched) == len(original), (
        f"Seed patch changed file size: {len(original)} → {len(patched)}"
    )

    d2s_path.write_bytes(patched)
    log.info(
        "Applied seed 0x%08X ('%s') to %s.d2s",
        saved_seed.seed_value, saved_seed.name, character,
    )

    await trigger_mothership_push(background_tasks, session)

    return {
        "success": True,
        "seed_name": saved_seed.name,
        "character": character,
        "seed_hex": f"0x{saved_seed.seed_value:08X}",
    }
