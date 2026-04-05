from __future__ import annotations

"""
Stash router.

Endpoints:
  GET  /api/stash                         - Download + parse stash, return all tabs + gold
  GET  /api/vault/gold                    - Current vault gold balance for a mode
  POST /api/stash/gold/deposit            - Move gold from stash → vault
  POST /api/stash/gold/withdraw           - Move gold from vault → stash
  POST /api/stash/item/store              - Remove item from stash, save in vault
  GET  /api/vault/items                   - List stored vault items for a mode
  POST /api/vault/items/{id}/retrieve     - Write vault item to tab 5, delete from vault
"""

import logging
from typing import Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.config import get_settings
from backend.database import get_session
from backend.models import VaultItem, GoldVault, BackupSnapshot, Season, ItemStatFeedback
from backend.services.stash_service import QUALITY_NAMES
from backend.services.item_parsing.item_stats import parse_standalone_stats

log = logging.getLogger(__name__)
router = APIRouter(tags=["stash"])

Mode = Literal["sc", "hc"]
Machine = Literal["pc", "deck"]


# ─── Request/Response schemas ─────────────────────────────────────────────────

class StashItemResponse(BaseModel):
    page_item_index: int
    item_type: str
    name: Optional[str]
    base_item: Optional[str]
    quality: int
    quality_name: str
    unique_id: Optional[int]
    set_id: Optional[int]
    is_ear: bool
    is_simple: bool
    item_level: int
    is_ethereal: bool
    is_runeword: bool
    properties: list[str]
    grid_x: int = 0
    grid_y: int = 0
    grid_width: int = 1
    grid_height: int = 1
    quantity: int = 1


class StashTabResponse(BaseModel):
    index: int
    item_count: int
    items: list[StashItemResponse]


class StashResponse(BaseModel):
    machine: str
    hardcore: bool
    gold: int
    vault_gold: int
    tabs: list[StashTabResponse]
    snapshot_at: Optional[str] = None


class StatFeedback(BaseModel):
    confirmed_accurate: bool
    corrected_stats: Optional[list[str]] = None


class VaultItemResponse(BaseModel):
    id: int
    name: Optional[str]
    base_item: Optional[str]
    quality: int
    quality_name: str
    tab: int
    hardcore: bool
    stored_at: str
    catalog_id: Optional[int]
    item_level: int
    is_ethereal: bool
    properties: list[str]
    feedback: Optional[StatFeedback] = None


class StatFeedbackRequest(BaseModel):
    confirmed_accurate: bool
    corrected_stats: Optional[list[str]] = None


class GoldVaultResponse(BaseModel):
    hardcore: bool
    amount: int


class GoldDepositRequest(BaseModel):
    machine: Machine
    mode: Mode
    amount: int


class GoldWithdrawRequest(BaseModel):
    machine: Machine
    mode: Mode
    amount: int


class StoreItemRequest(BaseModel):
    machine: Machine
    mode: Mode
    tab: int
    item_index: int




# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _get_conn_and_dir(session: AsyncSession, machine: Machine):
    """Shared helper: load SSH conn kwargs + save_dir for a machine."""
    from backend.routers.settings import _get_conn_kwargs, _get_setting
    conn = await _get_conn_kwargs(session, machine)
    save_dir = await _get_setting(session, f"{machine}_save_path") or ""
    if not save_dir:
        raise HTTPException(400, f"Save path not configured for {machine}")
    return conn, save_dir


