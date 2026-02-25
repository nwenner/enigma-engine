from __future__ import annotations

"""
Auto-sync background watcher.

Polls both machines for D2R running state. On a True→False transition (game
close), checks for conflicts and triggers a sync automatically.

State is persisted in the Settings KV store:
  autosync_enabled        "true" / "false"  (default "false")
  autosync_poll_interval  seconds as string  (default "30")
  autosync_state          JSON blob

autosync_state shape:
  {
    "status": "idle" | "pending" | "conflict",
    "direction": "pc_to_deck" | "deck_to_pc" | null,
    "detected_at": "<ISO>" | null,
    "expires_at": "<ISO>" | null,
    "reason": "<string>" | null
  }
"""

import asyncio
import json
import logging
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select

from backend.config import get_settings
from backend.database import AsyncSessionLocal
from backend.services.notify import notify_conflict
from backend.models import Settings, SyncOperation
from backend.routers.settings import _get_conn_kwargs, _get_setting
from backend.services.ssh_client import (
    get_sftp,
    check_d2r_running,
    list_d2s_files,
    SSHConnectionError,
)

log = logging.getLogger(__name__)

CONFLICT_THRESHOLD_SECONDS = 60  # buffer for clock skew + upload lag
PENDING_EXPIRY_DAYS = 7
DISABLED_SLEEP = 5  # seconds to sleep when auto-sync is disabled


# ─── Helpers ──────────────────────────────────────────────────────────────────


async def _get_autosync_setting(key: str) -> str | None:
    async with AsyncSessionLocal() as session:
        return await _get_setting(session, key)


async def _set_autosync_setting(key: str, value: str) -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Settings).where(Settings.key == key))
        row = result.scalar_one_or_none()
        if row:
            row.value = value
        else:
            session.add(Settings(key=key, value=value))
        await session.commit()


async def _get_state() -> dict:
    raw = await _get_autosync_setting("autosync_state")
    if not raw:
        return {"status": "idle", "direction": None, "detected_at": None, "expires_at": None, "reason": None}
    try:
        return json.loads(raw)
    except Exception:
        return {"status": "idle", "direction": None, "detected_at": None, "expires_at": None, "reason": None}


async def _set_state(state: dict) -> None:
    await _set_autosync_setting("autosync_state", json.dumps(state))


async def _get_last_sync_time() -> datetime | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(SyncOperation)
            .where(SyncOperation.status == "success")
            .order_by(SyncOperation.completed_at.desc())
            .limit(1)
        )
        op = result.scalar_one_or_none()
        if op and op.completed_at:
            # completed_at is stored as naive UTC
            return op.completed_at.replace(tzinfo=timezone.utc)
        return None


async def _check_d2r(machine: str, is_windows: bool) -> bool | None:
    """Return D2R running state or None on SSH failure."""
    async with AsyncSessionLocal() as session:
        try:
            kwargs = await _get_conn_kwargs(session, machine)
        except Exception:
            return None

    def _do() -> bool:
        with get_sftp(**kwargs) as (ssh, _sftp):
            return check_d2r_running(ssh, is_windows)

    try:
        return await asyncio.to_thread(_do)
    except (SSHConnectionError, Exception) as exc:
        log.warning("auto_sync: could not check D2R on %s: %s", machine, exc)
        return None


async def _get_d2s_mtimes(machine: str, is_windows: bool) -> list[float] | None:
    """Return mtime list of .d2s files on machine, or None on failure."""
    async with AsyncSessionLocal() as session:
        try:
            kwargs = await _get_conn_kwargs(session, machine)
            save_dir = await _get_setting(session, f"{machine}_save_path") or ""
        except Exception:
            return None

    def _do() -> list[float]:
        with get_sftp(**kwargs) as (_ssh, sftp):
            files = list_d2s_files(sftp, save_dir)
            return [f["modified_at"] for f in files if f["filename"].endswith(".d2s")]

    try:
        return await asyncio.to_thread(_do)
    except (SSHConnectionError, Exception) as exc:
        log.warning("auto_sync: could not list .d2s on %s: %s", machine, exc)
        return None


