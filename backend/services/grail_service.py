from __future__ import annotations

"""
Grail service: processes the portal tab (tab 5) of D2R shared stash files,
registers unique/set items in the grail database, and provides item retrieval.
"""
import asyncio
import logging
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.models import GrailCatalog, GrailEntry
from backend.services.item_parsing import (
    ParsedItem,
    ParsedStash,
    parse_stash,
    serialize_stash,
)
from backend.services.item_parsing.stash_format import (
    remove_items_from_page,
    insert_item_into_page,
    validate_page_items,
)

log = logging.getLogger(__name__)

# Map stash filenames to hardcore flag (Modern format only)
STASH_FILES: dict[str, bool] = {
    "ModernSharedStashSoftCoreV2.d2i": False,
    "ModernSharedStashHardCoreV2.d2i": True,
}

PORTAL_TAB_INDEX = 4  # 0-indexed; tab 5 is index 4

# Item quality values
QUALITY_SET = 5
QUALITY_UNIQUE = 7


# ─── Catalog lookup ───────────────────────────────────────────────────────────

async def _lookup_catalog(
    session: AsyncSession,
    item: ParsedItem,
) -> GrailCatalog | None:
    """Find the matching catalog entry for an item."""
    if item.quality == QUALITY_UNIQUE and item.unique_id is not None:
        result = await session.execute(
            select(GrailCatalog).where(
                GrailCatalog.unique_id == item.unique_id,
                GrailCatalog.quality == "unique",
            )
        )
        return result.scalar_one_or_none()

    if item.quality == QUALITY_SET and item.set_id is not None:
        item_code = item.item_type.rstrip()
        query = select(GrailCatalog).where(
            GrailCatalog.set_id == item.set_id,
            GrailCatalog.quality == "set",
        )
        if item_code:
            query = query.where(GrailCatalog.item_code == item_code)
        result = await session.execute(query)
        return result.scalar_one_or_none()

    return None


# ─── Grail entry upsert ───────────────────────────────────────────────────────

async def _upsert_grail_entry(
    session: AsyncSession,
    catalog: GrailCatalog,
    raw_item_bytes: bytes,
    hardcore: bool,
    is_deposited: bool = False,
    increment_count: bool = True,
) -> None:
    """
    INSERT or UPDATE grail entry.

    Args:
        increment_count: If False, only update deposited state without incrementing find_count.
    """
    result = await session.execute(
        select(GrailEntry).where(
            GrailEntry.catalog_id == catalog.id,
            GrailEntry.hardcore == hardcore,
        )
    )
    entry = result.scalar_one_or_none()

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    if entry is None:
        entry = GrailEntry(
            catalog_id=catalog.id,
            hardcore=hardcore,
            found_at=now,
            last_found_at=now,
            find_count=1,
            raw_item_bytes=raw_item_bytes,
            raw_item_bit_len=len(raw_item_bytes) * 8,
            is_deposited=is_deposited,
        )
        session.add(entry)
    else:
        if increment_count:
            entry.find_count += 1
            entry.last_found_at = now
        if entry.raw_item_bytes is None:
            entry.raw_item_bytes = raw_item_bytes
            entry.raw_item_bit_len = len(raw_item_bytes) * 8
        if is_deposited:
            entry.is_deposited = True


# ─── Portal tab processing ────────────────────────────────────────────────────

