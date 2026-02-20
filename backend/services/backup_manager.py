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
from sqlalchemy import select, delete

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
        EXCLUDED_FILES = {"Settings.json"}

        if staged_path is not None:
            # Use locally staged files — source machine does not need to be reachable
            def _copy_staged():
                downloaded = []
                staged_files = [p for p in staged_path.iterdir() if p.is_file()]
                d2s_found = any(p.suffix == ".d2s" for p in staged_files)
                if not d2s_found:
                    raise RuntimeError(f"No .d2s files found in staged directory {staged_path}")
                for src_file in staged_files:
                    if src_file.name in EXCLUDED_FILES:
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

            files_to_sync = [f for f in source_files if f["filename"] not in EXCLUDED_FILES]

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
                char_snapshots[item["filename"]] = char.to_dict()
            except D2SParseError as e:
                raise RuntimeError(f"Validation failed for {item['filename']}: {e}") from e

        # --- 5. Backup destination files ---
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_subdir = cfg.backups_dir / dest_machine / timestamp
        backup_subdir.mkdir(parents=True, exist_ok=True)

        def _backup_dest():
            backed_up = []
            with ssh_mod.get_sftp(**dest_conn) as (_ssh, sftp):
                dest_files = ssh_mod.list_all_files(sftp, dest_dir)
                for file_info in dest_files:
                    remote = ssh_mod.normalize_path(file_info["path"])
                    local = backup_subdir / file_info["filename"]
                    _sftp_download(sftp, remote, local)
                    backed_up.append(file_info["filename"])
            return backed_up

        backed_up_files = await asyncio.to_thread(_backup_dest)

        # Parse backed-up characters for snapshot metadata
        backup_chars = []
        for fname in backed_up_files:
            if fname.endswith(".d2s"):
                try:
                    c = parse_d2s(backup_subdir / fname)
                    backup_chars.append(c.to_dict())
                except D2SParseError:
                    pass

        # --- 6. Record snapshot ---
        snapshot = BackupSnapshot(
            source_machine=dest_machine,
            snapshot_path=str(backup_subdir.relative_to(cfg.data_dir)),
            file_count=len(backed_up_files),
            characters=backup_chars,
            sync_operation_id=operation.id,
        )
        session.add(snapshot)
        await session.commit()

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

        # --- 9. Prune old backups ---
        await _prune_backups(session, dest_machine, cfg)

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


async def _prune_backups(session: AsyncSession, machine: str, cfg) -> None:
    """Delete oldest backup snapshots beyond retention count."""
    result = await session.execute(
        select(BackupSnapshot)
        .where(BackupSnapshot.source_machine == machine)
        .order_by(BackupSnapshot.created_at.desc())
    )
    snapshots = result.scalars().all()

    if len(snapshots) <= cfg.backup_retention_count:
        return

    to_delete = snapshots[cfg.backup_retention_count:]
    for snap in to_delete:
        # Delete from disk
        snap_path = cfg.data_dir / snap.snapshot_path
        if snap_path.exists():
            shutil.rmtree(snap_path, ignore_errors=True)
        await session.delete(snap)

    await session.commit()
