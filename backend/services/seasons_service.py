from __future__ import annotations

"""
Seasons service: milestone detection, season start (wipe), and reward claim.
"""
import asyncio
import logging
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, update

from sqlalchemy import func
from backend.models import (
    Season, SeasonMilestone, SeasonAchievement,
    Character, GrailEntry, GrailCatalog, VaultItem, GoldVault, SeasonStats,
)
from sqlalchemy import update as sa_update
from backend.services.d2s_parser import parse_d2s, D2SParseError

log = logging.getLogger(__name__)


# ─── Milestone check (called after every sync) ────────────────────────────────

async def check_season_milestones(session: AsyncSession, downloaded: list[dict]) -> None:
    """
    Called after every sync (alongside grail hook). Detects newly crossed milestones.
    `downloaded` is the list of file dicts with 'filename' and 'local_part' keys.
    """
    active_season = await _get_active_season(session)
    if not active_season:
        return

    milestones = await _get_milestones(session, active_season.id)
    if not milestones:
        return

    for item in downloaded:
        if not item["filename"].endswith(".d2s"):
            continue
        try:
            char = parse_d2s(item["local_part"])
        except D2SParseError as e:
            log.warning("Seasons: could not parse %s: %s", item["filename"], e)
            continue

        # Skip HC characters — seasons are SC only
        if char.hardcore:
            continue

        await _check_char_milestones(session, active_season, milestones, char)

    # Also check season-wide milestones (gold vault etc.) on every check-in
    await check_gold_milestones(session, active_season, milestones)


async def _get_active_season(session: AsyncSession) -> Season | None:
    result = await session.execute(
        select(Season).where(Season.status == "active")
    )
    return result.scalar_one_or_none()


async def _get_milestones(session: AsyncSession, season_id: int) -> list[SeasonMilestone]:
    result = await session.execute(
        select(SeasonMilestone)
        .where(SeasonMilestone.season_id == season_id)
        .order_by(SeasonMilestone.sort_order)
    )
    return list(result.scalars().all())


async def _check_char_milestones(
    session: AsyncSession,
    season: Season,
    milestones: list[SeasonMilestone],
    char,
) -> None:
    """Check character-based milestones for one SC character and record new achievements."""
    now = datetime.now(timezone.utc)
    for ms in milestones:
        if ms.milestone_type == "gold_vault":
            continue  # season-wide, handled separately

        if not _milestone_met(ms, char=char, season_started_at=season.started_at, now=now):
            continue

        # Account-scoped: one achievement per season using the sentinel key.
        # Character-scoped: one achievement per character.
        scope = ms.scope if isinstance(ms.scope, str) else "character"
        if scope == "account":
            ach_char_name = _SEASON_SENTINEL
            ach_char_class = ""
            ach_char_level = 0
        else:
            ach_char_name = char.name
            ach_char_class = char.class_name
            ach_char_level = char.level

        existing = await session.execute(
            select(SeasonAchievement).where(
                SeasonAchievement.milestone_id == ms.id,
                SeasonAchievement.character_name == ach_char_name,
            )
        )
        if existing.scalar_one_or_none() is not None:
            continue

        achievement = SeasonAchievement(
            season_id=season.id,
            milestone_id=ms.id,
            character_name=ach_char_name,
            character_class=ach_char_class,
            character_level=ach_char_level,
            achieved_at=now,
        )
        session.add(achievement)
        log.info(
            "Season %d: milestone '%s' achieved (scope=%s char=%s lvl=%d)",
            season.id, ms.name, scope, char.class_name, char.level,
        )

    await session.commit()