async def process_portal_tab_hook(
    session: AsyncSession,
    downloaded: list[dict],
    source_conn: dict | None = None,
    source_dir: str | None = None,
) -> None:
    """
    For each downloaded .d2i stash file:
      1. Parse tab 5 (page index 4)
      2. Find unique/set items
      3. Upsert into grail_entries (DB only — stash files are never modified here)

    This function MUST NOT raise — errors are logged as warnings.
    """
    for file_info in downloaded:
        filename = file_info.get("filename", "")
        if filename not in STASH_FILES:
            continue

        hardcore = STASH_FILES[filename]
        local_part: Path = file_info["local_part"]

        try:
            stash = parse_stash(local_part, hardcore=hardcore)
        except Exception as e:
            log.warning("Grail: failed to parse %s: %s", filename, e)
            continue

        if len(stash.pages) <= PORTAL_TAB_INDEX:
            log.warning("Grail: %s has fewer than %d pages", filename, PORTAL_TAB_INDEX + 1)
            continue

        portal_page = stash.pages[PORTAL_TAB_INDEX]
        log.debug("Grail: %s tab 5 has %d items", filename, len(portal_page.items))

        if not validate_page_items(portal_page):
            log.warning("Grail: %s tab 5 failed validation — skipping", filename)
            continue

        registered = 0
        for idx, item in enumerate(portal_page.items):
            if item.quality not in (QUALITY_UNIQUE, QUALITY_SET):
                continue
            catalog = await _lookup_catalog(session, item)
            if catalog is None:
                continue
            raw_bytes = bytes(portal_page.raw_bytes[item.byte_start : item.byte_end])
            try:
                await _upsert_grail_entry(session, catalog, raw_bytes, hardcore, is_deposited=False)
                registered += 1
                log.info(
                    "Grail: registered %s (quality=%d, %s) - NOT deposited yet",
                    catalog.name,
                    item.quality,
                    "HC" if hardcore else "SC",
                )
            except Exception as e:
                log.warning("Grail: failed to upsert %s: %s", catalog.name, e)

        if registered:
            await session.commit()


# ─── Explicit deposit ─────────────────────────────────────────────────────────

