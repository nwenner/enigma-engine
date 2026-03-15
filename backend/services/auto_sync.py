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


_DEFAULT_STATE = {"status": "idle", "direction": None, "detected_at": None, "expires_at": None, "reason": None}


async def _get_state() -> dict:
    raw = await _get_autosync_setting("autosync_state")
    if not raw:
        return dict(_DEFAULT_STATE)
    try:
        return json.loads(raw)
    except Exception:
        return dict(_DEFAULT_STATE)


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


async def _push_to_machine(dest: str) -> None:
    """Push the latest vault snapshot to a single destination machine. Best-effort."""
    from backend.services.backup_manager import push_snapshot_to_machine

    is_windows = dest == "pc"
    log.warning("mothership_push: starting push to %s", dest)
    async with AsyncSessionLocal() as session:
        try:
            conn_kwargs = await _get_conn_kwargs(session, dest)
            save_dir = await _get_setting(session, f"{dest}_save_path") or ""
            removed, uploaded = await push_snapshot_to_machine(session, dest, conn_kwargs, save_dir, is_windows)
            log.warning("mothership_push: %s complete — removed %d, uploaded %d file(s)", dest, removed, uploaded)
        except Exception as exc:
            log.warning("mothership_push: push to %s failed (best-effort): %s", dest, exc)


async def guard_mothership_write(session) -> None:
    """Raise HTTP 409 if D2R is running on any auto-sync-enabled machine.

    Call this before any mothership write (grail, vault, rewards, demon, boss summon).
    No-op if auto-sync is disabled or no machines are reachable.
    Checks all enabled machines in parallel to minimize latency.
    """
    from fastapi import HTTPException

    enabled = await _get_setting(session, "autosync_enabled") or "false"
    if enabled.lower() != "true":
        return

    pc_enabled = await _get_setting(session, "autosync_pc_enabled") or "false"
    deck_enabled = await _get_setting(session, "autosync_deck_enabled") or "false"

    targets = []
    if pc_enabled.lower() == "true":
        targets.append(("pc", True))
    if deck_enabled.lower() == "true":
        targets.append(("deck", False))

    if not targets:
        return

    async def _check_one(machine: str, is_windows: bool) -> tuple[str, bool | None]:
        running = await _check_d2r(machine, is_windows)
        return machine, running

    results = await asyncio.gather(*[_check_one(m, w) for m, w in targets])

    for machine, is_running in results:
        if is_running is True:
            raise HTTPException(
                409,
                f"D2R is currently running on {machine.upper()}. "
                "Close the game before making changes — auto-sync would push them to the live device.",
            )


async def trigger_mothership_push(
    background_tasks,  # fastapi.BackgroundTasks
    session,           # AsyncSession — used to read settings
) -> None:
    """Schedule background pushes to all auto-sync-enabled machines.
    Called after any mothership write operation. No-op if auto-sync is disabled."""
    enabled = await _get_setting(session, "autosync_enabled") or "false"
    if enabled.lower() != "true":
        return

    pc_enabled = await _get_setting(session, "autosync_pc_enabled") or "false"
    deck_enabled = await _get_setting(session, "autosync_deck_enabled") or "false"

    targets = []
    if pc_enabled.lower() == "true":
        background_tasks.add_task(_push_to_machine, "pc")
        targets.append("pc")
    if deck_enabled.lower() == "true":
        background_tasks.add_task(_push_to_machine, "deck")
        targets.append("deck")

    if targets:
        log.warning("mothership_push: scheduled push to: %s", ", ".join(targets))


