from __future__ import annotations

"""
Stash service: live stash viewing, gold vault operations, and item storage/retrieval.

All stash-modifying operations follow the safety protocol:
  1. Create a full backup snapshot before any modification
  2. Download stash file
  3. Modify in memory
  4. Serialize and upload
"""

import asyncio
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.models import GrailCatalog, VaultItem, GoldVault, BackupSnapshot, Season
from backend.services.catalog_lookup import build_catalog_lookup
from backend.services.item_parsing import ParsedStash, parse_stash, serialize_stash
from backend.services.item_parsing.stash_format import (
    remove_items_from_page,
    insert_item_into_page,
    validate_page_items,
)

log = logging.getLogger(__name__)


QUALITY_NAMES: dict[int, str] = {
    1: "inferior",
    2: "normal",
    3: "superior",
    4: "magic",
    5: "set",
    6: "rare",
    7: "unique",
    8: "crafted",
}

MAX_STASH_GOLD = 12_500_000
PORTAL_TAB_INDEX = 4  # tab 5 = page index 4
VISIBLE_TAB_COUNT = 5  # pages 0-4 are real tabs; page 5 is the terminal marker


def _mode_hardcore(mode: str) -> bool:
    return mode == "hc"


async def _update_local_snapshot_stash(
    session: AsyncSession,
    filename: str,
    stash_bytes: bytes,
) -> None:
    """
    Write modified stash bytes into the latest local snapshot directory.

    This keeps the local snapshot (source of truth for the display) in sync after
    any vault operation that modifies the remote stash file. Without this, the
    display would show stale gold/items until the next Check In.
    """
    from backend.config import get_settings

    active_result = await session.execute(
        select(Season).where(Season.status == "active")
    )
    active_season = active_result.scalar_one_or_none()

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
        log.warning("No local snapshot found to update after vault operation")
        return

    snap_dir = get_settings().data_dir / snap.snapshot_path
    if snap_dir.exists():
        (snap_dir / filename).write_bytes(stash_bytes)
        log.info("Updated local snapshot stash file: %s/%s", snap.snapshot_path, filename)
    else:
        log.warning("Local snapshot directory missing: %s", snap_dir)


def _stash_filename(hardcore: bool) -> str:
    return "ModernSharedStashHardCoreV2.d2i" if hardcore else "ModernSharedStashSoftCoreV2.d2i"




async def fetch_stash(
    session: AsyncSession,
    machine: str,
    mode: str,
    conn: dict,
    save_dir: str,
) -> dict:
    """
    Download and parse the stash file for a machine+mode, returning structured data.
    This is a read-only operation (no backup needed).
    """
    from backend.services import ssh_client as ssh_mod
    from backend.services.backup_manager import _sftp_download

    hardcore = _mode_hardcore(mode)
    filename = _stash_filename(hardcore)
    remote_path = ssh_mod.normalize_path(f"{save_dir}/{filename}")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp) / filename

        def _download():
            with ssh_mod.get_sftp(**conn) as (_ssh, sftp):
                _sftp_download(sftp, remote_path, tmp_path)

        await asyncio.to_thread(_download)

        stash = parse_stash(tmp_path, hardcore=hardcore)

    # Vault gold for this mode
    vault_result = await session.execute(
        select(GoldVault).where(GoldVault.hardcore == hardcore)
    )
    vault = vault_result.scalar_one_or_none()
    vault_gold = vault.amount if vault else 0

    # Build catalog name lookup
    visible_pages = stash.pages[:VISIBLE_TAB_COUNT]
    catalog_lookup = await build_catalog_lookup(session, [p.items for p in visible_pages])

    tabs = []
    for page_idx, page in enumerate(visible_pages):
        items_out = []
        for item_idx, item in enumerate(page.items):
            cat: Optional[GrailCatalog] = None
            if item.quality == 7 and item.unique_id is not None:
                cat = catalog_lookup.get(("unique", item.unique_id))
            elif item.quality == 5 and item.set_id is not None:
                cat = catalog_lookup.get(("set", item.set_id))

            # Build display name: catalog > magic full name > rare name > base
            if cat:
                display_name = cat.name
                display_base = cat.base_item
            elif item.quality == 4:
                # display_name already has "Prefix Base of Suffix" from parser
                display_name = item.display_name
                display_base = None
            elif item.quality in (6, 8) and item.rare_name:
                display_name = item.rare_name
                display_base = item.base_name
            else:
                display_name = None
                display_base = item.base_name

            items_out.append({
                "page_item_index": item_idx,
                "item_type": item.item_type.strip(),
                "name": display_name,
                "base_item": display_base,
                "quality": item.quality,
                "quality_name": QUALITY_NAMES.get(item.quality, "unknown"),
                "unique_id": item.unique_id,
                "set_id": item.set_id,
                "is_ear": item.is_ear,
                "is_simple": item.is_simple,
                "item_level": item.item_level,
                "is_ethereal": item.is_ethereal,
                "properties": [],
            })

        tabs.append({
            "index": page_idx,
            "item_count": len(page.items),
            "items": items_out,
        })

    return {
        "machine": machine,
        "hardcore": hardcore,
        "gold": stash.gold,
        "vault_gold": vault_gold,
        "tabs": tabs,
    }


