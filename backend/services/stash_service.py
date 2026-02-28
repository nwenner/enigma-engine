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

from backend.models import GrailCatalog, VaultItem, GoldVault
from backend.services.d2i_parser import (
    parse_d2i,
    serialize_d2i,
    remove_items_from_page,
    insert_item_into_page,
    validate_page_items,
    MOD_ITEM_NAMES,
)

log = logging.getLogger(__name__)


def _base_item_name(item_type: str) -> str | None:
    """Return a display name for the base item type code, or None if unknown."""
    code = item_type.strip()
    if not code:
        return None
    return MOD_ITEM_NAMES.get(code) or code


def _magic_item_name(magic_prefix: str | None, magic_suffix: str | None, item_type: str) -> str | None:
    """
    Build the full magic item display name: "{prefix} {base} {suffix}".
    Returns None if no affixes are known (caller falls back to base_item display).
    """
    base = _base_item_name(item_type)
    parts: list[str] = []
    if magic_prefix:
        parts.append(magic_prefix)
    if base:
        parts.append(base)
    if magic_suffix:
        parts.append(magic_suffix)
    return " ".join(parts) if (magic_prefix or magic_suffix) and parts else None


QUALITY_NAMES: dict[int, str] = {
    0: "normal",
    1: "inferior",
    2: "superior",
    3: "magic",
    4: "rare",
    5: "set",
    6: "crafted",
    7: "unique",
    8: "tempered",
}

MAX_STASH_GOLD = 12_500_000
PORTAL_TAB_INDEX = 4  # tab 5 = page index 4
VISIBLE_TAB_COUNT = 5  # pages 0-4 are real tabs; page 5 is the terminal marker


def _mode_hardcore(mode: str) -> bool:
    return mode == "hc"


def _stash_filename(hardcore: bool) -> str:
    return "ModernSharedStashHardCoreV2.d2i" if hardcore else "ModernSharedStashSoftCoreV2.d2i"


