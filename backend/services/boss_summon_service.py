from __future__ import annotations

"""
Boss Summon Portals service.

Tracks whether the required summon items have been farmed at least once per season,
then provides infinite repeatable retrieval of those items into portal tab 5.
"""
import json
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.models import BossSummonProgress, Season, SeasonReward, BackupSnapshot
from backend.services.grail_service import (
    _latest_snapshot,
    _snapshot_dir,
    _create_local_backup_snapshot,
    STASH_FILES,
    PORTAL_TAB_INDEX,
)
from backend.services.item_parsing import parse_stash, serialize_stash
from backend.services.item_parsing.stash_format import insert_item_into_page, validate_page_items

log = logging.getLogger(__name__)


def _parse_unique_id_from_bytes(raw_bytes: bytes) -> int | None:
    """Parse unique_id from raw item bytes. Returns None if not a unique item or parse fails."""
    from backend.services.item_parsing.item_flags import read_item_flags
    from backend.services.item_parsing.item_fields import read_item_fields
    try:
        flags = read_item_flags(raw_bytes, 0)
        fields = read_item_fields(raw_bytes, flags, 0)
        return fields.unique_id if fields.quality == 7 else None
    except Exception:
        return None


# ─── Static boss summon set definitions ───────────────────────────────────────

BOSS_SUMMON_SETS: list[dict[str, Any]] = [
    {
        "id": "dclone",
        "name": "Diablo Clone",
        "description": "Sell a Stone of Jordan to unleash Diablo Clone.",
        "required_item_codes": ["rin"],  # SoJ — base ring type; acceptable for personal use
        "sort_order": 0,
    },
    {
        "id": "ubers_phase1",
        "name": "Uber Bosses — Phase 1",
        "description": "Open the Pandemonium portals with a set of three keys.",
        "required_item_codes": ["pk1", "pk2", "pk3"],  # Key of Terror, Key of Hate, Key of Destruction
        "sort_order": 1,
    },
    {
        "id": "ubers_phase2",
        "name": "Uber Tristram",
        "description": "Summon the three Uber bosses with the organs from Phase 1.",
        "required_item_codes": ["bey", "mbr", "dhn"],  # Baal's Eye, Mephisto's Brain, Diablo's Horn
        "sort_order": 2,
    },
    {
        "id": "ancients",
        "name": "Uber Ancients",
        "description": "Assemble one key per act to challenge the Uber Ancients.",
        "required_item_codes": ["xa1", "xa2", "xa3", "xa4", "xa5"],  # Act 1–5 Uber Ancient keys
        "sort_order": 3,
    },
]

_SETS_BY_ID: dict[str, dict] = {s["id"]: s for s in BOSS_SUMMON_SETS}

# Human-readable labels for item codes shown in the UI.
# Populated from the rewards library at runtime for unique items (see list_summon_status).
# Fallback labels for codes that are unlikely to be in the rewards library.
ITEM_CODE_LABELS: dict[str, str] = {
    "rin": "Stone of Jordan",   # overridden by rewards library lookup if present
    "pk1": "Key of Terror",
    "pk2": "Key of Hate",
    "pk3": "Key of Destruction",
    "bey": "Baal's Eye",
    "mbr": "Mephisto's Brain",
    "dhn": "Diablo's Horn",
    "xa1": "Ancient Key (Act 1)",
    "xa2": "Ancient Key (Act 2)",
    "xa3": "Ancient Key (Act 3)",
    "xa4": "Ancient Key (Act 4)",
    "xa5": "Ancient Key (Act 5)",
}


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _get_active_season(session: AsyncSession) -> Season | None:
    result = await session.execute(select(Season).where(Season.status == "active"))
    return result.scalar_one_or_none()


async def _get_or_create_progress(
    session: AsyncSession,
    set_id: str,
    season_id: int,
) -> BossSummonProgress:
    result = await session.execute(
        select(BossSummonProgress).where(
            BossSummonProgress.set_id == set_id,
            BossSummonProgress.season_id == season_id,
        )
    )
    progress = result.scalar_one_or_none()
    if progress is None:
        progress = BossSummonProgress(
            set_id=set_id,
            season_id=season_id,
            earned_codes="[]",
        )
        session.add(progress)
        await session.flush()
    return progress


# ─── Check-in hook ────────────────────────────────────────────────────────────