async def fetch_stash_local(
    session: AsyncSession,
    mode: str,
    local_dir: Path,
    source_machine: str = "unknown",
) -> dict:
    """
    Parse the stash file from a local snapshot directory (no SSH required).
    Same return shape as fetch_stash.
    """
    hardcore = _mode_hardcore(mode)
    filename = _stash_filename(hardcore)
    local_path = local_dir / filename

    if not local_path.exists():
        raise FileNotFoundError(f"Stash file {filename} not found in snapshot directory")

    stash = parse_stash(local_path, hardcore=hardcore)

    # Vault gold for this mode
    vault_result = await session.execute(
        select(GoldVault).where(GoldVault.hardcore == hardcore)
    )
    vault = vault_result.scalar_one_or_none()
    vault_gold = vault.amount if vault else 0

    # Build catalog name lookup
    visible_pages = stash.pages[:VISIBLE_TAB_COUNT]
    catalog_lookup = await build_catalog_lookup(session, [p.items for p in visible_pages])

    tabs = []
    for page_idx, page in enumerate(visible_pages):
        items_out = []
        for item_idx, item in enumerate(page.items):
            cat: Optional[GrailCatalog] = None
            if item.quality == 7 and item.unique_id is not None:
                cat = catalog_lookup.get(("unique", item.unique_id))
            elif item.quality == 5 and item.set_id is not None:
                cat = catalog_lookup.get(("set", item.set_id))

            # Build display name: catalog > magic full name > rare name > base
            if cat:
                display_name = cat.name
                display_base = cat.base_item
            elif item.quality == 4:
                display_name = item.display_name
                display_base = None
            elif item.quality in (6, 8) and item.rare_name:
                display_name = item.rare_name
                display_base = item.base_name
            else:
                display_name = None
                display_base = item.base_name

            items_out.append({
                "page_item_index": item_idx,
                "item_type": item.item_type.strip(),
                "name": display_name,
                "base_item": display_base,
                "quality": item.quality,
                "quality_name": QUALITY_NAMES.get(item.quality, "unknown"),
                "unique_id": item.unique_id,
                "set_id": item.set_id,
                "is_ear": item.is_ear,
                "is_simple": item.is_simple,
                "item_level": item.item_level,
                "is_ethereal": item.is_ethereal,
                "properties": [],
            })

        tabs.append({
            "index": page_idx,
            "item_count": len(page.items),
            "items": items_out,
        })

    return {
        "machine": source_machine,
        "hardcore": hardcore,
        "gold": stash.gold,
        "vault_gold": vault_gold,
        "tabs": tabs,
    }


async def deposit_gold(
    session: AsyncSession,
    machine: str,
    mode: str,
    amount: int,
    conn: dict,
    save_dir: str,
) -> dict:
    """
    Move `amount` gold from the stash into the GoldVault.

    SAFETY: Creates backup before any stash modification.
    """
    from backend.services import ssh_client as ssh_mod
    from backend.services.backup_manager import _sftp_download, _sftp_upload, create_snapshot

    if amount <= 0:
        raise ValueError("Amount must be positive")

    hardcore = _mode_hardcore(mode)
    filename = _stash_filename(hardcore)
    remote_path = ssh_mod.normalize_path(f"{save_dir}/{filename}")

    await create_snapshot(
        session=session,
        machine=machine,
        conn_kwargs=conn,
        save_dir=save_dir,
        label="pre_vault_gold",
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp) / filename

        def _download():
            with ssh_mod.get_sftp(**conn) as (_ssh, sftp):
                _sftp_download(sftp, remote_path, tmp_path)

        await asyncio.to_thread(_download)
        stash = parse_stash(tmp_path, hardcore=hardcore)

        if stash.gold < amount:
            raise ValueError(f"Stash only has {stash.gold:,} gold; cannot deposit {amount:,}")

        stash.gold -= amount

        vault_result = await session.execute(
            select(GoldVault).where(GoldVault.hardcore == hardcore)
        )
        vault = vault_result.scalar_one_or_none()
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if vault is None:
            vault = GoldVault(hardcore=hardcore, amount=amount, last_updated=now)
            session.add(vault)
        else:
            vault.amount += amount
            vault.last_updated = now

        new_bytes = serialize_stash(stash)
        upload_path = Path(tmp) / f"{filename}.out"
        upload_path.write_bytes(new_bytes)

        def _upload():
            with ssh_mod.get_sftp(**conn) as (_ssh, sftp):
                _sftp_upload(sftp, upload_path, remote_path)

        await asyncio.to_thread(_upload)
        await _update_local_snapshot_stash(session, filename, new_bytes)
        await session.commit()

    log.info("Vault: deposited %d gold from %s (%s)", amount, machine, mode)
    return {"stash_gold": stash.gold, "vault_gold": vault.amount}