async def _has_new_saves(machine: str, is_windows: bool, since: datetime) -> bool | None:
    """True if any .d2s on machine has mtime > since + threshold. None on failure."""
    mtimes = await _get_d2s_mtimes(machine, is_windows)
    if mtimes is None:
        return None
    threshold = since.timestamp() + CONFLICT_THRESHOLD_SECONDS
    return any(m > threshold for m in mtimes)


async def _trigger_sync(direction: str) -> None:
    """Create a SyncOperation record and dispatch the background task."""
    # Local imports to avoid circular imports at module level
    from backend.routers.sync import do_sync, sync_lock, _build_sync_kwargs

    if sync_lock.locked():
        log.info("auto_sync: sync already in progress, skipping trigger")
        return

    async with AsyncSessionLocal() as session:
        try:
            sync_kwargs = await _build_sync_kwargs(session, direction)
        except Exception as exc:
            log.error("auto_sync: could not build sync kwargs: %s", exc)
            return

        op = SyncOperation(direction=direction, status="pending")
        session.add(op)
        await session.commit()
        await session.refresh(op)
        op_id = op.id

    asyncio.create_task(do_sync(op_id, sync_kwargs))
    log.info("auto_sync: triggered %s (op_id=%d)", direction, op_id)


async def _snapshot_source(machine: str, is_windows: bool) -> tuple[Path, int]:
    """
    Create a game_close BackupSnapshot by downloading all save files from machine.
    Returns (snapshot_dir, file_count). Raises on any failure.
    """
    from backend.services.backup_manager import create_snapshot

    async with AsyncSessionLocal() as session:
        kwargs = await _get_conn_kwargs(session, machine)
        save_dir = await _get_setting(session, f"{machine}_save_path") or ""
        snapshot = await create_snapshot(
            session=session,
            machine=machine,
            conn_kwargs=kwargs,
            save_dir=save_dir,
            label="game_close",
        )

    snapshot_dir = get_settings().data_dir / snapshot.snapshot_path

    # Run grail hook against snapshot files — dest may be offline so source-only detection
    try:
        from backend.services.grail_service import process_portal_tab_hook
        snapshot_files = [f for f in snapshot_dir.iterdir() if f.is_file()]
        log.warning("Grail: snapshot hook running, files: %s", [f.name for f in snapshot_files])
        downloaded = [{"filename": f.name, "local_part": f} for f in snapshot_files]
        async with AsyncSessionLocal() as grail_session:
            await process_portal_tab_hook(
                session=grail_session,
                downloaded=downloaded,
                source_conn=kwargs,
                source_dir=save_dir,
            )
        log.warning("Grail: snapshot hook completed")
    except Exception as _grail_err:
        log.warning("Grail hook failed during snapshot (snapshot unaffected): %s", _grail_err)

    return snapshot_dir, snapshot.file_count


async def _cleanup_staged(staged_path_str: str | None) -> None:
    """
    Remove a staged directory if it exists. No-op if path is None.
    Snapshot dirs (under backups_dir) are managed by the prune system — they are not deleted here.
    """
    if not staged_path_str:
        return
    path = Path(staged_path_str)
    cfg = get_settings()
    # Don't delete snapshot dirs — the prune system owns their lifecycle
    if path.is_relative_to(cfg.backups_dir):
        return

    def _do() -> None:
        shutil.rmtree(str(path), ignore_errors=True)

    await asyncio.to_thread(_do)


async def _trigger_staged_sync(direction: str, staged_path: str) -> None:
    """Like _trigger_sync but passes staged_path so source SFTP is skipped."""
    from backend.routers.sync import do_sync, sync_lock, _build_sync_kwargs

    if sync_lock.locked():
        log.info("auto_sync: sync already in progress, skipping staged trigger")
        return

    async with AsyncSessionLocal() as session:
        try:
            sync_kwargs = await _build_sync_kwargs(session, direction)
        except Exception as exc:
            log.error("auto_sync: could not build sync kwargs for staged sync: %s", exc)
            return

        sync_kwargs["staged_path"] = staged_path

        op = SyncOperation(direction=direction, status="pending")
        session.add(op)
        await session.commit()
        await session.refresh(op)
        op_id = op.id

    asyncio.create_task(do_sync(op_id, sync_kwargs))
    log.info("auto_sync: triggered staged %s (op_id=%d, staged_path=%s)", direction, op_id, staged_path)