async def deposit_tab5(
    session: AsyncSession,
    machine: str,
    conn: dict,
    save_dir: str,
) -> dict:
    """
    On-demand deposit flow triggered by the user from the UI.

    CRITICAL SAFETY PROTOCOL:
      0. **BACKUP entire save directory FIRST** (required before ANY stash modification)
      1. Download current stash
      2. Parse tab 5
      3. Register unique/set items in DB
      4. Remove those items from tab 5
      5. Round-trip validate (parse serialized bytes, confirm counts)
      6. Upload modified stash back

    Returns a summary dict: { "registered": [...names], "skipped": [...names], "errors": [...msgs] }
    """
    from backend.services import ssh_client as ssh_mod
    from backend.services.backup_manager import _sftp_download, _sftp_upload, create_snapshot

    log.info("BACKUP: Creating pre-grail-deposit backup for %s", machine)
    try:
        await create_snapshot(
            session=session,
            machine=machine,
            conn_kwargs=conn,
            save_dir=save_dir,
            label="pre_grail_deposit",
        )
        log.info("BACKUP: Pre-grail-deposit backup created successfully")
    except Exception as e:
        log.error("BACKUP FAILED: Cannot proceed with deposit: %s", e)
        raise RuntimeError(f"Pre-deposit backup failed: {e}") from e

    registered_names: list[str] = []
    skipped_names: list[str] = []
    errors: list[str] = []

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)

        for filename, hardcore in STASH_FILES.items():
            remote_path = ssh_mod.normalize_path(f"{save_dir}/{filename}")
            local_path = tmp_dir / filename

            def _download(rp=remote_path, lp=local_path):
                with ssh_mod.get_sftp(**conn) as (_ssh, sftp):
                    try:
                        _sftp_download(sftp, rp, lp)
                        return True
                    except (FileNotFoundError, IOError):
                        return False

            exists = await asyncio.to_thread(_download)
            if not exists:
                log.debug("Deposit: %s not found on %s, skipping", filename, machine)
                continue

            try:
                stash = parse_stash(local_path, hardcore=hardcore)
            except Exception as e:
                errors.append(f"{filename}: parse failed — {e}")
                log.warning("Deposit: failed to parse %s: %s", filename, e)
                continue

            if len(stash.pages) <= PORTAL_TAB_INDEX:
                errors.append(f"{filename}: fewer than {PORTAL_TAB_INDEX + 1} pages")
                continue

            portal_page = stash.pages[PORTAL_TAB_INDEX]

            if not validate_page_items(portal_page):
                errors.append(f"{filename}: tab 5 failed item validation — skipping to protect stash")
                log.warning("Deposit: %s tab 5 failed validation", filename)
                continue

            if len(portal_page.items) == 0:
                log.debug("Deposit: %s tab 5 is empty", filename)
                continue

            indices_to_remove: list[int] = []
            items_to_deposit: list[tuple[int, GrailCatalog, bytes]] = []
            seen_catalog_ids: set[int] = set()

            for idx, item in enumerate(portal_page.items):
                if item.quality not in (QUALITY_UNIQUE, QUALITY_SET):
                    skipped_names.append(f"{filename}[{idx}] quality={item.quality}")
                    continue

                catalog = await _lookup_catalog(session, item)
                raw_bytes = bytes(portal_page.raw_bytes[item.byte_start : item.byte_end])

                if catalog is not None:
                    if catalog.id in seen_catalog_ids:
                        skipped_names.append(f"{catalog.name}: duplicate in tab 5, leaving in stash")
                        log.info("Deposit: %s already processed this run, skipping duplicate", catalog.name)
                        continue
                    seen_catalog_ids.add(catalog.id)

                    check_result = await session.execute(
                        select(GrailEntry).where(
                            GrailEntry.catalog_id == catalog.id,
                            GrailEntry.hardcore == hardcore,
                        )
                    )
                    existing = check_result.scalar_one_or_none()

                    if existing is None:
                        try:
                            await _upsert_grail_entry(session, catalog, raw_bytes, hardcore, is_deposited=False)
                            await session.commit()
                            log.warning(
                                "Deposit: item %s was NOT in DB yet - registered before deposit (%s)",
                                catalog.name,
                                "HC" if hardcore else "SC",
                            )
                        except Exception as e:
                            errors.append(f"{catalog.name}: Failed to register before deposit — {e}")
                            log.error("Deposit: CRITICAL - failed to register %s before deposit: %s", catalog.name, e)
                            continue
                    elif existing.is_deposited:
                        skipped_names.append(f"{catalog.name}: already deposited, leaving in stash")
                        log.info("Deposit: %s is already in vault, skipping", catalog.name)
                        continue

                    items_to_deposit.append((idx, catalog, raw_bytes))
                    indices_to_remove.append(idx)
                else:
                    skipped_names.append(f"{filename}[{idx}] quality={item.quality}: not in catalog, leaving in stash")

            for idx, catalog, raw_bytes in items_to_deposit:
                try:
                    await _upsert_grail_entry(session, catalog, raw_bytes, hardcore, is_deposited=True, increment_count=False)
                    registered_names.append(catalog.name)
                    log.info("Deposit: marked %s as deposited (%s)", catalog.name, "HC" if hardcore else "SC")
                except Exception as e:
                    errors.append(f"{catalog.name}: Failed to mark as deposited — {e}")
                    log.warning("Deposit: failed to mark %s as deposited: %s", catalog.name, e)

            if not indices_to_remove:
                continue

            modified_page = remove_items_from_page(portal_page, indices_to_remove)
            stash.pages[PORTAL_TAB_INDEX] = modified_page

            try:
                new_bytes = serialize_stash(stash)
            except Exception as e:
                errors.append(f"{filename}: serialization failed — {e}")
                log.warning("Deposit: failed to serialize %s: %s", filename, e)
                continue

            # Round-trip validate
            try:
                rt_path = _bytes_path(tmp_dir, filename, new_bytes)
                rt_stash = parse_stash(rt_path, hardcore=hardcore)
                rt_page = rt_stash.pages[PORTAL_TAB_INDEX]
                expected_count = len(portal_page.items) - len(indices_to_remove)
                if len(rt_page.items) != expected_count:
                    raise ValueError(
                        f"round-trip item count mismatch: expected {expected_count}, got {len(rt_page.items)}"
                    )
            except Exception as e:
                errors.append(f"{filename}: round-trip validation failed — {e}. Skipping upload.")
                log.warning("Deposit: round-trip validation failed for %s: %s", filename, e)
                continue

            upload_path = tmp_dir / f"{filename}.out"
            upload_path.write_bytes(new_bytes)

            def _upload(rp=remote_path, lp=upload_path):
                with ssh_mod.get_sftp(**conn) as (_ssh, sftp):
                    _sftp_upload(sftp, lp, rp)

            try:
                await asyncio.to_thread(_upload)
                log.info("Deposit: uploaded modified %s to %s", filename, machine)
            except Exception as e:
                errors.append(f"{filename}: upload failed — {e}")
                log.warning("Deposit: upload failed for %s: %s", filename, e)
                continue

            await session.commit()

    return {
        "registered": registered_names,
        "skipped": skipped_names,
        "errors": errors,
    }