async def _auto_push_to_dest(direction: str) -> None:
    """Push the latest vault snapshot to the destination machine."""
    from backend.services.backup_manager import push_snapshot_to_machine

    dest = "deck" if direction == "pc_to_deck" else "pc"
    async with AsyncSessionLocal() as session:
        try:
            dest_conn = await _get_conn_kwargs(session, dest)
            dest_dir = await _get_setting(session, f"{dest}_save_path") or ""
        except Exception as exc:
            log.error("auto_sync: could not get dest conn kwargs: %s", exc)
            return

    dest_is_windows = dest == "pc"
    try:
        async with AsyncSessionLocal() as session:
            await push_snapshot_to_machine(session, dest, dest_conn, dest_dir, dest_is_windows)
        log.info("auto_sync: pushed snapshot to %s", dest)
    except Exception as exc:
        log.error("auto_sync: push to %s failed: %s", dest, exc)


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
    snapshot_files = [f for f in snapshot_dir.iterdir() if f.is_file()]
    downloaded = [{"filename": f.name, "local_part": f} for f in snapshot_files]

    # Run grail hook against snapshot files — dest may be offline so source-only detection
    try:
        from backend.services.grail_service import process_portal_tab_hook
        log.warning("Grail: snapshot hook running, files: %s", [f.name for f in snapshot_files])
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

    try:
        from backend.services.seasons_service import check_season_milestones
        async with AsyncSessionLocal() as s:
            await check_season_milestones(session=s, downloaded=downloaded)
    except Exception as _err:
        log.warning("Seasons hook failed during auto-checkin (snapshot unaffected): %s", _err)

    try:
        from backend.services.boss_summon_service import check_boss_summon_progress
        async with AsyncSessionLocal() as s:
            await check_boss_summon_progress(session=s, snapshot_dir=snapshot_dir)
    except Exception as _err:
        log.warning("Boss summon hook failed during auto-checkin (snapshot unaffected): %s", _err)

    return snapshot_dir, snapshot.file_count


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

            pc_enabled = (await _get_autosync_setting("autosync_pc_enabled") or "true").lower() == "true"
            deck_enabled = (await _get_autosync_setting("autosync_deck_enabled") or "true").lower() == "true"

            # Check for expired pending state
            state = await _get_state()
            if state["status"] == "pending" and state.get("expires_at"):
                try:
                    expires = datetime.fromisoformat(state["expires_at"])
                    if expires.tzinfo is None:
                        expires = expires.replace(tzinfo=timezone.utc)
                    if datetime.now(timezone.utc) > expires:
                        log.info("auto_sync: pending state expired, clearing")
                        await _set_state(dict(_DEFAULT_STATE))
                        state = await _get_state()
                except Exception:
                    pass

            # If there's a pending sync, try to execute it now that dest may be online
            if state["status"] == "pending" and state.get("direction"):
                direction = state["direction"]
                dest = "deck" if direction == "pc_to_deck" else "pc"
                dest_is_windows = dest == "pc"
                dest_alive = await _get_d2s_mtimes(dest, dest_is_windows)
                if dest_alive is not None:
                    log.info("auto_sync: dest %s is now reachable, pushing pending snapshot", dest)
                    await _set_state(dict(_DEFAULT_STATE))
                    asyncio.create_task(_auto_push_to_dest(direction))

            # Poll D2R state (skip unregistered machines)
            pc_now = await _check_d2r("pc", True) if pc_enabled else None
            deck_now = await _check_d2r("deck", False) if deck_enabled else None

            for machine, now_val, was_val, is_windows in [
                ("pc", pc_now, prev["pc"], True),
                ("deck", deck_now, prev["deck"], False),
            ]:
                if was_val is True and now_val is False:
                    # Game just closed on this machine
                    log.warning("auto_sync: D2R closed on %s", machine)
                    direction = "pc_to_deck" if machine == "pc" else "deck_to_pc"
                    dest = "deck" if machine == "pc" else "pc"
                    dest_is_windows = dest == "pc"

                    # Don't overwrite an unresolved conflict — user must resolve first
                    cur_state = await _get_state()
                    if cur_state["status"] == "conflict":
                        log.info("auto_sync: unresolved conflict — skipping game-close trigger on %s", machine)
                        continue

                    # Check dest for unseen saves (conflict detection)
                    last_sync_time = await _get_last_sync_time()
                    if last_sync_time is not None:
                        dest_has_new = await _has_new_saves(dest, dest_is_windows, last_sync_time)
                        if dest_has_new is True:
                            log.warning("auto_sync: conflict detected (both machines have new saves)")
                            now_iso = datetime.now(timezone.utc).isoformat()
                            await _set_state({
                                "status": "conflict",
                                "direction": None,
                                "detected_at": now_iso,
                                "expires_at": None,
                                "reason": "Both PC and Deck have unseen saves since last sync",
                            })
                            asyncio.create_task(notify_conflict())
                            continue

                    # Check-in from source: creates game_close snapshot + runs all hooks
                    try:
                        _snapshot_dir, count = await _snapshot_source(machine, is_windows)
                        log.info("auto_sync: checked in %d files from %s", count, machine)
                    except Exception as exc:
                        log.warning("auto_sync: check-in snapshot failed: %s", exc)
                        continue

                    # Push to dest or record pending
                    dest_alive = await _get_d2s_mtimes(dest, dest_is_windows)
                    if dest_alive is not None:
                        asyncio.create_task(_auto_push_to_dest(direction))
                    else:
                        now_iso = datetime.now(timezone.utc).isoformat()
                        expires_iso = (datetime.now(timezone.utc) + timedelta(days=PENDING_EXPIRY_DAYS)).isoformat()
                        await _set_state({
                            "status": "pending",
                            "direction": direction,
                            "detected_at": now_iso,
                            "expires_at": expires_iso,
                            "reason": f"Waiting for {dest} to come online",
                        })
                        log.info("auto_sync: %s offline, snapshot in vault, state=pending", dest)

            # Update prev state only for successful checks
            if pc_now is not None:
                prev["pc"] = pc_now
            if deck_now is not None:
                prev["deck"] = deck_now

        except Exception as exc:
            log.error("auto_sync: unexpected error in watcher loop: %s", exc, exc_info=True)

        await asyncio.sleep(interval)
