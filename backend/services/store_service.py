from __future__ import annotations

"""
store_service — Rune Store: buy runes with vault gold or trade same-tier runes.

All write operations work on the latest local snapshot (no SSH required).
Called by: backend/routers/store.py

Safety protocol (same as retrieve_vault_item in stash_service):
  1. create_local_snapshot() before any .d2i modification
  2. Round-trip validate after serialize_stash
  3. Write to disk only when validation passes
"""

import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from backend.models import GoldVault, BackupSnapshot, Season, RuneStoreLibrary
from backend.services.item_parsing import parse_stash, serialize_stash
from backend.services.item_parsing.stash_format import (
    insert_item_into_page,
    remove_items_from_page,
    validate_page_items,
)
from backend.services.item_parsing.tables.item_types import ITEM_TYPES

log = logging.getLogger(__name__)

# ─── Tier / cost constants ────────────────────────────────────────────────────

RUNE_TIERS: dict[str, list[str]] = {
    "low":  [f"r{i:02d}" for i in range(1, 13)],   # r01–r12
    "mid":  [f"r{i:02d}" for i in range(13, 25)],  # r13–r24
    "high": [f"r{i:02d}" for i in range(25, 34)],  # r25–r33
}
TIER_GOLD_COST: dict[str, int] = {
    "low": 500_000,
    "mid": 2_500_000,
    "high": 12_000_000,
}
_CODE_TO_TIER: dict[str, str] = {
    code: tier
    for tier, codes in RUNE_TIERS.items()
    for code in codes
}

PORTAL_TAB_INDEX = 4  # tab 5 = page index 4


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _stash_filename(hardcore: bool) -> str:
    return "ModernSharedStashHardCoreV2.d2i" if hardcore else "ModernSharedStashSoftCoreV2.d2i"


async def _get_latest_snap(session: AsyncSession) -> Optional[BackupSnapshot]:
    """Return the latest manual/game_close snapshot, season-scoped if active."""
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
    return result.scalar_one_or_none()


# ─── Public API ───────────────────────────────────────────────────────────────

