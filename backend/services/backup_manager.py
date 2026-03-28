from __future__ import annotations

"""
Backup manager: orchestrates the full download → backup → validate → upload → prune flow.

Called by the sync router. Operations are async at the outer level (DB calls),
but SFTP calls are synchronous (run via asyncio.to_thread).
"""
import asyncio
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.config import get_settings
from backend.models import SyncOperation, SyncFileRecord, BackupSnapshot
from backend.services import ssh_client as ssh_mod
from backend.services.d2s_parser import parse_d2s, D2SParseError

log = logging.getLogger(__name__)


def _sftp_download(sftp, remote_path: str, local_path: Path) -> int:
    """Download a file over SFTP and return bytes transferred."""
    local_path.parent.mkdir(parents=True, exist_ok=True)
    sftp.get(remote_path, str(local_path))
    return local_path.stat().st_size


def _sftp_upload(sftp, local_path: Path, remote_path: str) -> int:
    """Upload a file over SFTP and return bytes transferred."""
    sftp.put(str(local_path), remote_path)
    return local_path.stat().st_size


def _sftp_download_if_exists(sftp, remote_path: str, local_path: Path) -> bool:
    """Download remote file if it exists. Returns True if downloaded."""
    try:
        _sftp_download(sftp, remote_path, local_path)
        return True
    except FileNotFoundError:
        return False
    except IOError:
        return False


async def create_snapshot(
    session: AsyncSession,
    machine: str,
    conn_kwargs: dict,
    save_dir: str,
    label: str = "manual",
    sync_operation_id: int | None = None,
    update_characters: bool = True,
) -> BackupSnapshot:
    """
    Download all files from save_dir on machine and create a BackupSnapshot record.

    Args:
        machine: "pc" or "deck" — the machine being snapshotted
        conn_kwargs: SSH connection dict (host, port, username, password, key_path)
        save_dir: remote path to the save directory
        label: snapshot type — "manual", "game_close", "pre_sync", "pre_grail_deposit", "pre_grail_retrieve"
        sync_operation_id: link to a SyncOperation if applicable
    """
    cfg = get_settings()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_subdir = cfg.backups_dir / machine / f"{timestamp}_{label}"
    backup_subdir.mkdir(parents=True, exist_ok=True)

    _SNAPSHOT_EXCLUDED = {"settings.json"}

    def _download_all() -> list[dict]:
        backed_up = []
        with ssh_mod.get_sftp(**conn_kwargs) as (_ssh, sftp):
            all_files = ssh_mod.list_all_files(sftp, save_dir)
            for file_info in all_files:
                if file_info["filename"].lower() in _SNAPSHOT_EXCLUDED:
                    continue
                remote = ssh_mod.normalize_path(file_info["path"])
                local = backup_subdir / file_info["filename"]
                _sftp_download(sftp, remote, local)
                backed_up.append({
                    "filename": file_info["filename"],
                    "modified_at": file_info.get("modified_at", 0.0),
                })
        return backed_up

    backed_up_files = await asyncio.to_thread(_download_all)

    backup_chars = []
    char_list = []
    for item in backed_up_files:
        fname = item["filename"]
        if fname.endswith(".d2s"):
            try:
                c = parse_d2s(backup_subdir / fname)
                d = c.to_dict()
                backup_chars.append(d)
                char_list.append({**d, "modified_at": item["modified_at"]})
            except D2SParseError:
                pass

    snapshot = BackupSnapshot(
        source_machine=machine,
        snapshot_path=str(backup_subdir.relative_to(cfg.data_dir)),
        file_count=len(backed_up_files),
        characters=backup_chars,
        sync_operation_id=sync_operation_id,
        label=label,
    )
    session.add(snapshot)
    await session.commit()

    await _prune_backups(session, cfg, label)

    if update_characters and label in ("manual", "game_close") and char_list:
        from backend.routers.characters import upsert_characters
        await upsert_characters(session, char_list)

    return snapshot