async def check_boss_summon_progress(
    session: AsyncSession,
    snapshot_dir: Path,
) -> None:
    """
    Called from the check-in hook after snapshot is written.
    Scans portal tab 5 of both SC and HC stashes. For each item code found,
    marks it as earned in BossSummonProgress and unlocks the set if all codes are earned.

    This MUST NOT raise — errors are logged as warnings.
    """
    season = await _get_active_season(session)
    if season is None:
        log.debug("BossSummon: no active season, skipping progress check")
        return

    # Build a precise match index from the rewards library.
    # For unique items (quality=7), match by unique_id parsed from reward bytes.
    # For all others, match by item_code. This ensures e.g. SoJ is detected
    # specifically rather than firing on any generic ring.
    all_required_codes: set[str] = {
        code for boss_set in BOSS_SUMMON_SETS for code in boss_set["required_item_codes"]
    }
    reward_result = await session.execute(
        select(SeasonReward)
        .where(SeasonReward.item_code.in_(list(all_required_codes)))
        .order_by(SeasonReward.created_at.desc())
    )
    # For each required code, record its unique_id (if unique) so tab 5 detection is precise
    reward_unique_ids: dict[str, int | None] = {}  # item_code → unique_id (None = match by code only)
    seen_codes: set[str] = set()
    for r in reward_result.scalars().all():
        if r.item_code and r.item_code not in seen_codes:
            uid = _parse_unique_id_from_bytes(r.raw_item_bytes)
            reward_unique_ids[r.item_code] = uid
            seen_codes.add(r.item_code)

    # Collect item codes present in tab 5 across both stash files.
    # For unique items, also track the unique_ids found.
    found_codes: set[str] = set()          # codes matched precisely (library-aware)
    tab5_unique_ids: dict[str, set[int]] = {}  # item_code → set of unique_ids seen in tab 5
    for filename, hardcore in STASH_FILES.items():
        stash_path = snapshot_dir / filename
        if not stash_path.exists():
            continue
        try:
            stash = parse_stash(stash_path, hardcore=hardcore)
        except Exception as e:
            log.warning("BossSummon: failed to parse %s: %s", filename, e)
            continue

        if len(stash.pages) <= PORTAL_TAB_INDEX:
            continue

        portal_page = stash.pages[PORTAL_TAB_INDEX]
        for item in portal_page.items:
            code = item.item_type.rstrip()
            if not code:
                continue
            if code not in all_required_codes:
                continue
            # For unique items: check unique_id matches the reward library entry
            required_uid = reward_unique_ids.get(code)
            if required_uid is not None:
                # We need to match by unique_id
                if item.unique_id == required_uid:
                    found_codes.add(code)
                    log.debug("BossSummon: matched unique item code '%s' (uid=%d) in tab 5", code, required_uid)
                else:
                    log.debug(
                        "BossSummon: skipping '%s' item in tab 5 (uid=%s, need uid=%d)",
                        code, item.unique_id, required_uid,
                    )
            else:
                # Non-unique: item_code match is sufficient
                found_codes.add(code)

    if not found_codes:
        log.debug("BossSummon: no matching required items in portal tab 5")
        return

    log.debug("BossSummon: found matching item codes in tab 5: %s", found_codes)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    any_changes = False

    for boss_set in BOSS_SUMMON_SETS:
        set_id = boss_set["id"]
        required: list[str] = boss_set["required_item_codes"]

        # Only process if any required code was found
        if not any(code in found_codes for code in required):
            continue

        try:
            progress = await _get_or_create_progress(session, set_id, season.id)
            earned: list[str] = json.loads(progress.earned_codes)

            changed = False
            for code in required:
                if code in found_codes and code not in earned:
                    earned.append(code)
                    changed = True
                    log.info("BossSummon: earned code '%s' for set '%s'", code, set_id)

            if changed:
                progress.earned_codes = json.dumps(earned)
                any_changes = True

            # Unlock if all required codes are now earned
            if set(required).issubset(set(earned)) and progress.unlocked_at is None:
                progress.unlocked_at = now
                log.info("BossSummon: set '%s' UNLOCKED for season %d", set_id, season.id)
                any_changes = True

        except Exception as e:
            log.warning("BossSummon: error processing set '%s': %s", set_id, e)

    if any_changes:
        await session.commit()


# ─── List status ──────────────────────────────────────────────────────────────