async def seed_rune_library(session: AsyncSession, stash_bytes: bytes, hardcore: bool) -> int:
    """
    Parse a stash file and upsert all rune items into RuneStoreLibrary.
    Returns the count of runes seeded (inserted or updated).
    """
    filename = _stash_filename(hardcore)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp) / filename
        tmp_path.write_bytes(stash_bytes)
        stash = parse_stash(tmp_path, hardcore=hardcore)

    count = 0
    for page in stash.pages:
        for item in page.items:
            code = item.item_type.strip()
            if code not in _CODE_TO_TIER:
                continue

            tier = _CODE_TO_TIER[code]
            rune_name = ITEM_TYPES.get(code, code)
            item_bytes = bytes(page.raw_bytes[item.byte_start:item.byte_end])

            # Delete + re-add is the safest upsert for SQLite (item_code is PK)
            await session.execute(
                delete(RuneStoreLibrary).where(RuneStoreLibrary.item_code == code)
            )
            entry = RuneStoreLibrary(
                item_code=code,
                tier=tier,
                rune_name=rune_name,
                raw_item_bytes=item_bytes,
                seeded_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
            session.add(entry)
            count += 1
            log.info("store_service: seeded rune %s (%s)", code, rune_name)

    await session.commit()
    return count


async def get_catalog(session: AsyncSession) -> dict:
    """
    Return the rune catalog grouped by tier, indicating which runes are seeded.
    """
    result = await session.execute(select(RuneStoreLibrary))
    seeded: dict[str, RuneStoreLibrary] = {r.item_code: r for r in result.scalars().all()}

    catalog: dict[str, list[dict]] = {}
    for tier, codes in RUNE_TIERS.items():
        entries = []
        for code in codes:
            rune_name = ITEM_TYPES.get(code, code)
            entries.append({
                "item_code": code,
                "rune_name": rune_name,
                "tier": tier,
                "gold_cost": TIER_GOLD_COST[tier],
                "seeded": code in seeded,
            })
        catalog[tier] = entries

    return catalog


async def get_tab5_runes(session: AsyncSession, mode: str) -> list[dict]:
    """
    Return all rune items currently on stash tab 5 (portal tab) of the latest snapshot.
    """
    hardcore = mode == "hc"
    filename = _stash_filename(hardcore)

    snap = await _get_latest_snap(session)
    if snap is None:
        return []

    from backend.config import get_settings
    cfg = get_settings()
    stash_path = cfg.data_dir / snap.snapshot_path / filename

    if not stash_path.exists():
        return []

    try:
        stash = parse_stash(stash_path, hardcore=hardcore)
    except Exception as exc:
        log.warning("store_service: failed to parse stash for tab5 runes: %s", exc)
        return []

    if len(stash.pages) <= PORTAL_TAB_INDEX:
        return []

    runes = []
    for i, item in enumerate(stash.pages[PORTAL_TAB_INDEX].items):
        code = item.item_type.strip()
        if code not in _CODE_TO_TIER:
            continue
        runes.append({
            "item_index": i,
            "item_code": code,
            "rune_name": ITEM_TYPES.get(code, code),
            "tier": _CODE_TO_TIER[code],
        })
    return runes


async def buy_rune(session: AsyncSession, item_code: str, mode: str) -> dict:
    """
    Purchase a rune from the store by deducting vault gold and inserting the rune
    into tab 5 of the latest local snapshot.

    Raises ValueError for user-visible errors, RuntimeError for safety failures.
    """
    from backend.config import get_settings
    from backend.services.backup_manager import create_local_snapshot

    # 1. Validate rune code
    if item_code not in _CODE_TO_TIER:
        raise ValueError(f"'{item_code}' is not a valid rune code")

    # 2. Fetch library entry
    lib_result = await session.execute(
        select(RuneStoreLibrary).where(RuneStoreLibrary.item_code == item_code)
    )
    lib_entry = lib_result.scalar_one_or_none()
    if lib_entry is None:
        raise ValueError(f"Rune '{item_code}' is not in the store library yet — seed the library first")

    # 3. Determine tier and gold cost (always SC for gold vault)
    tier = _CODE_TO_TIER[item_code]
    gold_cost = TIER_GOLD_COST[tier]

    # 4. Check vault gold (store always uses SC vault, hardcore=False)
    vault_result = await session.execute(
        select(GoldVault).where(GoldVault.hardcore == False)  # noqa: E712
    )
    vault = vault_result.scalar_one_or_none()
    vault_amount = vault.amount if vault else 0
    if vault_amount < gold_cost:
        raise ValueError(
            f"Insufficient vault gold. Need {gold_cost:,} but vault has {vault_amount:,}."
        )

    # 5. Find latest snapshot
    snap = await _get_latest_snap(session)
    if snap is None:
        raise ValueError("No snapshot available. Check In from a device first.")

    cfg = get_settings()
    hardcore = mode == "hc"
    filename = _stash_filename(hardcore)
    snap_dir = cfg.data_dir / snap.snapshot_path
    stash_path = snap_dir / filename

    if not stash_path.exists():
        raise ValueError(f"{filename} not found in snapshot. Check In from a device first.")

    # 6. Backup before modifying
    await create_local_snapshot(session, snap, "pre_store_buy")

    # 7. Parse stash
    stash = parse_stash(stash_path, hardcore=hardcore)

    # 8. Validate tab exists
    if len(stash.pages) <= PORTAL_TAB_INDEX:
        raise RuntimeError(f"{filename} has fewer than {PORTAL_TAB_INDEX + 1} pages")

    # 9. Validate page items
    if not validate_page_items(stash.pages[PORTAL_TAB_INDEX]):
        raise RuntimeError("Tab 5 failed item validation — aborting to protect stash")

    # 10. Record original count for round-trip check
    original_count = len(stash.pages[PORTAL_TAB_INDEX].items)

    # 11. Insert rune into tab 5
    stash.pages[PORTAL_TAB_INDEX] = insert_item_into_page(
        stash.pages[PORTAL_TAB_INDEX],
        bytes(lib_entry.raw_item_bytes),
    )

    # 12. Serialize
    new_bytes = serialize_stash(stash)

    # 13. Round-trip validate
    with tempfile.TemporaryDirectory() as tmp:
        verify_path = Path(tmp) / filename
        verify_path.write_bytes(new_bytes)
        verify_stash = parse_stash(verify_path, hardcore=hardcore)

    new_count = len(verify_stash.pages[PORTAL_TAB_INDEX].items)
    if new_count != original_count + 1:
        raise RuntimeError(
            f"Round-trip validation failed: expected {original_count + 1} items on tab 5, "
            f"got {new_count} — aborting write"
        )

    # 14. Write to disk
    stash_path.write_bytes(new_bytes)

    # 15. Deduct gold
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if vault is None:
        # Should not happen given the check above, but be defensive
        raise RuntimeError("Vault row disappeared between check and deduct")
    vault.amount -= gold_cost
    vault.last_updated = now

    # 16. Commit
    await session.commit()

    log.info(
        "store_service: bought %s (%s) for %d gold — vault now %d",
        lib_entry.rune_name, item_code, gold_cost, vault.amount,
    )

    # 17. Return
    return {"vault_gold": vault.amount, "rune_name": lib_entry.rune_name}


async def trade_rune(
    session: AsyncSession,
    tab5_item_index: int,
    target_code: str,
    mode: str,
) -> dict:
    """
    Trade a rune on tab 5 for another rune of the same tier from the library.
    Removes the source rune and inserts the target rune.

    Raises ValueError for user-visible errors, RuntimeError for safety failures.
    """
    from backend.config import get_settings
    from backend.services.backup_manager import create_local_snapshot

    # 1. Validate target code
    if target_code not in _CODE_TO_TIER:
        raise ValueError(f"'{target_code}' is not a valid rune code")

    # 2. Fetch target library entry
    lib_result = await session.execute(
        select(RuneStoreLibrary).where(RuneStoreLibrary.item_code == target_code)
    )
    target_lib = lib_result.scalar_one_or_none()
    if target_lib is None:
        raise ValueError(f"Rune '{target_code}' is not in the store library yet — seed the library first")

    # 3. Find latest snapshot, parse stash
    snap = await _get_latest_snap(session)
    if snap is None:
        raise ValueError("No snapshot available. Check In from a device first.")

    cfg = get_settings()
    hardcore = mode == "hc"
    filename = _stash_filename(hardcore)
    snap_dir = cfg.data_dir / snap.snapshot_path
    stash_path = snap_dir / filename

    if not stash_path.exists():
        raise ValueError(f"{filename} not found in snapshot. Check In from a device first.")

    stash = parse_stash(stash_path, hardcore=hardcore)

    # 4. Validate tab index
    if len(stash.pages) <= PORTAL_TAB_INDEX:
        raise RuntimeError(f"{filename} has fewer than {PORTAL_TAB_INDEX + 1} pages")

    tab5 = stash.pages[PORTAL_TAB_INDEX]
    if tab5_item_index < 0 or tab5_item_index >= len(tab5.items):
        raise ValueError(
            f"Item index {tab5_item_index} is out of range (tab 5 has {len(tab5.items)} items)"
        )

    # 5. Get the source item
    source_item = tab5.items[tab5_item_index]
    source_code = source_item.item_type.strip()

    # 6. Validate source is a rune
    if source_code not in _CODE_TO_TIER:
        raise ValueError(f"Item at index {tab5_item_index} is not a rune (type='{source_code}')")

    # 7. Validate not trading for the same rune
    if source_code == target_code:
        raise ValueError(f"Cannot trade a rune for the same rune ('{source_code}')")

    # 8. Validate same tier
    source_tier = _CODE_TO_TIER[source_code]
    target_tier = _CODE_TO_TIER[target_code]
    if source_tier != target_tier:
        raise ValueError(
            f"Tier mismatch: '{source_code}' is {source_tier} tier, "
            f"'{target_code}' is {target_tier} tier. Trades must be within the same tier."
        )

    source_name = ITEM_TYPES.get(source_code, source_code)
    original_count = len(tab5.items)

    # 9. Backup before modifying
    await create_local_snapshot(session, snap, "pre_store_trade")

    # 10. Re-parse stash (fresh read after backup to get clean state)
    stash = parse_stash(stash_path, hardcore=hardcore)

    # 11. Validate page items
    if not validate_page_items(stash.pages[PORTAL_TAB_INDEX]):
        raise RuntimeError("Tab 5 failed item validation — aborting to protect stash")

    # 12. Remove source rune, insert target rune
    modified = remove_items_from_page(stash.pages[PORTAL_TAB_INDEX], [tab5_item_index])
    modified = insert_item_into_page(modified, bytes(target_lib.raw_item_bytes))
    stash.pages[PORTAL_TAB_INDEX] = modified

    # 13. Serialize
    new_bytes = serialize_stash(stash)

    # 14. Round-trip validate (count should be unchanged: removed 1, added 1)
    with tempfile.TemporaryDirectory() as tmp:
        verify_path = Path(tmp) / filename
        verify_path.write_bytes(new_bytes)
        verify_stash = parse_stash(verify_path, hardcore=hardcore)

    new_count = len(verify_stash.pages[PORTAL_TAB_INDEX].items)
    if new_count != original_count:
        raise RuntimeError(
            f"Round-trip validation failed: expected {original_count} items on tab 5, "
            f"got {new_count} — aborting write"
        )

    # 15. Write to disk
    stash_path.write_bytes(new_bytes)

    # 16. Commit (no gold change for trade)
    await session.commit()

    log.info(
        "store_service: traded %s (%s) → %s (%s)",
        source_name, source_code, target_lib.rune_name, target_code,
    )

    # 17. Return
    return {"source_rune": source_name, "target_rune": target_lib.rune_name}


async def delete_library_entry(session: AsyncSession, item_code: str) -> bool:
    """Delete a rune from the library. Returns False if not found."""
    result = await session.execute(
        select(RuneStoreLibrary).where(RuneStoreLibrary.item_code == item_code)
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        return False
    await session.execute(
        delete(RuneStoreLibrary).where(RuneStoreLibrary.item_code == item_code)
    )
    await session.commit()
    log.info("store_service: deleted library entry for %s", item_code)
    return True