async def check_gold_milestones(
    session: AsyncSession,
    active_season: Season | None = None,
    milestones: list[SeasonMilestone] | None = None,
) -> None:
    """
    Check gold_vault milestones against the current SC vault balance.
    Called after every deposit and at the end of every check-in.

    Parameters are optional so callers that already have them can avoid re-fetching.
    """
    if active_season is None:
        active_season = await _get_active_season(session)
        if not active_season:
            return

    if milestones is None:
        milestones = await _get_milestones(session, active_season.id)

    gold_milestones = [m for m in milestones if m.milestone_type == "gold_vault"]
    if not gold_milestones:
        return

    vault_result = await session.execute(
        select(GoldVault).where(GoldVault.hardcore == False)
    )
    vault = vault_result.scalar_one_or_none()
    vault_gold_sc = vault.amount if vault else 0

    now = datetime.now(timezone.utc)
    for ms in gold_milestones:
        if not _milestone_met(ms, season_started_at=active_season.started_at, now=now, vault_gold_sc=vault_gold_sc):
            continue

        existing = await session.execute(
            select(SeasonAchievement).where(
                SeasonAchievement.milestone_id == ms.id,
                SeasonAchievement.character_name == _SEASON_SENTINEL,
            )
        )
        if existing.scalar_one_or_none() is not None:
            continue

        achievement = SeasonAchievement(
            season_id=active_season.id,
            milestone_id=ms.id,
            character_name=_SEASON_SENTINEL,
            character_class="",
            character_level=0,
            achieved_at=now,
        )
        session.add(achievement)
        log.info(
            "Season %d: gold vault milestone '%s' achieved (vault=%d, target=%d)",
            active_season.id, ms.name, vault_gold_sc, ms.numeric_target or 0,
        )

    await session.commit()


# Sentinel used for season-wide achievements that aren't tied to a specific character
_SEASON_SENTINEL = "(Season)"


def _milestone_met(
    ms: SeasonMilestone,
    char=None,
    season_started_at: datetime | None = None,
    now: datetime | None = None,
    vault_gold_sc: int = 0,
) -> bool:
    """
    Returns True if the milestone condition is met AND the time window (if any)
    has not closed.

    char:          required for character-based milestone types
    vault_gold_sc: required for gold_vault type
    """
    # Time window guard — applies to all types
    if ms.time_limit_hours is not None and season_started_at is not None:
        _now = now or datetime.now(timezone.utc)
        started = season_started_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        deadline = started + timedelta(hours=ms.time_limit_hours)
        if _now > deadline:
            return False

    if ms.milestone_type == "level":
        return char is not None and ms.level_target is not None and char.level >= ms.level_target
    elif ms.milestone_type.startswith("cleared_act"):
        return char is not None and char.acts_cleared.get(ms.milestone_type, False)
    elif ms.milestone_type == "gold_vault":
        return ms.numeric_target is not None and vault_gold_sc >= ms.numeric_target
    return False


# ─── Season stats snapshot ────────────────────────────────────────────────────

async def compute_and_save_season_stats(session: AsyncSession, season: Season) -> SeasonStats:
    """
    Compute current-season metrics from DB and upsert into SeasonStats.
    Call this before wiping data (start_season) or when ending a season.
    """
    # Characters
    chars_result = await session.execute(select(Character).where(Character.season_id == None))
    all_chars = list(chars_result.scalars().all())
    sc_chars = [c for c in all_chars if not c.hardcore]
    hc_chars = [c for c in all_chars if c.hardcore]

    def _char_dict(c: Character) -> dict:
        return {
            "name": c.name,
            "class_name": c.class_name,
            "level": c.level,
            "ever_died": c.ever_died,
            "difficulty_active": c.difficulty_active,
        }

    highest_level_sc = max((c.level for c in sc_chars), default=None)
    highest_level_hc = max((c.level for c in hc_chars), default=None)

    # Gold vault
    gold_result = await session.execute(select(GoldVault))
    gold_map = {g.hardcore: g.amount for g in gold_result.scalars().all()}
    gold_sc = gold_map.get(False, 0)
    gold_hc = gold_map.get(True, 0)

    # Grail counts (join GrailEntry → GrailCatalog for quality)
    grail_uniques_sc = (await session.execute(
        select(func.count(GrailEntry.id))
        .join(GrailCatalog, GrailEntry.catalog_id == GrailCatalog.id)
        .where(GrailEntry.hardcore == False, GrailCatalog.quality == "unique")
    )).scalar() or 0

    grail_sets_sc = (await session.execute(
        select(func.count(GrailEntry.id))
        .join(GrailCatalog, GrailEntry.catalog_id == GrailCatalog.id)
        .where(GrailEntry.hardcore == False, GrailCatalog.quality == "set")
    )).scalar() or 0

    grail_uniques_hc = (await session.execute(
        select(func.count(GrailEntry.id))
        .join(GrailCatalog, GrailEntry.catalog_id == GrailCatalog.id)
        .where(GrailEntry.hardcore == True, GrailCatalog.quality == "unique")
    )).scalar() or 0

    grail_sets_hc = (await session.execute(
        select(func.count(GrailEntry.id))
        .join(GrailCatalog, GrailEntry.catalog_id == GrailCatalog.id)
        .where(GrailEntry.hardcore == True, GrailCatalog.quality == "set")
    )).scalar() or 0

    grail_catalog_total = (await session.execute(
        select(func.count(GrailCatalog.id))
    )).scalar() or 0

    # Days played
    days_played: int | None = None
    if season.started_at:
        started = season.started_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        days_played = (datetime.now(timezone.utc) - started).days

    # Upsert SeasonStats
    existing = (await session.execute(
        select(SeasonStats).where(SeasonStats.season_id == season.id)
    )).scalar_one_or_none()

    if existing is None:
        existing = SeasonStats(season_id=season.id)
        session.add(existing)

    existing.highest_level_sc = highest_level_sc
    existing.highest_level_hc = highest_level_hc
    existing.characters_sc = [_char_dict(c) for c in sc_chars]
    existing.characters_hc = [_char_dict(c) for c in hc_chars]
    existing.total_gold_vault_sc = gold_sc
    existing.total_gold_vault_hc = gold_hc
    existing.grail_uniques_sc = grail_uniques_sc
    existing.grail_sets_sc = grail_sets_sc
    existing.grail_uniques_hc = grail_uniques_hc
    existing.grail_sets_hc = grail_sets_hc
    existing.grail_catalog_total = grail_catalog_total
    existing.days_played = days_played
    existing.snapshot_at = datetime.now(timezone.utc)

    await session.commit()
    return existing