async def create_local_snapshot(
    session: AsyncSession,
    source_snapshot: "BackupSnapshot",
    label: str,
) -> "BackupSnapshot":
    """
    Create a local copy of an existing snapshot directory without SSH.

    Used before in-place modifications to local snapshot files (e.g. milestone
    claim reward). Mirrors the safety semantics of create_snapshot() but operates
    entirely on the local filesystem — no device connection required.
    """
    cfg = get_settings()
    # Include microseconds so rapid sequential calls (e.g. bulk reward claims)
    # never collide on the destination directory name.
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    source_dir = cfg.data_dir / source_snapshot.snapshot_path

    if not source_dir.exists():
        raise RuntimeError(f"Source snapshot directory not found: {source_dir}")

    dest_dir = cfg.backups_dir / source_snapshot.source_machine / f"{timestamp}_{label}"
    await asyncio.to_thread(shutil.copytree, str(source_dir), str(dest_dir))
    log.info("LOCAL BACKUP: Copied %s → %s", source_dir, dest_dir)

    snapshot = BackupSnapshot(
        source_machine=source_snapshot.source_machine,
        snapshot_path=str(dest_dir.relative_to(cfg.data_dir)),
        file_count=source_snapshot.file_count,
        characters=source_snapshot.characters,
        label=label,
    )
    session.add(snapshot)
    await session.commit()

    await _prune_backups(session, cfg, label)

    return snapshot


async def push_snapshot_to_machine(
    session: AsyncSession,
    machine: str,
    conn_kwargs: dict,
    save_dir: str,
    is_windows: bool,
) -> tuple[int, int]:
    """
    Push the latest manual/game_close snapshot to the target machine.

    Full mirror: delete all .d2s/.d2i on target, then upload all snapshot files.
    If no snapshot exists (empty season state), device ends up with no saves.

    Returns (files_removed, files_uploaded).
    """
    cfg = get_settings()

    # Only push snapshots from the current active season (after season.started_at).
    # This prevents pre-season saves from being pushed to the device after a season wipe.
    from backend.models import Season as _Season
    active_season_result = await session.execute(
        select(_Season).where(_Season.status == "active")
    )
    active_season = active_season_result.scalar_one_or_none()

    snap_query = (
        select(BackupSnapshot)
        .where(BackupSnapshot.label.in_(["manual", "game_close"]))
        .order_by(BackupSnapshot.created_at.desc())
        .limit(1)
    )
    if active_season and active_season.started_at:
        snap_query = snap_query.where(BackupSnapshot.created_at >= active_season.started_at)

    def _resolve_snapshot_dir() -> Path | None:
        """Re-execute snap_query synchronously (called inside _push thread)."""
        # We can't await here, so snapshot_dir is resolved before the thread starts.
        # See the async re-resolution below for the race-condition fix.
        return snapshot_dir_ref[0]

    # Snapshot the destination's current saves before overwriting them.
    # This is the pre_sync safety backup — restoring it undoes the push.
    # NOTE: this await may yield to the event loop, allowing a concurrent checkin
    # to create a newer game_close snapshot and prune the one we're about to push.
    # We re-resolve the snapshot AFTER this call to avoid a FileNotFoundError.
    await create_snapshot(
        session=session,
        machine=machine,
        conn_kwargs=conn_kwargs,
        save_dir=save_dir,
        label="pre_sync",
        sync_operation_id=None,
        update_characters=False,
    )

    # Re-resolve the snapshot after yielding — a concurrent checkin may have
    # created a newer snapshot and pruned the previous one off disk.
    result = await session.execute(snap_query)
    snapshot = result.scalar_one_or_none()

    snapshot_dir: Path | None = None
    if snapshot:
        candidate = cfg.data_dir / snapshot.snapshot_path
        if candidate.exists():
            snapshot_dir = candidate

    # snapshot_dir_ref lets the _push closure see any re-resolution above.
    snapshot_dir_ref = [snapshot_dir]

    def _push() -> tuple[int, int]:
        sd = snapshot_dir_ref[0]
        with ssh_mod.get_sftp(**conn_kwargs) as (ssh, sftp):
            if ssh_mod.check_d2r_running(ssh, is_windows):
                raise RuntimeError(
                    f"D2R.exe is currently running on {machine.upper()}. "
                    "Please close the game before syncing."
                )

            all_remote = ssh_mod.list_all_files(sftp, save_dir)
            removed = 0
            for f in all_remote:
                if f["filename"].endswith(".d2s") or f["filename"].endswith(".d2i"):
                    sftp.remove(ssh_mod.normalize_path(f["path"]))
                    removed += 1

            _PUSH_EXCLUDED = {"settings.json"}
            uploaded = 0
            if sd:
                for local_file in sorted(sd.iterdir()):
                    if local_file.is_file() and local_file.name.lower() not in _PUSH_EXCLUDED:
                        remote = ssh_mod.normalize_path(f"{save_dir}/{local_file.name}")
                        sftp.put(str(local_file), remote)
                        uploaded += 1

        return removed, uploaded

    removed, uploaded = await asyncio.to_thread(_push)
    log.info("push_snapshot: removed=%d uploaded=%d on %s", removed, uploaded, machine)
    return removed, uploaded