# ─── Main watcher loop ────────────────────────────────────────────────────────


async def run_auto_sync_watcher() -> None:
    """Runs forever as an asyncio background task."""
    prev: dict[str, bool | None] = {"pc": None, "deck": None}

    log.warning("auto_sync: watcher started")

    while True:
        interval = 30  # default; overwritten below when enabled
        try:
            enabled_raw = await _get_autosync_setting("autosync_enabled")
            enabled = (enabled_raw or "false").lower() == "true"

            if not enabled:
                await asyncio.sleep(DISABLED_SLEEP)
                continue

            interval_raw = await _get_autosync_setting("autosync_poll_interval")
            try:
                interval = int(interval_raw or "30")
            except ValueError:
                interval = 30

            # Check for expired pending state
            state = await _get_state()
            if state["status"] == "pending" and state.get("expires_at"):
                try:
                    expires = datetime.fromisoformat(state["expires_at"])
                    if expires.tzinfo is None:
                        expires = expires.replace(tzinfo=timezone.utc)
                    if datetime.now(timezone.utc) > expires:
                        log.info("auto_sync: pending state expired, clearing")
                        await _cleanup_staged(state.get("staged_path"))
                        await _set_state({"status": "idle", "direction": None, "detected_at": None, "expires_at": None, "reason": None})
                        state = await _get_state()
                except Exception:
                    pass

            # If there's a pending sync, try to execute it
            if state["status"] == "pending" and state.get("direction"):
                direction = state["direction"]
                dest = "deck" if direction == "pc_to_deck" else "pc"
                dest_is_windows = dest == "pc"
                dest_alive = await _get_d2s_mtimes(dest, dest_is_windows)
                if dest_alive is not None:
                    log.info("auto_sync: dest %s is now reachable, executing pending %s", dest, direction)
                    staged_path = state.get("staged_path")
                    await _set_state({"status": "idle", "direction": None, "detected_at": None, "expires_at": None, "reason": None})
                    if staged_path:
                        await _trigger_staged_sync(direction, staged_path)
                    else:
                        await _trigger_sync(direction)

            # Poll D2R state
            pc_now = await _check_d2r("pc", True)
            deck_now = await _check_d2r("deck", False)

            for machine, now_val, was_val, is_windows in [
                ("pc", pc_now, prev["pc"], True),
                ("deck", deck_now, prev["deck"], False),
            ]:
                if was_val is True and now_val is False:
                    # Game just closed on this machine
                    log.warning("auto_sync: D2R closed on %s, triggering %s", machine, "pc_to_deck" if machine == "pc" else "deck_to_pc")
                    direction = "pc_to_deck" if machine == "pc" else "deck_to_pc"
                    dest = "deck" if machine == "pc" else "pc"
                    dest_is_windows = dest == "pc"

                    last_sync_time = await _get_last_sync_time()

                    if last_sync_time is None:
                        # Never synced — trigger anyway, user has to decide via UI
                        log.info("auto_sync: no prior sync, triggering %s", direction)
                        cur_state = await _get_state()
                        if cur_state["status"] not in ("pending", "conflict"):
                            await _trigger_sync(direction)
                    else:
                        # Check dest for unseen progress
                        dest_has_new = await _has_new_saves(dest, dest_is_windows, last_sync_time)

                        if dest_has_new is True:
                            # Conflict: both machines have progress
                            log.warning("auto_sync: conflict detected (both machines have new saves)")
                            now_iso = datetime.now(timezone.utc).isoformat()
                            await _set_state({
                                "status": "conflict",
                                "direction": None,
                                "detected_at": now_iso,
                                "expires_at": None,
                                "reason": f"Both PC and Deck have unseen saves since last sync",
                            })
                            asyncio.create_task(notify_conflict())
                        elif dest_has_new is None:
                            # Dest offline — stage files then record pending
                            log.info("auto_sync: dest %s offline, staging files from %s", dest, machine)
                            now_iso = datetime.now(timezone.utc).isoformat()
                            expires_iso = (datetime.now(timezone.utc) + timedelta(days=PENDING_EXPIRY_DAYS)).isoformat()

                            cur_state = await _get_state()
                            if cur_state["status"] == "pending" and cur_state.get("staged_path"):
                                pending_source = "pc" if cur_state["direction"] == "pc_to_deck" else "deck"

                                if machine == pending_source:
                                    # Same machine played again — not a conflict, just re-stage
                                    # with the fresher saves (source machine is still online).
                                    log.info(
                                        "auto_sync: %s played again before dest came online; "
                                        "re-staging with fresher saves",
                                        machine,
                                    )
                                    await _cleanup_staged(cur_state["staged_path"])
                                    try:
                                        staged_path, count = await _snapshot_source(machine, is_windows)
                                        log.info("auto_sync: re-staged %d files from %s", count, machine)
                                        await _set_state({
                                            "status": "pending",
                                            "direction": direction,
                                            "staged_path": str(staged_path),
                                            "staged_file_count": count,
                                            "detected_at": now_iso,
                                            "expires_at": expires_iso,
                                            "reason": f"Waiting for {dest} to come online",
                                        })
                                    except Exception as exc:
                                        log.warning(
                                            "auto_sync: re-staging failed (%s), keeping pending without staged files", exc
                                        )
                                        await _set_state({
                                            "status": "pending",
                                            "direction": direction,
                                            "detected_at": now_iso,
                                            "expires_at": expires_iso,
                                            "reason": f"Waiting for {dest} to come online",
                                        })
                                else:
                                    # Different machine played while first machine's staged saves
                                    # are still waiting — genuine conflict.
                                    log.warning(
                                        "auto_sync: conflict — %s closed but %s has staged saves waiting; "
                                        "marking conflict instead of overwriting",
                                        machine, pending_source,
                                    )
                                    await _set_state({
                                        "status": "conflict",
                                        "direction": None,
                                        "detected_at": now_iso,
                                        "expires_at": None,
                                        "staged_path": cur_state["staged_path"],  # preserve for dismiss cleanup
                                        "reason": "Both machines played since last sync. Staged saves waiting. Choose manually.",
                                    })
                                    asyncio.create_task(notify_conflict())
                            else:
                                try:
                                    staged_path, count = await _snapshot_source(machine, is_windows)
                                    log.info("auto_sync: staged %d files from %s", count, machine)
                                    await _set_state({
                                        "status": "pending",
                                        "direction": direction,
                                        "staged_path": str(staged_path),
                                        "staged_file_count": count,
                                        "detected_at": now_iso,
                                        "expires_at": expires_iso,
                                        "reason": f"Waiting for {dest} to come online",
                                    })
                                except Exception as exc:
                                    log.warning(
                                        "auto_sync: staging failed (%s), recording pending without staged files", exc
                                    )
                                    await _set_state({
                                        "status": "pending",
                                        "direction": direction,
                                        "detected_at": now_iso,
                                        "expires_at": expires_iso,
                                        "reason": f"Waiting for {dest} to come online",
                                    })
                        else:
                            # No conflict, dest reachable — sync now
                            cur_state = await _get_state()
                            if cur_state["status"] not in ("pending", "conflict"):
                                await _trigger_sync(direction)

            # Update prev state only for successful checks
            if pc_now is not None:
                prev["pc"] = pc_now
            if deck_now is not None:
                prev["deck"] = deck_now

        except Exception as exc:
            log.error("auto_sync: unexpected error in watcher loop: %s", exc, exc_info=True)

        await asyncio.sleep(interval)