async def list_summon_status(session: AsyncSession) -> list[dict]:
    """Returns all 4 sets merged with current season progress."""
    season = await _get_active_season(session)

    # Collect all progress rows for the active season
    progress_map: dict[str, BossSummonProgress] = {}
    if season is not None:
        result = await session.execute(
            select(BossSummonProgress).where(BossSummonProgress.season_id == season.id)
        )
        for p in result.scalars().all():
            progress_map[p.set_id] = p

    # Build reward availability index: item_code → most recent SeasonReward
    reward_result = await session.execute(
        select(SeasonReward).order_by(SeasonReward.created_at.desc())
    )
    rewards_by_code: dict[str, SeasonReward] = {}
    for r in reward_result.scalars().all():
        if r.item_code and r.item_code not in rewards_by_code:
            rewards_by_code[r.item_code] = r

    output = []
    for boss_set in BOSS_SUMMON_SETS:
        set_id = boss_set["id"]
        required: list[str] = boss_set["required_item_codes"]
        progress = progress_map.get(set_id)

        earned: list[str] = json.loads(progress.earned_codes) if progress else []
        unlocked = progress.unlocked_at is not None if progress else False
        summon_count = progress.summon_count if progress else 0
        last_summoned_at = (
            progress.last_summoned_at.isoformat() if progress and progress.last_summoned_at else None
        )
        missing_rewards = [code for code in required if code not in rewards_by_code]

        # Build required_items with human-readable labels from ITEM_CODE_LABELS.
        # Parsed item_name from the reward library is intentionally ignored here —
        # unique items parse as e.g. "Ring (unique)" which is less useful than the hardcoded name.
        required_items = [
            {"code": code, "label": ITEM_CODE_LABELS.get(code, code)}
            for code in required
        ]

        output.append({
            "id": set_id,
            "name": boss_set["name"],
            "description": boss_set["description"],
            "required_item_codes": required,
            "required_items": required_items,
            "sort_order": boss_set["sort_order"],
            "earned_codes": earned,
            "unlocked": unlocked,
            "summon_count": summon_count,
            "last_summoned_at": last_summoned_at,
            "missing_rewards": missing_rewards,
        })

    return output


# ─── Earn code manually (fallback) ────────────────────────────────────────────

async def earn_code_manually(session: AsyncSession, set_id: str, code: str) -> dict:
    """Mark a specific code as earned for the active season (fallback if auto-detect misses)."""
    boss_set = _SETS_BY_ID.get(set_id)
    if boss_set is None:
        raise ValueError(f"Unknown set_id: {set_id!r}")

    required: list[str] = boss_set["required_item_codes"]
    if code not in required:
        raise ValueError(f"Code '{code}' is not a required code for set '{set_id}'")

    season = await _get_active_season(session)
    if season is None:
        raise RuntimeError("No active season")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    progress = await _get_or_create_progress(session, set_id, season.id)
    earned: list[str] = json.loads(progress.earned_codes)

    if code not in earned:
        earned.append(code)
        progress.earned_codes = json.dumps(earned)
        log.info("BossSummon: manually earned code '%s' for set '%s'", code, set_id)

    if set(required).issubset(set(earned)) and progress.unlocked_at is None:
        progress.unlocked_at = now
        log.info("BossSummon: set '%s' UNLOCKED via manual earn", set_id)

    await session.commit()
    return {"set_id": set_id, "earned_codes": earned, "unlocked": progress.unlocked_at is not None}


# ─── Reset progress ───────────────────────────────────────────────────────────

async def reset_summon_progress(session: AsyncSession, set_id: str) -> dict:
    """Reset progress for a set in the active season."""
    if set_id not in _SETS_BY_ID:
        raise ValueError(f"Unknown set_id: {set_id!r}")

    season = await _get_active_season(session)
    if season is None:
        raise RuntimeError("No active season")

    result = await session.execute(
        select(BossSummonProgress).where(
            BossSummonProgress.set_id == set_id,
            BossSummonProgress.season_id == season.id,
        )
    )
    progress = result.scalar_one_or_none()
    if progress is not None:
        progress.earned_codes = "[]"
        progress.unlocked_at = None
        progress.summon_count = 0
        progress.last_summoned_at = None
        await session.commit()

    return {"set_id": set_id, "reset": True}


# ─── Summon ───────────────────────────────────────────────────────────────────