async def run_sync(
    *,
    session: AsyncSession,
    operation: SyncOperation,
    source_machine: str,  # "pc" | "deck"
    dest_machine: str,
    source_conn: dict,
    dest_conn: dict,
    source_dir: str,
    dest_dir: str,
    source_is_windows: bool,
    dest_is_windows: bool,
    staged_path: Path | None = None,
) -> None:
    """
    Execute the full sync flow. Updates operation status in the DB.
    source_conn / dest_conn are dicts with keys: host, port, username, password, key_path
    If staged_path is set, source files are read from local staging dir instead of SFTP.
    """
    cfg = get_settings()
    tmp_dir = cfg.tmp_dir / str(operation.id)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    try:
        operation.status = "running"
        await session.commit()
        print(f"[sync] op_id={operation.id} starting: {source_machine} → {dest_machine}", flush=True)

        # --- 1. Preflight: check D2R is not running ---
        def _preflight():
            # Only check source over SSH if not using staged files (source may be offline)
            if staged_path is None:
                with ssh_mod.get_sftp(**source_conn) as (ssh, _sftp):
                    if ssh_mod.check_d2r_running(ssh, source_is_windows):
                        raise RuntimeError(
                            f"D2R.exe is currently running on {source_machine.upper()}. "
                            "Please close the game before syncing."
                        )
            with ssh_mod.get_sftp(**dest_conn) as (ssh, _sftp):
                if ssh_mod.check_d2r_running(ssh, dest_is_windows):
                    raise RuntimeError(
                        f"D2R.exe is currently running on {dest_machine.upper()}. "
                        "Please close the game before syncing."
                    )

        await asyncio.to_thread(_preflight)

        # --- 2+3. List and obtain source files ---
        EXCLUDED_FILES = {"settings.json"}

        if staged_path is not None:
            # Use locally staged files — source machine does not need to be reachable
            def _copy_staged():
                downloaded = []
                staged_files = [p for p in staged_path.iterdir() if p.is_file()]
                d2s_found = any(p.suffix == ".d2s" for p in staged_files)
                if not d2s_found:
                    raise RuntimeError(f"No .d2s files found in staged directory {staged_path}")
                for src_file in staged_files:
                    if src_file.name.lower() in EXCLUDED_FILES:
                        continue
                    local = tmp_dir / f"{src_file.name}.part"
                    shutil.copy2(str(src_file), str(local))
                    stat = local.stat()
                    downloaded.append({
                        "filename": src_file.name,
                        "path": str(src_file),
                        "size": stat.st_size,
                        "modified_at": stat.st_mtime,
                        "local_part": local,
                        "bytes": stat.st_size,
                    })
                return downloaded

            downloaded = await asyncio.to_thread(_copy_staged)
        else:
            # Original path: list and download from source over SFTP
            def _list_source():
                with ssh_mod.get_sftp(**source_conn) as (_ssh, sftp):
                    return ssh_mod.list_all_files(sftp, source_dir)

            source_files = await asyncio.to_thread(_list_source)

            # Sanity check: confirm this is actually a D2R save directory
            d2s_files = [f for f in source_files if f["filename"].endswith(".d2s")]
            if not d2s_files:
                raise RuntimeError(f"No .d2s files found in {source_dir} on {source_machine.upper()}")

            files_to_sync = [f for f in source_files if f["filename"].lower() not in EXCLUDED_FILES]

            def _download_source():
                result = []
                with ssh_mod.get_sftp(**source_conn) as (_ssh, sftp):
                    for file_info in files_to_sync:
                        remote = ssh_mod.normalize_path(file_info["path"])
                        local = tmp_dir / f"{file_info['filename']}.part"
                        bytes_dl = _sftp_download(sftp, remote, local)
                        result.append({**file_info, "local_part": local, "bytes": bytes_dl})
                return result

            downloaded = await asyncio.to_thread(_download_source)

        # --- 4. Validate .d2s files ---
        char_snapshots: dict[str, dict] = {}
        for item in downloaded:
            if not item["filename"].endswith(".d2s"):
                continue
            try:
                char = parse_d2s(item["local_part"])
                snap = char.to_dict()
                snap["filename"] = item["filename"]
                char_snapshots[item["filename"]] = snap
            except D2SParseError as e:
                raise RuntimeError(f"Validation failed for {item['filename']}: {e}") from e

        # --- 5+6. Backup destination files before overwriting ---
        await create_snapshot(
            session=session,
            machine=dest_machine,
            conn_kwargs=dest_conn,
            save_dir=dest_dir,
            label="pre_sync",
            sync_operation_id=operation.id,
        )

        # --- 7. Upload source files to dest ---
        def _upload_dest():
            results = []
            with ssh_mod.get_sftp(**dest_conn) as (_ssh, sftp):
                for item in downloaded:
                    remote = ssh_mod.normalize_path(
                        f"{dest_dir}/{item['filename']}"
                    )
                    part_path = item["local_part"]
                    bytes_up = _sftp_upload(sftp, part_path, remote)
                    results.append({**item, "bytes_up": bytes_up})
            return results

        upload_results = await asyncio.to_thread(_upload_dest)

        # --- 8. Record file records ---
        for item in upload_results:
            fname = item["filename"]
            record = SyncFileRecord(
                sync_operation_id=operation.id,
                filename=fname,
                source_machine=source_machine,
                dest_machine=dest_machine,
                bytes_transferred=item.get("bytes_up", 0),
                success=True,
                char_snapshot=char_snapshots.get(fname) if fname.endswith(".d2s") else None,
            )
            session.add(record)

        operation.file_count = len(upload_results)
        operation.status = "success"
        operation.completed_at = datetime.utcnow()
        await session.commit()
        print(f"[sync] op_id={operation.id} success: {len(upload_results)} files synced", flush=True)

        from backend.services.event_bus import emit
        emit("sync_complete", direction=operation.direction or "manual")

        # --- 8b. Update character DB from synced files ---
        from backend.routers.characters import upsert_characters

        char_list = [
            {
                **snap,
                "modified_at": next(
                    (it["modified_at"] for it in upload_results if it["filename"] == fname),
                    0.0,
                ),
            }
            for fname, snap in char_snapshots.items()
        ]
        await upsert_characters(session, char_list)

        # --- 8c. Process Holy Grail portal tab ---
        try:
            from backend.services.grail_service import process_portal_tab_hook
            await process_portal_tab_hook(
                session=session,
                downloaded=downloaded,
            )
        except Exception as _grail_err:
            log.warning("Grail hook failed (sync unaffected): %s", _grail_err)

        # --- 8d. Check season milestones ---
        try:
            from backend.services.seasons_service import check_season_milestones
            await check_season_milestones(session=session, downloaded=downloaded)
        except Exception as _season_err:
            log.warning("Seasons hook failed (sync unaffected): %s", _season_err)

    except Exception as e:
        log.error("Sync operation %d failed: %s", operation.id, e)
        operation.status = "failed"
        operation.error_message = str(e)
        operation.completed_at = datetime.utcnow()
        await session.commit()
        raise

    finally:
        # --- 10. Cleanup tmp ---
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)


