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

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.database import get_session
from backend.models import VaultItem, GoldVault
from backend.services.stash_service import QUALITY_NAMES

log = logging.getLogger(__name__)
router = APIRouter(tags=["stash"])

Mode = Literal["sc", "hc"]
Machine = Literal["pc", "deck"]


# ─── Request/Response schemas ─────────────────────────────────────────────────

class StashItemResponse(BaseModel):
    page_item_index: int
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
    properties: list[str]


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


class VaultRetrieveRequest(BaseModel):
    machine: Machine
    mode: Mode


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
        log.warning("Could not verify D2R is not running: %s", e)


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.get("/stash", response_model=StashResponse)
async def get_stash(
    machine: Machine = Query(...),
    mode: Mode = Query(...),
    session: AsyncSession = Depends(get_session),
):
    """Download and parse the current stash from a machine (read-only)."""
    from backend.services.stash_service import fetch_stash

    conn, save_dir = await _get_conn_and_dir(session, machine)

    try:
        data = await fetch_stash(
            session=session,
            machine=machine,
            mode=mode,
            conn=conn,
            save_dir=save_dir,
        )
    except Exception as e:
        log.error("Stash fetch failed: %s", e)
        raise HTTPException(500, str(e))

    return StashResponse(
        machine=data["machine"],
        hardcore=data["hardcore"],
        gold=data["gold"],
        vault_gold=data["vault_gold"],
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
    session: AsyncSession = Depends(get_session),
):
    """Move gold from stash into the vault. D2R must not be running."""
    from backend.services.stash_service import deposit_gold as _deposit

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

    return {"success": True, "stash_gold": result["stash_gold"], "vault_gold": result["vault_gold"]}


@router.post("/stash/gold/withdraw")
async def withdraw_gold(
    body: GoldWithdrawRequest,
    session: AsyncSession = Depends(get_session),
):
    """Move gold from vault into the stash. D2R must not be running."""
    from backend.services.stash_service import withdraw_gold as _withdraw

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

    return {"success": True, "stash_gold": result["stash_gold"], "vault_gold": result["vault_gold"]}


@router.post("/stash/item/store")
async def store_item(
    body: StoreItemRequest,
    session: AsyncSession = Depends(get_session),
):
    """Remove an item from the stash and save it in the vault. D2R must not be running."""
    from backend.services.stash_service import store_item as _store

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
            properties=item.properties or [],
        )
        for item in items
    ]


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
    from backend.services.d2i_parser import parse_d2i

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
        stash = parse_d2i(tmp_path)

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
            "p1_unique_id": item.p1_unique_id,
            "p1_set_id": item.p1_set_id,
            "properties": item.properties,
        })

    return {
        "machine": machine,
        "mode": mode,
        "tab": tab,
        "item_count": page.item_count,
        "items": items_out,
    }


@router.post("/vault/items/{item_id}/retrieve")
async def retrieve_vault_item(
    item_id: int,
    body: VaultRetrieveRequest,
    session: AsyncSession = Depends(get_session),
):
    """Write a stored vault item to tab 5 on the target machine. D2R must not be running."""
    from backend.services.stash_service import retrieve_vault_item as _retrieve

    hardcore = body.mode == "hc"
    stash_filename = (
        "ModernSharedStashHardCoreV2.d2i" if hardcore
        else "ModernSharedStashSoftCoreV2.d2i"
    )

    conn, save_dir = await _get_conn_and_dir(session, body.machine)
    await _check_not_running(conn, body.machine)

    try:
        display_name = await _retrieve(
            session=session,
            vault_item_id=item_id,
            machine=body.machine,
            conn=conn,
            save_dir=save_dir,
            stash_filename=stash_filename,
        )
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        log.error("Vault retrieve failed: %s", e)
        raise HTTPException(500, str(e))

    return {
        "success": True,
        "message": f"{display_name} written to stash tab 5 on {body.machine.upper()}",
    }