async def _build_catalog_lookup(
    session: AsyncSession,
    all_page_items: list[list],
) -> dict[tuple, GrailCatalog]:
    """Batch-fetch GrailCatalog entries for all unique/set items across all pages."""
    unique_ids: set[int] = set()
    set_ids: set[int] = set()

    for page_items in all_page_items:
        for item in page_items:
            if item.quality == 7 and item.unique_id is not None:
                unique_ids.add(item.unique_id)
            elif item.quality == 5 and item.set_id is not None:
                set_ids.add(item.set_id)
            # Also collect Phase 1 IDs — Phase 2 may have overridden quality
            # but Phase 1's uid/sid might still be the real catalog key
            if item.p1_unique_id is not None:
                unique_ids.add(item.p1_unique_id)
            if item.p1_set_id is not None:
                set_ids.add(item.p1_set_id)

    lookup: dict[tuple, GrailCatalog] = {}

    if unique_ids:
        result = await session.execute(
            select(GrailCatalog).where(
                GrailCatalog.quality == "unique",
                GrailCatalog.unique_id.in_(unique_ids),
            )
        )
        for cat in result.scalars().all():
            lookup[("unique", cat.unique_id)] = cat

    if set_ids:
        result = await session.execute(
            select(GrailCatalog).where(
                GrailCatalog.quality == "set",
                GrailCatalog.set_id.in_(set_ids),
            )
        )
        for cat in result.scalars().all():
            lookup[("set", cat.set_id)] = cat

    return lookup


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

        stash = parse_d2i(tmp_path)

    # Vault gold for this mode
    vault_result = await session.execute(
        select(GoldVault).where(GoldVault.hardcore == hardcore)
    )
    vault = vault_result.scalar_one_or_none()
    vault_gold = vault.amount if vault else 0

    # Build catalog name lookup
    visible_pages = stash.pages[:VISIBLE_TAB_COUNT]
    catalog_lookup = await _build_catalog_lookup(session, [p.items for p in visible_pages])

    tabs = []
    for page_idx, page in enumerate(visible_pages):
        items_out = []
        for item_idx, item in enumerate(page.items):
            cat: Optional[GrailCatalog] = None
            display_quality = item.quality
            display_unique_id = item.unique_id
            display_set_id = item.set_id

            # Phase 1 catalog override: only when Phase 2 found a low-confidence
            # quality (q=0 normal, q=1 inferior, q=2 superior — minimal quality
            # data, easy to coincidentally match). When Phase 2 found q=3/4/6/8
            # (magic/rare/crafted/tempered, all with substantial affix data that
            # Phase 2 validates explicitly), trust Phase 2 completely — a Phase 1
            # catalog coincidence would be a regression (e.g. magic charm showing
            # as the set item whose set_id happened to match the false-positive).
            use_p1_catalog = item.quality not in (3, 4, 6, 8)

            if use_p1_catalog and item.p1_unique_id is not None:
                cat = catalog_lookup.get(("unique", item.p1_unique_id))
                if cat:
                    display_quality = 7
                    display_unique_id = item.p1_unique_id
                    display_set_id = None
            if use_p1_catalog and cat is None and item.p1_set_id is not None:
                cat = catalog_lookup.get(("set", item.p1_set_id))
                if cat:
                    display_quality = 5
                    display_unique_id = None
                    display_set_id = item.p1_set_id
            # Standard catalog lookup via Phase 2's uid/sid (or Phase 1 if it won)
            if cat is None:
                if item.quality == 7 and item.unique_id is not None:
                    cat = catalog_lookup.get(("unique", item.unique_id))
                elif item.quality == 5 and item.set_id is not None:
                    cat = catalog_lookup.get(("set", item.set_id))

            # Build display name: catalog > magic full name > rare name > None
            if cat:
                display_name = cat.name
                display_base = cat.base_item
            elif item.quality == 3:
                # Magic item — build "Prefix Base of Suffix" name; base_item is redundant
                display_name = _magic_item_name(item.magic_prefix, item.magic_suffix, item.item_type)
                display_base = None if display_name else _base_item_name(item.item_type)
            elif item.quality in (4, 6) and item.rare_name:
                display_name = item.rare_name
                display_base = _base_item_name(item.item_type)
            else:
                display_name = None
                display_base = _base_item_name(item.item_type)

            items_out.append({
                "page_item_index": item_idx,
                "name": display_name,
                "base_item": display_base,
                "quality": display_quality,
                "quality_name": QUALITY_NAMES.get(display_quality, "unknown"),
                "unique_id": display_unique_id,
                "set_id": display_set_id,
                "is_ear": item.is_ear,
                "is_simple": item.is_simple,
                "item_level": item.item_level,
                "is_ethereal": item.is_ethereal,
                "properties": item.properties,
            })

        tabs.append({
            "index": page_idx,
            "item_count": page.item_count,
            "items": items_out,
        })

    return {
        "machine": machine,
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
        stash = parse_d2i(tmp_path)

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

        new_bytes = serialize_d2i(stash)
        upload_path = Path(tmp) / f"{filename}.out"
        upload_path.write_bytes(new_bytes)

        def _upload():
            with ssh_mod.get_sftp(**conn) as (_ssh, sftp):
                _sftp_upload(sftp, upload_path, remote_path)

        await asyncio.to_thread(_upload)
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
        stash = parse_d2i(tmp_path)

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

        new_bytes = serialize_d2i(stash)
        upload_path = Path(tmp) / f"{filename}.out"
        upload_path.write_bytes(new_bytes)

        def _upload():
            with ssh_mod.get_sftp(**conn) as (_ssh, sftp):
                _sftp_upload(sftp, upload_path, remote_path)

        await asyncio.to_thread(_upload)
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
        stash = parse_d2i(tmp_path)

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
        # Try Phase 1 IDs first (more reliable for catalog matching when Phase 2
        # overrides quality) then fall back to Phase 2's uid/sid.
        cat: Optional[GrailCatalog] = None
        store_quality = item.quality
        use_p1_catalog = item.quality not in (3, 4, 6, 8)
        if use_p1_catalog and item.p1_unique_id is not None:
            result = await session.execute(
                select(GrailCatalog).where(
                    GrailCatalog.quality == "unique",
                    GrailCatalog.unique_id == item.p1_unique_id,
                )
            )
            cat = result.scalar_one_or_none()
            if cat:
                store_quality = 7
        if use_p1_catalog and cat is None and item.p1_set_id is not None:
            result = await session.execute(
                select(GrailCatalog).where(
                    GrailCatalog.quality == "set",
                    GrailCatalog.set_id == item.p1_set_id,
                )
            )
            cat = result.scalar_one_or_none()
            if cat:
                store_quality = 5
        if cat is None and item.quality == 7 and item.unique_id is not None:
            result = await session.execute(
                select(GrailCatalog).where(
                    GrailCatalog.quality == "unique",
                    GrailCatalog.unique_id == item.unique_id,
                )
            )
            cat = result.scalar_one_or_none()
        elif cat is None and item.quality == 5 and item.set_id is not None:
            result = await session.execute(
                select(GrailCatalog).where(
                    GrailCatalog.quality == "set",
                    GrailCatalog.set_id == item.set_id,
                )
            )
            cat = result.scalar_one_or_none()

        modified_page = remove_items_from_page(page, [item_index])
        stash.pages[tab] = modified_page

        new_bytes = serialize_d2i(stash)
        upload_path = Path(tmp) / f"{filename}.out"
        upload_path.write_bytes(new_bytes)

        def _upload():
            with ssh_mod.get_sftp(**conn) as (_ssh, sftp):
                _sftp_upload(sftp, upload_path, remote_path)

        await asyncio.to_thread(_upload)

        # Build stored name and base_item using same logic as fetch_stash
        if cat:
            vault_name = cat.name
            vault_base = cat.base_item
        elif item.quality == 3:
            vault_name = _magic_item_name(item.magic_prefix, item.magic_suffix, item.item_type)
            vault_base = None if vault_name else _base_item_name(item.item_type)
        elif item.quality in (4, 6) and item.rare_name:
            vault_name = item.rare_name
            vault_base = _base_item_name(item.item_type)
        else:
            vault_name = None
            vault_base = _base_item_name(item.item_type)

        vault_item = VaultItem(
            item_code=item.item_type,
            name=vault_name,
            base_item=vault_base,
            quality=store_quality,
            item_level=item.item_level,
            is_ethereal=item.is_ethereal,
            tab=tab,
            hardcore=hardcore,
            raw_item_bytes=item_bytes,
            properties=item.properties,
            stored_at=datetime.now(timezone.utc).replace(tzinfo=None),
            catalog_id=cat.id if cat else None,
        )
        session.add(vault_item)
        await session.commit()

    quality_name = QUALITY_NAMES.get(store_quality, "unknown")
    display_name = vault_name or f"{quality_name} item"
    log.info("Vault: stored %s from tab %d on %s (%s)", display_name, tab, machine, mode)
    return {
        "name": vault_name,
        "quality": store_quality,
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

        stash = parse_d2i(tmp_path)

        if len(stash.pages) <= PORTAL_TAB_INDEX:
            raise RuntimeError(
                f"{stash_filename} has fewer than {PORTAL_TAB_INDEX + 1} pages"
            )

        modified_page = insert_item_into_page(stash.pages[PORTAL_TAB_INDEX], item_bytes)
        stash.pages[PORTAL_TAB_INDEX] = modified_page

        new_bytes = serialize_d2i(stash)
        upload_path = Path(tmp) / f"{stash_filename}.out"
        upload_path.write_bytes(new_bytes)

        def _upload():
            with ssh_mod.get_sftp(**conn) as (_ssh, sftp):
                _sftp_upload(sftp, upload_path, remote_path)

        await asyncio.to_thread(_upload)

    await session.delete(vault_item)
    await session.commit()

    log.info("Vault: retrieved %s to tab 5 on %s", display_name, machine)
    return display_name