async def _prune_backups(session: AsyncSession, cfg, label: str) -> None:
    """
    Delete oldest backup snapshots beyond retention limits for the given label group.

    Retention rules (total across all platforms):
      - "game_close" / "manual": keep 1 total
      - "pre_sync": keep 5 total
      - "pre_grail_*": keep 5 total
      - "pre_vault_*": keep 5 total
      - anything else: no-op
    """
    if label in ("game_close", "manual"):
        result = await session.execute(
            select(BackupSnapshot)
            .where(BackupSnapshot.label.in_(["game_close", "manual"]))
            .order_by(BackupSnapshot.created_at.desc())
        )
        keep = 1
    elif label == "pre_sync":
        result = await session.execute(
            select(BackupSnapshot)
            .where(BackupSnapshot.label == "pre_sync")
            .order_by(BackupSnapshot.created_at.desc())
        )
        keep = 5
    elif label.startswith("pre_grail"):
        result = await session.execute(
            select(BackupSnapshot)
            .where(BackupSnapshot.label.like("pre_grail%"))
            .order_by(BackupSnapshot.created_at.desc())
        )
        keep = 5
    elif label.startswith("pre_vault"):
        result = await session.execute(
            select(BackupSnapshot)
            .where(BackupSnapshot.label.like("pre_vault%"))
            .order_by(BackupSnapshot.created_at.desc())
        )
        keep = 5
    elif label == "pre_season_reward":
        result = await session.execute(
            select(BackupSnapshot)
            .where(BackupSnapshot.label == "pre_season_reward")
            .order_by(BackupSnapshot.created_at.desc())
        )
        keep = 5
    elif label == "season_archive":
        # Season archives are never auto-pruned — lifecycle managed via Season records
        return
    else:
        return

    snapshots = result.scalars().all()
    if len(snapshots) <= keep:
        return

    to_delete = snapshots[keep:]
    for snap in to_delete:
        snap_path = cfg.data_dir / snap.snapshot_path
        if snap_path.exists():
            shutil.rmtree(snap_path, ignore_errors=True)
        await session.delete(snap)

    await session.commit()