async def _check_not_running(conn: dict, machine: Machine) -> None:
    """Raise 409 if D2R is currently running on the target machine."""
    from backend.services.ssh_client import check_d2r_running, get_sftp
    import asyncio

    def _check():
        with get_sftp(**conn) as (_ssh, _sftp):
            is_windows = machine == "pc"
            return check_d2r_running(_ssh, is_windows)

    try:
        is_running = await asyncio.to_thread(_check)
        if is_running:
            raise HTTPException(
                409,
                f"D2R is currently running on {machine.upper()}. "
                "Close the game before modifying the stash."
            )
    except HTTPException:
        raise
    except Exception as e:
        log.warning("Could not verify D2R is not running on %s: %s — blocking write to be safe", machine, e)
        raise HTTPException(
            409,
            f"Could not verify D2R is not running on {machine.upper()} ({e}). "
            "Close the game and try again."
        )


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.get("/stash", response_model=StashResponse)
async def get_stash(
    mode: Mode = Query(...),
    session: AsyncSession = Depends(get_session),
):
    """Parse the stash from the latest local snapshot (read-only)."""
    from pathlib import Path
    from backend.services.stash_service import fetch_stash_local

    # Only show snapshots from the current active season (after season.started_at).
    # This prevents pre-season saves from appearing in a fresh season before any Check In.
    active_season_result = await session.execute(
        select(Season).where(Season.status == "active")
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

    result = await session.execute(snap_query)
    snap = result.scalar_one_or_none()

    if snap is None:
        no_snap_msg = (
            "No snapshot for the current season yet. Check In from a device first."
            if active_season else
            "No snapshot available. Take a manual snapshot or check in from a device."
        )
        raise HTTPException(404, no_snap_msg)

    local_dir = get_settings().data_dir / snap.snapshot_path
    if not local_dir.exists():
        raise HTTPException(
            404,
            "Snapshot files not found on disk. Take a new snapshot.",
        )

    try:
        data = await fetch_stash_local(
            session=session,
            mode=mode,
            local_dir=local_dir,
            source_machine=snap.source_machine,
        )
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        log.error("Stash fetch failed: %s", e)
        raise HTTPException(500, str(e))

    return StashResponse(
        machine=data["machine"],
        hardcore=data["hardcore"],
        gold=data["gold"],
        vault_gold=data["vault_gold"],
        snapshot_at=snap.created_at.isoformat(),
        tabs=[
            StashTabResponse(
                index=tab["index"],
                item_count=tab["item_count"],
                items=[StashItemResponse(**it) for it in tab["items"]],
            )
            for tab in data["tabs"]
        ],
    )


@router.get("/vault/gold", response_model=GoldVaultResponse)
async def get_vault_gold(
    mode: Mode = Query(...),
    session: AsyncSession = Depends(get_session),
):
    hardcore = mode == "hc"
    result = await session.execute(
        select(GoldVault).where(GoldVault.hardcore == hardcore)
    )
    vault = result.scalar_one_or_none()
    return GoldVaultResponse(
        hardcore=hardcore,
        amount=vault.amount if vault else 0,
    )


@router.post("/stash/gold/deposit")
async def deposit_gold(
    body: GoldDepositRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    """Move gold from stash into the vault. D2R must not be running."""
    from backend.services.stash_service import deposit_gold as _deposit

    from backend.services.auto_sync import guard_mothership_write
    await guard_mothership_write(session)

    conn, save_dir = await _get_conn_and_dir(session, body.machine)
    await _check_not_running(conn, body.machine)

    try:
        result = await _deposit(
            session=session,
            machine=body.machine,
            mode=body.mode,
            amount=body.amount,
            conn=conn,
            save_dir=save_dir,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        log.error("Gold deposit failed: %s", e)
        raise HTTPException(500, str(e))

    # Check if any gold_vault milestones are now met
    try:
        from backend.services.seasons_service import check_gold_milestones
        await check_gold_milestones(session)
    except Exception as e:
        log.warning("Gold milestone check failed (non-fatal): %s", e)

    from backend.services.auto_sync import trigger_mothership_push
    await trigger_mothership_push(background_tasks, session)

    return {"success": True, "stash_gold": result["stash_gold"], "vault_gold": result["vault_gold"]}


@router.post("/stash/gold/withdraw")
async def withdraw_gold(
    body: GoldWithdrawRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    """Move gold from vault into the stash. D2R must not be running."""
    from backend.services.stash_service import withdraw_gold as _withdraw

    from backend.services.auto_sync import guard_mothership_write
    await guard_mothership_write(session)

    conn, save_dir = await _get_conn_and_dir(session, body.machine)
    await _check_not_running(conn, body.machine)

    try:
        result = await _withdraw(
            session=session,
            machine=body.machine,
            mode=body.mode,
            amount=body.amount,
            conn=conn,
            save_dir=save_dir,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        log.error("Gold withdraw failed: %s", e)
        raise HTTPException(500, str(e))

    from backend.services.auto_sync import trigger_mothership_push
    await trigger_mothership_push(background_tasks, session)

    return {"success": True, "stash_gold": result["stash_gold"], "vault_gold": result["vault_gold"]}


@router.post("/stash/item/store")
async def store_item(
    body: StoreItemRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    """Remove an item from the stash and save it in the vault. D2R must not be running."""
    from backend.services.stash_service import store_item as _store

    from backend.services.auto_sync import guard_mothership_write
    await guard_mothership_write(session)

    conn, save_dir = await _get_conn_and_dir(session, body.machine)
    await _check_not_running(conn, body.machine)

    try:
        result = await _store(
            session=session,
            machine=body.machine,
            mode=body.mode,
            tab=body.tab,
            item_index=body.item_index,
            conn=conn,
            save_dir=save_dir,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        log.error("Item store failed: %s", e)
        raise HTTPException(500, str(e))

    from backend.services.auto_sync import trigger_mothership_push
    await trigger_mothership_push(background_tasks, session)

    return {"success": True, **result}


@router.get("/vault/items", response_model=list[VaultItemResponse])
async def list_vault_items(
    mode: Mode = Query(...),
    session: AsyncSession = Depends(get_session),
):
    hardcore = mode == "hc"
    result = await session.execute(
        select(VaultItem)
        .where(VaultItem.hardcore == hardcore)
        .order_by(VaultItem.stored_at.desc())
    )
    items = result.scalars().all()

    feedback_result = await session.execute(
        select(ItemStatFeedback).where(
            ItemStatFeedback.vault_item_id.in_([i.id for i in items])
        )
    )
    feedback_map = {f.vault_item_id: f for f in feedback_result.scalars()}

    return [
        VaultItemResponse(
            id=item.id,
            name=item.name,
            base_item=item.base_item,
            quality=item.quality,
            quality_name=QUALITY_NAMES.get(item.quality, "unknown"),
            tab=item.tab,
            hardcore=item.hardcore,
            stored_at=item.stored_at.isoformat(),
            catalog_id=item.catalog_id,
            item_level=item.item_level,
            is_ethereal=item.is_ethereal,
            properties=parse_standalone_stats(item.raw_item_bytes) if item.raw_item_bytes else [],
            feedback=(
                StatFeedback(
                    confirmed_accurate=feedback_map[item.id].confirmed_accurate,
                    corrected_stats=feedback_map[item.id].corrected_stats,
                )
                if item.id in feedback_map else None
            ),
        )
        for item in items
    ]


@router.get("/stash/item-bytes")
async def get_stash_item_bytes(
    mode: Mode = Query(...),
    tab: int = Query(...),
    index: int = Query(...),
    session: AsyncSession = Depends(get_session),
):
    """
    Return the raw hex bytes for a single item from the latest local snapshot.
    No SSH required — reads from disk.  Use this to grab bytes for season rewards.
    """
    from backend.services.stash_service import _mode_hardcore, _stash_filename
    from backend.services.item_parsing import parse_stash

    result = await session.execute(
        select(BackupSnapshot)
        .where(BackupSnapshot.label.in_(["manual", "game_close"]))
        .order_by(BackupSnapshot.created_at.desc())
        .limit(1)
    )
    snap = result.scalar_one_or_none()
    if snap is None:
        raise HTTPException(404, "No snapshot available")

    local_dir = get_settings().data_dir / snap.snapshot_path
    hardcore = _mode_hardcore(mode)
    local_path = local_dir / _stash_filename(hardcore)
    if not local_path.exists():
        raise HTTPException(404, "Stash file not found in snapshot")

    stash = parse_stash(local_path, hardcore=hardcore)

    if tab >= len(stash.pages):
        raise HTTPException(400, f"Tab {tab} out of range")
    page = stash.pages[tab]
    if index >= len(page.items):
        raise HTTPException(400, f"Item index {index} out of range (tab has {len(page.items)} items)")

    item = page.items[index]
    raw = bytes(page.raw_bytes[item.byte_start:item.byte_end])
    hex_spaced = " ".join(f"{b:02x}" for b in raw)

    return {
        "hex": hex_spaced,
        "byte_len": len(raw),
        "display_name": item.display_name,
        "quality": item.quality,
        "quality_name": QUALITY_NAMES.get(item.quality, "unknown"),
        "item_type": item.item_type.strip(),
    }


@router.get("/vault/items/{item_id}/bytes")
async def get_vault_item_bytes(
    item_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Return the raw hex bytes for a vault item (already stored in DB)."""
    item = await session.get(VaultItem, item_id)
    if item is None:
        raise HTTPException(404, "Vault item not found")
    if not item.raw_item_bytes:
        raise HTTPException(404, "No raw bytes stored for this item")

    raw = bytes(item.raw_item_bytes)
    hex_spaced = " ".join(f"{b:02x}" for b in raw)

    return {
        "hex": hex_spaced,
        "byte_len": len(raw),
        "display_name": item.name or item.base_item or "Unknown",
        "quality": item.quality,
        "quality_name": QUALITY_NAMES.get(item.quality, "unknown"),
        "item_type": item.item_code,
    }


@router.get("/stash/debug")
async def get_stash_debug(
    machine: Machine = Query(...),
    mode: Mode = Query(...),
    tab: int = Query(0),
    session: AsyncSession = Depends(get_session),
):
    """
    Debugging endpoint: return raw hex bytes + parsed fields for each item in
    a specific stash tab. Used to reverse-engineer the Modern format item type
    encoding by comparing bytes across known item types.

    Usage:
      GET /api/stash/debug?machine=pc&mode=sc&tab=0
    """
    import asyncio
    import tempfile
    from pathlib import Path
    from backend.services.item_parsing import parse_stash

    conn, save_dir = await _get_conn_and_dir(session, machine)

    hardcore = mode == "hc"
    filename = (
        "ModernSharedStashHardCoreV2.d2i" if hardcore
        else "ModernSharedStashSoftCoreV2.d2i"
    )

    from backend.services import ssh_client as ssh_mod
    from backend.services.backup_manager import _sftp_download

    remote_path = ssh_mod.normalize_path(f"{save_dir}/{filename}")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp) / filename

        def _download():
            with ssh_mod.get_sftp(**conn) as (_ssh, sftp):
                _sftp_download(sftp, remote_path, tmp_path)

        await asyncio.to_thread(_download)
        stash = parse_stash(tmp_path, hardcore=hardcore)

    if tab >= len(stash.pages):
        raise HTTPException(400, f"Tab {tab} does not exist (stash has {len(stash.pages)} pages)")

    page = stash.pages[tab]
    items_out = []
    for i, item in enumerate(page.items):
        raw = bytes(page.raw_bytes[item.byte_start:item.byte_end])
        items_out.append({
            "index": i,
            "byte_len": len(raw),
            "raw_hex": raw.hex(),
            # Annotated nibble view for readability: groups of 2 hex chars
            "raw_bytes_spaced": " ".join(raw.hex()[j:j+2] for j in range(0, len(raw.hex()), 2)),
            "quality": item.quality,
            "quality_name": QUALITY_NAMES.get(item.quality, "unknown"),
            "item_level": item.item_level,
            "is_simple": item.is_simple,
            "is_ear": item.is_ear,
            "is_ethereal": item.is_ethereal,
            "unique_id": item.unique_id,
            "set_id": item.set_id,
            "properties": [],
        })

    return {
        "machine": machine,
        "mode": mode,
        "tab": tab,
        "item_count": len(page.items),
        "items": items_out,
    }


@router.post("/vault/items/{item_id}/feedback")
async def save_stat_feedback(
    item_id: int,
    body: StatFeedbackRequest,
    session: AsyncSession = Depends(get_session),
):
    """Upsert stat feedback for a vault item (for parser calibration)."""
    item = await session.get(VaultItem, item_id)
    if item is None:
        raise HTTPException(404, "Vault item not found")

    result = await session.execute(
        select(ItemStatFeedback).where(ItemStatFeedback.vault_item_id == item_id)
    )
    existing = result.scalar_one_or_none()

    from datetime import datetime
    if existing:
        existing.confirmed_accurate = body.confirmed_accurate
        existing.corrected_stats = body.corrected_stats
        existing.updated_at = datetime.utcnow()
    else:
        session.add(ItemStatFeedback(
            vault_item_id=item_id,
            confirmed_accurate=body.confirmed_accurate,
            corrected_stats=body.corrected_stats,
        ))

    await session.commit()
    return {"success": True}


@router.get("/stat-feedback/export")
async def export_stat_feedback(session: AsyncSession = Depends(get_session)):
    """Export all vault items with feedback for parser calibration analysis."""
    result = await session.execute(
        select(ItemStatFeedback).order_by(ItemStatFeedback.vault_item_id)
    )
    feedbacks = result.scalars().all()

    out = []
    for fb in feedbacks:
        item = await session.get(VaultItem, fb.vault_item_id)
        if item is None:
            continue
        parsed = parse_standalone_stats(item.raw_item_bytes) if item.raw_item_bytes else []
        out.append({
            "vault_item_id": item.id,
            "item_name": item.name or item.base_item,
            "item_type": item.item_code,
            "item_level": item.item_level,
            "hex_bytes": bytes(item.raw_item_bytes).hex() if item.raw_item_bytes else "",
            "parsed_stats": parsed,
            "corrected_stats": fb.corrected_stats,
            "confirmed_accurate": fb.confirmed_accurate,
        })
    return out


@router.post("/vault/items/{item_id}/retrieve")
async def retrieve_vault_item(
    item_id: int,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    """Write a stored vault item to tab 5 of the local snapshot. No SSH required — Sync to Device will push it."""
    from backend.services.auto_sync import guard_mothership_write
    from backend.services.stash_service import retrieve_vault_item as _retrieve

    await guard_mothership_write(session)

    try:
        display_name = await _retrieve(session=session, vault_item_id=item_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        log.error("Vault retrieve failed: %s", e)
        raise HTTPException(500, str(e))

    from backend.services.auto_sync import trigger_mothership_push
    await trigger_mothership_push(background_tasks, session)

    return {
        "success": True,
        "message": f"{display_name} written to stash tab 5 in vault snapshot",
    }