async def withdraw_gold(
    session: AsyncSession,
    machine: str,
    mode: str,
    amount: int,
    conn: dict,
    save_dir: str,
) -> dict:
    """
    Move `amount` gold from the GoldVault into the stash.

    SAFETY: Creates backup before any stash modification.
    """
    from backend.services import ssh_client as ssh_mod
    from backend.services.backup_manager import _sftp_download, _sftp_upload, create_snapshot

    if amount <= 0:
        raise ValueError("Amount must be positive")

    hardcore = _mode_hardcore(mode)
    filename = _stash_filename(hardcore)
    remote_path = ssh_mod.normalize_path(f"{save_dir}/{filename}")

    vault_result = await session.execute(
        select(GoldVault).where(GoldVault.hardcore == hardcore)
    )
    vault = vault_result.scalar_one_or_none()
    vault_amount = vault.amount if vault else 0
    if vault_amount < amount:
        raise ValueError(f"Vault only has {vault_amount:,} gold; cannot withdraw {amount:,}")

    await create_snapshot(
        session=session,
        machine=machine,
        conn_kwargs=conn,
        save_dir=save_dir,
        label="pre_vault_gold",
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp) / filename

        def _download():
            with ssh_mod.get_sftp(**conn) as (_ssh, sftp):
                _sftp_download(sftp, remote_path, tmp_path)

        await asyncio.to_thread(_download)
        stash = parse_stash(tmp_path, hardcore=hardcore)

        if stash.gold + amount > MAX_STASH_GOLD:
            max_withdraw = MAX_STASH_GOLD - stash.gold
            raise ValueError(
                f"Stash gold cap is {MAX_STASH_GOLD:,}. "
                f"Stash already has {stash.gold:,}; max additional is {max_withdraw:,}."
            )

        stash.gold += amount
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        vault.amount -= amount
        vault.last_updated = now

        new_bytes = serialize_stash(stash)
        upload_path = Path(tmp) / f"{filename}.out"
        upload_path.write_bytes(new_bytes)

        def _upload():
            with ssh_mod.get_sftp(**conn) as (_ssh, sftp):
                _sftp_upload(sftp, upload_path, remote_path)

        await asyncio.to_thread(_upload)
        await _update_local_snapshot_stash(session, filename, new_bytes)
        await session.commit()

    log.info("Vault: withdrew %d gold to %s (%s)", amount, machine, mode)
    return {"stash_gold": stash.gold, "vault_gold": vault.amount}


