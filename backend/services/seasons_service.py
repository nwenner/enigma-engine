from __future__ import annotations

"""
Seasons service: milestone detection, season start (wipe), and reward claim.
"""
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
    """Check all milestones for one character and record new achievements."""
    now = datetime.now(timezone.utc)
    for ms in milestones:
        if not _milestone_met(ms, char, season.started_at, now):
            continue

        # Check if already recorded
        existing = await session.execute(
            select(SeasonAchievement).where(
                SeasonAchievement.milestone_id == ms.id,
                SeasonAchievement.character_name == char.name,
            )
        )
        if existing.scalar_one_or_none() is not None:
            continue

        achievement = SeasonAchievement(
            season_id=season.id,
            milestone_id=ms.id,
            character_name=char.name,
            character_class=char.class_name,
            character_level=char.level,
            achieved_at=now,
        )
        session.add(achievement)
        log.info(
            "Season %d: %s achieved milestone '%s' (char=%s lvl=%d)",
            season.id, char.name, ms.name, char.class_name, char.level,
        )

    await session.commit()


def _milestone_met(
    ms: SeasonMilestone,
    char,
    season_started_at: datetime | None = None,
    now: datetime | None = None,
) -> bool:
    """
    Returns True if the character meets the milestone condition AND the time
    window (if any) has not yet closed.
    """
    # Check time window first — if expired, no new achievements are possible
    if ms.time_limit_hours is not None and season_started_at is not None:
        _now = now or datetime.now(timezone.utc)
        # Make started_at timezone-aware if stored naive
        started = season_started_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        deadline = started + timedelta(hours=ms.time_limit_hours)
        if _now > deadline:
            return False

    if ms.milestone_type == "level":
        return ms.level_target is not None and char.level >= ms.level_target
    elif ms.milestone_type == "cleared_normal":
        return char.cleared_normal
    elif ms.milestone_type == "cleared_nightmare":
        return char.cleared_nightmare
    elif ms.milestone_type == "cleared_hell":
        return char.cleared_hell
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
    machine: str,
    conn: dict,
    save_dir: str,
    is_windows: bool = True,
) -> SeasonAchievement:
    """
    Write the milestone reward item to tab 5 of the SC stash on the target machine.
    """
    from backend.services import ssh_client as ssh_mod
    from backend.services.backup_manager import create_snapshot
    from backend.services.item_parsing import parse_stash, serialize_stash
    from backend.services.item_parsing.stash_format import insert_item_into_page

    achievement = await session.get(SeasonAchievement, achievement_id)
    if achievement is None:
        raise ValueError(f"Achievement {achievement_id} not found")
    if achievement.claimed_at is not None:
        raise ValueError("Reward already claimed")

    milestone = await session.get(SeasonMilestone, achievement.milestone_id)
    if milestone is None or milestone.reward_item_bytes is None:
        raise ValueError("No reward item configured for this milestone")

    # Check D2R not running
    def _check_running():
        with ssh_mod.get_sftp(**conn) as (ssh, _sftp):
            if ssh_mod.check_d2r_running(ssh, is_windows):
                raise RuntimeError(f"D2R.exe is running on {machine.upper()}. Close the game first.")

    await asyncio.to_thread(_check_running)

    # Create safety snapshot before modifying
    await create_snapshot(
        session=session,
        machine=machine,
        conn_kwargs=conn,
        save_dir=save_dir,
        label="pre_season_reward",
    )

    STASH_FILENAME = "ModernSharedStashSoftCoreV2.d2i"

    # Download stash, insert item, re-upload
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        local_stash = Path(tmpdir) / STASH_FILENAME
        remote_stash = ssh_mod.normalize_path(f"{save_dir}/{STASH_FILENAME}")

        def _download():
            with ssh_mod.get_sftp(**conn) as (_ssh, sftp):
                sftp.get(remote_stash, str(local_stash))

        await asyncio.to_thread(_download)

        stash = parse_stash(local_stash, hardcore=False)
        if len(stash.pages) <= 4:
            raise RuntimeError("Stash has fewer than 5 tabs; cannot write to tab 5")

        insert_item_into_page(stash.pages[4], milestone.reward_item_bytes)
        out_bytes = serialize_stash(stash)
        local_stash.write_bytes(out_bytes)

        def _upload():
            with ssh_mod.get_sftp(**conn) as (_ssh, sftp):
                sftp.put(str(local_stash), remote_stash)

        await asyncio.to_thread(_upload)

    achievement.claimed_at = datetime.now(timezone.utc)
    await session.commit()
    return achievement