async def summon_boss_set(
    session: AsyncSession,
    set_id: str,
    hardcore: bool = False,
) -> dict:
    """
    Insert the required summon items into portal tab 5 of the latest snapshot.

    CRITICAL SAFETY PROTOCOL: creates a pre_boss_summon backup before any modification.
    """
    boss_set = _SETS_BY_ID.get(set_id)
    if boss_set is None:
        raise ValueError(f"Unknown set_id: {set_id!r}")

    season = await _get_active_season(session)
    if season is None:
        raise RuntimeError("No active season — start a season first")

    # Check progress + unlock
    result = await session.execute(
        select(BossSummonProgress).where(
            BossSummonProgress.set_id == set_id,
            BossSummonProgress.season_id == season.id,
        )
    )
    progress = result.scalar_one_or_none()
    if progress is None or progress.unlocked_at is None:
        raise PermissionError(f"Set '{set_id}' is not yet unlocked for this season")

    required: list[str] = boss_set["required_item_codes"]

    # Look up SeasonReward bytes for each required code (most recent)
    items_to_insert: list[tuple[str, bytes]] = []
    for code in required:
        reward_result = await session.execute(
            select(SeasonReward)
            .where(SeasonReward.item_code == code)
            .order_by(SeasonReward.created_at.desc())
            .limit(1)
        )
        reward = reward_result.scalar_one_or_none()
        if reward is None:
            raise RuntimeError(f"No reward in library for item code '{code}'. Upload it first.")
        items_to_insert.append((code, reward.raw_item_bytes))

    # Get latest snapshot
    snap = await _latest_snapshot(session)
    if snap is None:
        raise RuntimeError("No snapshot available. Check In from a device first.")

    snap_dir = _snapshot_dir(snap)

    # Determine stash file
    stash_filename = (
        "ModernSharedStashHardCoreV2.d2i" if hardcore else "ModernSharedStashSoftCoreV2.d2i"
    )
    stash_path = snap_dir / stash_filename

    if not stash_path.exists():
        raise RuntimeError(f"{stash_filename} not found in latest snapshot")

    # BACKUP FIRST
    log.info("BACKUP: Creating pre-boss-summon backup")
    try:
        await _create_local_backup_snapshot(session, snap, "pre_boss_summon")
        log.info("BACKUP: Pre-boss-summon backup created successfully")
    except Exception as e:
        log.error("BACKUP FAILED: Cannot proceed with summon: %s", e)
        raise RuntimeError(f"Pre-summon backup failed: {e}") from e

    # Parse stash
    try:
        stash = parse_stash(stash_path, hardcore=hardcore)
    except Exception as e:
        raise RuntimeError(f"Failed to parse {stash_filename}: {e}") from e

    if len(stash.pages) <= PORTAL_TAB_INDEX:
        raise RuntimeError(f"{stash_filename} has fewer than {PORTAL_TAB_INDEX + 1} pages")

    # Insert each item into portal tab 5
    portal_page = stash.pages[PORTAL_TAB_INDEX]
    for code, item_bytes in items_to_insert:
        portal_page = insert_item_into_page(portal_page, item_bytes)
        log.info("BossSummon: inserted item code '%s' into tab 5", code)

    stash.pages[PORTAL_TAB_INDEX] = portal_page

    # Serialize
    try:
        new_bytes = serialize_stash(stash)
    except Exception as e:
        raise RuntimeError(f"Failed to serialize modified stash: {e}") from e

    # Round-trip validate
    try:
        with tempfile.NamedTemporaryFile(suffix=".d2i", delete=False) as tf:
            tf.write(new_bytes)
            rt_path = Path(tf.name)
        rt_stash = parse_stash(rt_path, hardcore=hardcore)
        rt_path.unlink(missing_ok=True)
        rt_page = rt_stash.pages[PORTAL_TAB_INDEX]
        expected_count = len(stash.pages[PORTAL_TAB_INDEX].items)
        if len(rt_page.items) != expected_count:
            raise ValueError(
                f"round-trip item count mismatch: expected {expected_count}, got {len(rt_page.items)}"
            )
    except Exception as e:
        raise RuntimeError(f"Round-trip validation failed: {e}") from e

    # Write to disk
    stash_path.write_bytes(new_bytes)
    log.info("BossSummon: wrote modified %s to snapshot", stash_filename)

    # Update progress
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    progress.summon_count += 1
    progress.last_summoned_at = now
    await session.commit()

    return {
        "success": True,
        "set_id": set_id,
        "items_inserted": len(items_to_insert),
        "summon_count": progress.summon_count,
    }