# ─── Start season (wipe saves + DB reset) ─────────────────────────────────────

async def start_season(
    session: AsyncSession,
    season_id: int,
) -> Season:
    """
    1. Verify no other active season
    2. Copy latest local snapshot to a season_archive dir
    3. Snapshot season metrics
    4. Clear DB tables (characters, grail_entries, vault_items, gold_vaults)
    5. Set season.status = "active"

    No SSH required — archive is built entirely from local snapshot data.
    """
    from backend.config import get_settings
    from backend.models import BackupSnapshot

    season = await session.get(Season, season_id)
    if season is None:
        raise ValueError(f"Season {season_id} not found")
    if season.status == "active":
        raise ValueError("Season is already active")
    if season.status == "completed":
        raise ValueError("Cannot start a completed season")

    other = await session.execute(
        select(Season).where(Season.status == "active", Season.id != season_id)
    )
    if other.scalar_one_or_none():
        raise ValueError("Another season is already active")

    cfg = get_settings()

    # Find latest manual/game_close snapshot to archive
    snap_result = await session.execute(
        select(BackupSnapshot)
        .where(BackupSnapshot.label.in_(["manual", "game_close"]))
        .order_by(BackupSnapshot.created_at.desc())
        .limit(1)
    )
    latest_snap = snap_result.scalar_one_or_none()

    archive_snap: BackupSnapshot | None = None

    if latest_snap:
        src_dir = cfg.data_dir / latest_snap.snapshot_path
        if src_dir.exists():
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            archive_dir = cfg.backups_dir / latest_snap.source_machine / f"{timestamp}_season_archive"
            shutil.copytree(str(src_dir), str(archive_dir))

            archive_snap = BackupSnapshot(
                source_machine=latest_snap.source_machine,
                snapshot_path=str(archive_dir.relative_to(cfg.data_dir)),
                file_count=latest_snap.file_count,
                characters=latest_snap.characters,
                label="season_archive",
            )
            session.add(archive_snap)
            await session.flush()
            log.info("Season start: archived snapshot from %s to %s", src_dir, archive_dir)
        else:
            log.warning("Season start: latest snapshot dir missing (%s), skipping archive", src_dir)
    else:
        log.info("Season start: no manual/game_close snapshot found, season archive will be empty")

    # Remove any stale character archives for this season (can occur if a previous
    # start attempt failed mid-transaction and left orphaned rows).
    stale_result = await session.execute(
        select(Character).where(Character.season_id == season_id)
    )
    stale = stale_result.scalars().all()
    if stale:
        log.warning(
            "Season %d: found %d stale archived characters from a failed previous start — removing before re-archiving",
            season_id, len(stale),
        )
        await session.execute(delete(Character).where(Character.season_id == season_id))

    # Archive current characters to this season (soft delete — preserves history)
    await session.execute(
        sa_update(Character)
        .where(Character.season_id == None)
        .values(season_id=season_id)
    )

    # Reset DB tables
    await session.execute(delete(GrailEntry))
    await session.execute(delete(VaultItem))
    await session.execute(update(GoldVault).values(amount=0))

    # Activate season
    season.status = "active"
    season.started_at = datetime.now(timezone.utc)
    season.archive_snapshot_id = archive_snap.id if archive_snap else None

    # Initialize season stats at zero — correctly reflects fresh start state
    await compute_and_save_season_stats(session, season)

    await session.commit()

    return season