async def store_item(
    session: AsyncSession,
    machine: str,
    mode: str,
    tab: int,
    item_index: int,
    conn: dict,
    save_dir: str,
) -> dict:
    """
    Remove item at (tab, item_index) from the stash and save it as a VaultItem.

    SAFETY: Creates backup before any stash modification.
    """
    from backend.services import ssh_client as ssh_mod
    from backend.services.backup_manager import _sftp_download, _sftp_upload, create_snapshot

    hardcore = _mode_hardcore(mode)
    filename = _stash_filename(hardcore)
    remote_path = ssh_mod.normalize_path(f"{save_dir}/{filename}")

    await create_snapshot(
        session=session,
        machine=machine,
        conn_kwargs=conn,
        save_dir=save_dir,
        label="pre_vault_store",
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp) / filename

        def _download():
            with ssh_mod.get_sftp(**conn) as (_ssh, sftp):
                _sftp_download(sftp, remote_path, tmp_path)

        await asyncio.to_thread(_download)
        stash = parse_stash(tmp_path, hardcore=hardcore)

        if tab >= len(stash.pages):
            raise ValueError(f"Tab {tab} does not exist (stash has {len(stash.pages)} pages)")

        page = stash.pages[tab]

        if not validate_page_items(page):
            raise RuntimeError(f"Tab {tab} failed item validation — aborting to protect stash")

        if item_index >= len(page.items):
            raise ValueError(
                f"Tab {tab} has {len(page.items)} items; index {item_index} out of range"
            )

        item = page.items[item_index]
        item_bytes = bytes(page.raw_bytes[item.byte_start:item.byte_end])

        # Look up catalog for name/base_item.
        cat: Optional[GrailCatalog] = None
        if item.quality == 7 and item.unique_id is not None:
            result = await session.execute(
                select(GrailCatalog).where(
                    GrailCatalog.quality == "unique",
                    GrailCatalog.unique_id == item.unique_id,
                )
            )
            cat = result.scalar_one_or_none()
        elif item.quality == 5 and item.set_id is not None:
            result = await session.execute(
                select(GrailCatalog).where(
                    GrailCatalog.quality == "set",
                    GrailCatalog.set_id == item.set_id,
                )
            )
            cat = result.scalar_one_or_none()

        modified_page = remove_items_from_page(page, [item_index])
        stash.pages[tab] = modified_page

        new_bytes = serialize_stash(stash)
        upload_path = Path(tmp) / f"{filename}.out"
        upload_path.write_bytes(new_bytes)

        def _upload():
            with ssh_mod.get_sftp(**conn) as (_ssh, sftp):
                _sftp_upload(sftp, upload_path, remote_path)

        await asyncio.to_thread(_upload)
        await _update_local_snapshot_stash(session, filename, new_bytes)

        # Build stored name and base_item using same logic as fetch_stash
        if cat:
            vault_name = cat.name
            vault_base = cat.base_item
        elif item.quality == 4:
            vault_name = item.display_name
            vault_base = None
        elif item.quality in (6, 8) and item.rare_name:
            vault_name = item.rare_name
            vault_base = item.base_name
        else:
            vault_name = None
            vault_base = item.base_name

        vault_item = VaultItem(
            item_code=item.item_type,
            name=vault_name,
            base_item=vault_base,
            quality=item.quality,
            item_level=item.item_level,
            is_ethereal=item.is_ethereal,
            tab=tab,
            hardcore=hardcore,
            raw_item_bytes=item_bytes,
            properties=[],
            stored_at=datetime.now(timezone.utc).replace(tzinfo=None),
            catalog_id=cat.id if cat else None,
        )
        session.add(vault_item)
        await session.commit()

    quality_name = QUALITY_NAMES.get(item.quality, "unknown")
    display_name = vault_name or f"{quality_name} item"
    log.info("Vault: stored %s from tab %d on %s (%s)", display_name, tab, machine, mode)
    return {
        "name": vault_name,
        "quality": item.quality,
        "quality_name": quality_name,
    }


async def retrieve_vault_item(
    session: AsyncSession,
    vault_item_id: int,
    machine: str,
    conn: dict,
    save_dir: str,
    stash_filename: str,
) -> str:
    """
    Write the stored item to tab 5 of the target machine's stash, then delete the VaultItem.

    SAFETY: Creates backup before any stash modification.
    Returns the item's display name.
    """
    from backend.services import ssh_client as ssh_mod
    from backend.services.backup_manager import _sftp_download, _sftp_upload, create_snapshot

    result = await session.execute(
        select(VaultItem).where(VaultItem.id == vault_item_id)
    )
    vault_item = result.scalar_one_or_none()
    if vault_item is None:
        raise ValueError(f"VaultItem {vault_item_id} not found")

    item_bytes = vault_item.raw_item_bytes
    display_name = vault_item.name or f"quality={vault_item.quality} item"

    await create_snapshot(
        session=session,
        machine=machine,
        conn_kwargs=conn,
        save_dir=save_dir,
        label="pre_vault_retrieve",
    )

    remote_path = ssh_mod.normalize_path(f"{save_dir}/{stash_filename}")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp) / stash_filename

        def _download():
            with ssh_mod.get_sftp(**conn) as (_ssh, sftp):
                _sftp_download(sftp, remote_path, tmp_path)

        await asyncio.to_thread(_download)

        hardcore = "HardCore" in stash_filename
        stash = parse_stash(tmp_path, hardcore=hardcore)

        if len(stash.pages) <= PORTAL_TAB_INDEX:
            raise RuntimeError(
                f"{stash_filename} has fewer than {PORTAL_TAB_INDEX + 1} pages"
            )

        modified_page = insert_item_into_page(stash.pages[PORTAL_TAB_INDEX], item_bytes)
        stash.pages[PORTAL_TAB_INDEX] = modified_page

        new_bytes = serialize_stash(stash)
        upload_path = Path(tmp) / f"{stash_filename}.out"
        upload_path.write_bytes(new_bytes)

        def _upload():
            with ssh_mod.get_sftp(**conn) as (_ssh, sftp):
                _sftp_upload(sftp, upload_path, remote_path)

        await asyncio.to_thread(_upload)
        await _update_local_snapshot_stash(session, stash_filename, new_bytes)

    await session.delete(vault_item)
    await session.commit()

    log.info("Vault: retrieved %s to tab 5 on %s", display_name, machine)
    return display_name