def _bytes_path(tmp_dir: Path, filename: str, data: bytes) -> Path:
    """Write bytes to a temp file and return its path (for round-trip parse)."""
    p = tmp_dir / f"{filename}.rt"
    p.write_bytes(data)
    return p


# ─── Item retrieval ───────────────────────────────────────────────────────────

async def retrieve_item_to_tab5(
    session: AsyncSession,
    catalog_id: int,
    hardcore: bool,
    target_machine: str,
    conn: dict,
    save_dir: str,
    stash_filename: str,
) -> None:
    """
    Inject a stored item into tab 5 of the target machine's stash.

    CRITICAL SAFETY PROTOCOL:
      0. **BACKUP entire save directory FIRST** (required before ANY stash modification)
      1. Load GrailEntry → raw_item_bytes
      2. Download current stash from target machine
      3. Parse; insert item into page 4 (tab 5)
      4. Serialize and upload back
    """
    from backend.services import ssh_client as ssh_mod
    from backend.services.backup_manager import create_snapshot

    result = await session.execute(
        select(GrailEntry).where(
            GrailEntry.catalog_id == catalog_id,
            GrailEntry.hardcore == hardcore,
        )
    )
    entry = result.scalar_one_or_none()
    if entry is None or entry.raw_item_bytes is None:
        raise ValueError("No stored item bytes for this grail entry")

    item_bytes = entry.raw_item_bytes

    log.info("BACKUP: Creating pre-grail-retrieve backup for %s", target_machine)
    try:
        await create_snapshot(
            session=session,
            machine=target_machine,
            conn_kwargs=conn,
            save_dir=save_dir,
            label="pre_grail_retrieve",
        )
        log.info("BACKUP: Pre-grail-retrieve backup created successfully")
    except Exception as e:
        log.error("BACKUP FAILED: Cannot proceed with retrieve: %s", e)
        raise RuntimeError(f"Pre-retrieve backup failed: {e}") from e

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp) / stash_filename
        remote_path = f"{save_dir}/{stash_filename}"

        def _download() -> bool:
            try:
                with ssh_mod.get_sftp(**conn) as (_ssh, sftp):
                    from backend.services.backup_manager import _sftp_download
                    _sftp_download(sftp, ssh_mod.normalize_path(remote_path), tmp_path)
                return True
            except Exception as e:
                raise RuntimeError(f"Failed to download {stash_filename}: {e}") from e

        await asyncio.to_thread(_download)

        try:
            stash = parse_stash(tmp_path, hardcore=hardcore)
        except Exception as e:
            raise RuntimeError(f"Failed to parse {stash_filename}: {e}") from e

        if len(stash.pages) <= PORTAL_TAB_INDEX:
            raise RuntimeError(f"{stash_filename} has fewer than {PORTAL_TAB_INDEX + 1} pages")

        portal_page = stash.pages[PORTAL_TAB_INDEX]
        stash.pages[PORTAL_TAB_INDEX] = insert_item_into_page(portal_page, item_bytes)

        try:
            new_bytes = serialize_stash(stash)
        except Exception as e:
            raise RuntimeError(f"Failed to serialize modified stash: {e}") from e

        tmp_path.write_bytes(new_bytes)

        def _upload() -> None:
            with ssh_mod.get_sftp(**conn) as (_ssh, sftp):
                from backend.services.backup_manager import _sftp_upload
                _sftp_upload(sftp, tmp_path, ssh_mod.normalize_path(remote_path))

        try:
            await asyncio.to_thread(_upload)
        except Exception as e:
            raise RuntimeError(f"Failed to upload modified stash: {e}") from e

        entry.is_deposited = False
        await session.commit()