# ─── Claim reward ─────────────────────────────────────────────────────────────

async def claim_reward(
    session: AsyncSession,
    achievement_id: int,
) -> SeasonAchievement:
    """
    Insert the milestone reward item into tab 5 of the Mothership (latest local snapshot).
    No SSH required — the vault is the source of truth. Sync to Device will push it to
    whatever machine the player is on.

    Safety protocol (mirrors grail_service.deposit_tab5):
      0. Backup existing snapshot locally (no SSH) before ANY modification
      1. Parse stash
      2. Validate tab 5 before modification
      3. Insert reward item into tab 5
      4. Serialize and round-trip validate (re-parse, confirm item count)
      5. Write to disk
      6. Mark achievement claimed and commit DB
    """
    import tempfile
    from backend.config import get_settings
    from backend.services.item_parsing import parse_stash, serialize_stash
    from backend.services.item_parsing.stash_format import insert_item_into_page, validate_page_items
    from backend.models import BackupSnapshot
    from backend.services.backup_manager import create_local_snapshot

    achievement = await session.get(SeasonAchievement, achievement_id)
    if achievement is None:
        raise ValueError(f"Achievement {achievement_id} not found")
    if achievement.claimed_at is not None:
        raise ValueError("Reward already claimed")

    milestone = await session.get(SeasonMilestone, achievement.milestone_id)
    if milestone is None or milestone.reward_item_bytes is None:
        raise ValueError("No reward item configured for this milestone")

    # Find the latest Mothership snapshot
    snap_result = await session.execute(
        select(BackupSnapshot)
        .where(BackupSnapshot.label.in_(["manual", "game_close"]))
        .order_by(BackupSnapshot.created_at.desc())
        .limit(1)
    )
    snap = snap_result.scalar_one_or_none()
    if snap is None:
        raise ValueError("No snapshot available. Check In from a device first.")

    cfg = get_settings()
    snap_dir = cfg.data_dir / snap.snapshot_path
    stash_path = snap_dir / "ModernSharedStashSoftCoreV2.d2i"

    if not stash_path.exists():
        raise ValueError("Stash file not found in snapshot. Check In from a device first.")

    # SAFETY: Backup snapshot before ANY modification (mirrors grail deposit protocol)
    log.info("BACKUP: Creating pre-milestone-claim backup of snapshot %s", snap.snapshot_path)
    try:
        await create_local_snapshot(session, snap, label="pre_season_reward")
        log.info("BACKUP: Pre-milestone-claim backup created successfully")
    except Exception as e:
        log.error("BACKUP FAILED: Cannot proceed with milestone claim: %s", e)
        raise RuntimeError(f"Pre-claim backup failed: {e}") from e

    stash = parse_stash(stash_path, hardcore=False)
    if len(stash.pages) <= 4:
        raise ValueError("Stash has fewer than 5 tabs; cannot write to tab 5")

    # Validate tab 5 before modification
    if not validate_page_items(stash.pages[4]):
        raise RuntimeError("Tab 5 failed item validation — aborting to protect stash")

    original_item_count = len(stash.pages[4].items)
    stash.pages[4] = insert_item_into_page(stash.pages[4], bytes(milestone.reward_item_bytes))
    new_bytes = serialize_stash(stash)

    # Round-trip validate: re-parse serialized bytes and confirm item count
    with tempfile.TemporaryDirectory() as tmp:
        rt_path = Path(tmp) / "rt_stash.d2i"
        rt_path.write_bytes(new_bytes)
        rt_stash = parse_stash(rt_path, hardcore=False)
        rt_page = rt_stash.pages[4]
        expected_count = original_item_count + 1
        if len(rt_page.items) != expected_count:
            raise RuntimeError(
                f"Round-trip validation failed: expected {expected_count} items in tab 5, "
                f"got {len(rt_page.items)} — aborting write to protect stash"
            )

    # All validation passed — write to disk, then commit DB
    stash_path.write_bytes(new_bytes)
    log.info("Claim reward: wrote modified stash to %s", stash_path)

    achievement.claimed_at = datetime.now(timezone.utc)
    await session.commit()
    return achievement
