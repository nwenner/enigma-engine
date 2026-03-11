from __future__ import annotations

"""
Grail service: processes the portal tab (tab 5) of D2R shared stash files,
registers unique/set items in the grail database, and provides item retrieval.
"""
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.config import get_settings
from backend.models import GrailCatalog, GrailEntry, BackupSnapshot, Season
from backend.services.catalog_lookup import lookup_catalog_item
from backend.services.item_parsing import (
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

QUALITY_NAMES: dict[int, str] = {
    0: "normal", 1: "inferior", 2: "superior", 3: "magic",
    4: "rare", 5: "set", 6: "crafted", 7: "unique", 8: "tempered",
}


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


def _snapshot_dir(snap: BackupSnapshot) -> Path:
    return get_settings().data_dir / snap.snapshot_path


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


# ─── Tab 5 preview (read-only) ───────────────────────────────────────────────

async def preview_tab5(session: AsyncSession) -> list[dict]:
    """
    Read-only scan of tab 5 from the latest snapshot stash files.
    Returns metadata for each item found — no DB writes, no file modifications.
    """
    snap = await _latest_snapshot(session)
    if snap is None:
        return []

    snap_dir = _snapshot_dir(snap)
    results: list[dict] = []

    for filename, hardcore in STASH_FILES.items():
        stash_path = snap_dir / filename
        if not stash_path.exists():
            continue

        try:
            stash = parse_stash(stash_path, hardcore=hardcore)
        except Exception as e:
            log.warning("Preview: failed to parse %s: %s", filename, e)
            continue

        if len(stash.pages) <= PORTAL_TAB_INDEX:
            continue

        portal_page = stash.pages[PORTAL_TAB_INDEX]

        for idx, item in enumerate(portal_page.items):
            catalog = await lookup_catalog_item(session, item)
            already_deposited = False
            if catalog:
                entry_result = await session.execute(
                    select(GrailEntry).where(
                        GrailEntry.catalog_id == catalog.id,
                        GrailEntry.hardcore == hardcore,
                    )
                )
                entry = entry_result.scalar_one_or_none()
                already_deposited = entry is not None and entry.is_deposited

            results.append({
                "stash_filename": filename,
                "item_index": idx,
                "catalog_id": catalog.id if catalog else None,
                "item_name": catalog.name if catalog else item.display_name,
                "base_item": item.base_name,
                "quality_name": QUALITY_NAMES.get(item.quality),
                "item_code": item.item_type.rstrip(),
                "is_ethereal": item.is_ethereal,
                "in_catalog": catalog is not None,
                "already_deposited": already_deposited,
                "hardcore": hardcore,
            })

    return results


# ─── Portal tab processing (check-in hook) ────────────────────────────────────

async def process_portal_tab_hook(
    session: AsyncSession,
    downloaded: list[dict],
    source_conn: dict | None = None,
    source_dir: str | None = None,
) -> None:
    """
    For each downloaded .d2i stash file, scan ALL 5 tabs:
      1. Find unique/set items across all pages
      2. Upsert into grail_entries (DB only — stash files are never modified here)

    Idempotent: items already recorded are not re-counted (increment_count=False).
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

        registered = 0
        for page_idx, page in enumerate(stash.pages):
            if not validate_page_items(page):
                log.warning("Grail: %s page %d failed validation — skipping", filename, page_idx)
                continue

            log.debug("Grail: %s page %d has %d items", filename, page_idx, len(page.items))

            for item in page.items:
                if item.quality not in (QUALITY_UNIQUE, QUALITY_SET):
                    continue
                catalog = await lookup_catalog_item(session, item)
                if catalog is None:
                    continue
                raw_bytes = bytes(page.raw_bytes[item.byte_start : item.byte_end])
                try:
                    await _upsert_grail_entry(
                        session, catalog, raw_bytes, hardcore,
                        is_deposited=False, increment_count=False,
                    )
                    registered += 1
                    log.info(
                        "Grail: registered %s (quality=%d, %s, page=%d)",
                        catalog.name, item.quality, "HC" if hardcore else "SC", page_idx,
                    )
                except Exception as e:
                    log.warning("Grail: failed to upsert %s: %s", catalog.name, e)

        if registered:
            await session.commit()


# ─── Explicit deposit (mothership) ────────────────────────────────────────────

async def deposit_tab5(
    session: AsyncSession,
    catalog_ids: list[int] | None = None,
) -> dict:
    """
    On-demand deposit flow triggered by the user from the UI.

    Reads from the local snapshot (mothership), clears tab 5, writes back.
    User syncs to device afterward.

    CRITICAL SAFETY PROTOCOL:
      0. **BACKUP entire save directory FIRST**
      1. Parse tab 5 of each stash in the latest snapshot
      2. Register unique/set items in DB
      3. Remove those items from tab 5
      4. Round-trip validate
      5. Write modified stash back to snapshot dir

    Args:
        catalog_ids: If provided, only deposit items matching these catalog IDs.
                     If None, deposit all recognized items in tab 5.

    Returns a summary dict: { "registered": [...names], "skipped": [...names], "errors": [...msgs] }
    """
    snap = await _latest_snapshot(session)
    if snap is None:
        raise RuntimeError("No snapshot available. Check In from a device first.")

    snap_dir = _snapshot_dir(snap)

    log.info("BACKUP: Creating pre-grail-deposit backup")
    try:
        await _create_local_backup_snapshot(session, snap, "pre_grail_deposit")
        log.info("BACKUP: Pre-grail-deposit backup created successfully")
    except Exception as e:
        log.error("BACKUP FAILED: Cannot proceed with deposit: %s", e)
        raise RuntimeError(f"Pre-deposit backup failed: {e}") from e

    registered_names: list[str] = []
    skipped_names: list[str] = []
    errors: list[str] = []

    for filename, hardcore in STASH_FILES.items():
        stash_path = snap_dir / filename

        if not stash_path.exists():
            log.debug("Deposit: %s not found in snapshot, skipping", filename)
            continue

        try:
            stash = parse_stash(stash_path, hardcore=hardcore)
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

            catalog = await lookup_catalog_item(session, item)
            raw_bytes = bytes(portal_page.raw_bytes[item.byte_start : item.byte_end])

            if catalog is not None:
                if catalog_ids is not None and catalog.id not in catalog_ids:
                    skipped_names.append(f"{catalog.name}: not selected, leaving in stash")
                    continue

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
                            catalog.name, "HC" if hardcore else "SC",
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
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".d2i", delete=False) as tf:
                tf.write(new_bytes)
                rt_path = Path(tf.name)
            rt_stash = parse_stash(rt_path, hardcore=hardcore)
            rt_path.unlink(missing_ok=True)
            rt_page = rt_stash.pages[PORTAL_TAB_INDEX]
            expected_count = len(portal_page.items) - len(indices_to_remove)
            if len(rt_page.items) != expected_count:
                raise ValueError(
                    f"round-trip item count mismatch: expected {expected_count}, got {len(rt_page.items)}"
                )
        except Exception as e:
            errors.append(f"{filename}: round-trip validation failed — {e}. Skipping write.")
            log.warning("Deposit: round-trip validation failed for %s: %s", filename, e)
            continue

        stash_path.write_bytes(new_bytes)
        log.info("Deposit: wrote modified %s to snapshot", filename)
        await session.commit()

    return {
        "registered": registered_names,
        "skipped": skipped_names,
        "errors": errors,
    }


# ─── Item retrieval (mothership) ──────────────────────────────────────────────

async def retrieve_item_to_tab5(
    session: AsyncSession,
    catalog_id: int,
    hardcore: bool,
    stash_filename: str,
) -> None:
    """
    Inject a stored item into tab 5 of the latest snapshot stash.
    User syncs to device afterward.

    CRITICAL SAFETY PROTOCOL:
      0. **BACKUP entire save directory FIRST**
      1. Load GrailEntry → raw_item_bytes
      2. Parse stash from latest local snapshot
      3. Insert item into page 4 (tab 5)
      4. Write modified stash back to snapshot
    """
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

    snap = await _latest_snapshot(session)
    if snap is None:
        raise RuntimeError("No snapshot available. Check In from a device first.")

    snap_dir = _snapshot_dir(snap)
    stash_path = snap_dir / stash_filename

    if not stash_path.exists():
        raise RuntimeError(f"{stash_filename} not found in latest snapshot")

    log.info("BACKUP: Creating pre-grail-retrieve backup")
    try:
        await _create_local_backup_snapshot(session, snap, "pre_grail_retrieve")
        log.info("BACKUP: Pre-grail-retrieve backup created successfully")
    except Exception as e:
        log.error("BACKUP FAILED: Cannot proceed with retrieve: %s", e)
        raise RuntimeError(f"Pre-retrieve backup failed: {e}") from e

    try:
        stash = parse_stash(stash_path, hardcore=hardcore)
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

    stash_path.write_bytes(new_bytes)
    log.info("Retrieve: wrote modified %s to snapshot", stash_filename)

    entry.is_deposited = False
    await session.commit()
