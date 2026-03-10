from __future__ import annotations

"""
Seasons router.

Endpoints:
  GET    /api/seasons                          — list all seasons
  POST   /api/seasons                          — create a new season
  GET    /api/seasons/active                   — active season detail
  GET    /api/seasons/{id}                     — single season detail
  DELETE /api/seasons/{id}                     — delete season record
  POST   /api/seasons/{id}/start               — start season (wipe + activate)
  POST   /api/seasons/{id}/end                 — mark season completed
  GET    /api/seasons/{id}/achievements        — achievements for a season
  POST   /api/seasons/milestones/validate-item          — parse hex bytes → item preview
  POST   /api/seasons/achievements/{id}/claim           — claim reward item
  POST   /api/seasons/{id}/milestones                   — add milestone to active/setup season
  PATCH  /api/seasons/{id}/milestones/{ms_id}           — edit milestone fields (partial update)
  DELETE /api/seasons/{id}/milestones/{ms_id}           — delete milestone + cascade achievements
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_session
from backend.models import Season, SeasonMilestone, SeasonAchievement, SeasonStats, Character, GoldVault, GrailEntry, GrailCatalog
from backend.routers.settings import _get_conn_kwargs, _get_setting
from backend.services import ssh_client as ssh_mod

log = logging.getLogger(__name__)
router = APIRouter(tags=["seasons"])


# ─── Pydantic schemas ──────────────────────────────────────────────────────────

class MilestoneIn(BaseModel):
    name: str
    milestone_type: str          # "level" | "cleared_normal" | "cleared_nightmare"
    level_target: Optional[int] = None
    sort_order: int = 0
    reward_item_hex: Optional[str] = None   # space-separated or continuous hex bytes
    reward_item_name: Optional[str] = None  # display name override
    reward_item_code: Optional[str] = None  # 4-char type code override
    time_limit_hours: Optional[int] = None  # null = no time limit; e.g. 48 = 2 days


class SeasonCreate(BaseModel):
    name: str
    notes: Optional[str] = None
    duration_weeks: Optional[int] = None    # null = no end date; 1–26
    milestones: list[MilestoneIn] = []


class MilestoneOut(BaseModel):
    id: int
    season_id: int
    name: str
    milestone_type: str
    level_target: Optional[int]
    reward_item_name: Optional[str]
    reward_item_code: Optional[str]
    has_reward: bool
    time_limit_hours: Optional[int]
    is_expired: bool    # True when time window has closed and no new achievements can be earned
    sort_order: int


class AchievementOut(BaseModel):
    id: int
    season_id: int
    milestone_id: int
    character_name: str
    character_class: str
    character_level: int
    achieved_at: str
    claimed_at: Optional[str]


class SeasonOut(BaseModel):
    id: int
    name: str
    status: str
    started_at: Optional[str]
    ended_at: Optional[str]
    scheduled_end_at: Optional[str]  # started_at + duration_weeks if both set
    notes: Optional[str]
    duration_weeks: Optional[int]
    created_at: str
    milestones: list[MilestoneOut]
    achievements: list[AchievementOut]


class SeasonListItem(BaseModel):
    id: int
    name: str
    status: str
    started_at: Optional[str]
    ended_at: Optional[str]
    scheduled_end_at: Optional[str]
    duration_weeks: Optional[int]
    created_at: str
    milestone_count: int
    achievement_count: int


class StartSeasonRequest(BaseModel):
    pass  # no body required — uses settings DB for conn info


class MilestonePatch(BaseModel):
    """All fields optional — only provided fields are updated (model_fields_set)."""
    name: Optional[str] = None
    milestone_type: Optional[str] = None
    level_target: Optional[int] = None          # explicit None clears the target
    reward_item_hex: Optional[str] = None        # "" or None = clear reward; non-empty = replace
    reward_item_name: Optional[str] = None
    time_limit_hours: Optional[int] = None       # explicit None clears the limit


class ValidateItemRequest(BaseModel):
    reward_item_hex: str


class ValidateItemResponse(BaseModel):
    item_name: Optional[str]
    item_code: Optional[str]
    quality: Optional[int]


class CharacterStatEntry(BaseModel):
    name: str
    class_name: str
    level: int
    ever_died: bool
    difficulty_active: int


class SeasonStatsOut(BaseModel):
    season_id: int
    season_name: str
    status: str
    started_at: Optional[str]
    scheduled_end_at: Optional[str]
    days_elapsed: int
    highest_level_sc: Optional[int]
    highest_level_hc: Optional[int]
    characters_sc: list[CharacterStatEntry]
    characters_hc: list[CharacterStatEntry]
    total_gold_vault_sc: int
    total_gold_vault_hc: int
    grail_uniques_sc: int
    grail_sets_sc: int
    grail_uniques_hc: int
    grail_sets_hc: int
    grail_catalog_total: int
    grail_progress_pct: float


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _ms_out(ms: SeasonMilestone, season_started_at: datetime | None = None) -> MilestoneOut:
    is_expired = False
    if ms.time_limit_hours is not None and season_started_at is not None:
        started = season_started_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        deadline = started + timedelta(hours=ms.time_limit_hours)
        is_expired = datetime.now(timezone.utc) > deadline

    return MilestoneOut(
        id=ms.id,
        season_id=ms.season_id,
        name=ms.name,
        milestone_type=ms.milestone_type,
        level_target=ms.level_target,
        reward_item_name=ms.reward_item_name,
        reward_item_code=ms.reward_item_code,
        has_reward=ms.reward_item_bytes is not None,
        time_limit_hours=ms.time_limit_hours,
        is_expired=is_expired,
        sort_order=ms.sort_order,
    )


def _ach_out(a: SeasonAchievement) -> AchievementOut:
    return AchievementOut(
        id=a.id,
        season_id=a.season_id,
        milestone_id=a.milestone_id,
        character_name=a.character_name,
        character_class=a.character_class,
        character_level=a.character_level,
        achieved_at=a.achieved_at.isoformat(),
        claimed_at=a.claimed_at.isoformat() if a.claimed_at else None,
    )


def _scheduled_end_at(season: Season) -> str | None:
    if season.started_at is None or season.duration_weeks is None:
        return None
    started = season.started_at
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    return (started + timedelta(weeks=season.duration_weeks)).isoformat()


async def _season_out(session: AsyncSession, season: Season) -> SeasonOut:
    ms_result = await session.execute(
        select(SeasonMilestone)
        .where(SeasonMilestone.season_id == season.id)
        .order_by(SeasonMilestone.sort_order)
    )
    milestones = list(ms_result.scalars().all())

    ach_result = await session.execute(
        select(SeasonAchievement)
        .where(SeasonAchievement.season_id == season.id)
        .order_by(SeasonAchievement.achieved_at)
    )
    achievements = list(ach_result.scalars().all())

    return SeasonOut(
        id=season.id,
        name=season.name,
        status=season.status,
        started_at=season.started_at.isoformat() if season.started_at else None,
        ended_at=season.ended_at.isoformat() if season.ended_at else None,
        scheduled_end_at=_scheduled_end_at(season),
        notes=season.notes,
        duration_weeks=season.duration_weeks,
        created_at=season.created_at.isoformat(),
        milestones=[_ms_out(m, season.started_at) for m in milestones],
        achievements=[_ach_out(a) for a in achievements],
    )


def _hex_to_bytes(hex_str: str) -> bytes:
    """Parse space-separated or continuous hex string to bytes."""
    cleaned = hex_str.replace(" ", "").replace("\n", "").replace("\t", "")
    return bytes.fromhex(cleaned)


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.get("/seasons", response_model=list[SeasonListItem])
async def list_seasons(session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Season).order_by(Season.created_at.desc())
    )
    seasons = result.scalars().all()

    items = []
    for s in seasons:
        ms_count = len((await session.execute(
            select(SeasonMilestone).where(SeasonMilestone.season_id == s.id)
        )).scalars().all())
        ach_count = len((await session.execute(
            select(SeasonAchievement).where(SeasonAchievement.season_id == s.id)
        )).scalars().all())
        items.append(SeasonListItem(
            id=s.id,
            name=s.name,
            status=s.status,
            started_at=s.started_at.isoformat() if s.started_at else None,
            ended_at=s.ended_at.isoformat() if s.ended_at else None,
            scheduled_end_at=_scheduled_end_at(s),
            duration_weeks=s.duration_weeks,
            created_at=s.created_at.isoformat(),
            milestone_count=ms_count,
            achievement_count=ach_count,
        ))
    return items


@router.get("/seasons/active", response_model=SeasonOut)
async def get_active_season(session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Season).where(Season.status == "active")
    )
    season = result.scalar_one_or_none()
    if season is None:
        raise HTTPException(404, "No active season")
    return await _season_out(session, season)


async def _live_stats_out(session: AsyncSession, season: Season) -> SeasonStatsOut:
    """Compute live season stats from current DB data."""
    chars_result = await session.execute(select(Character).where(Character.season_id == None))
    all_chars = list(chars_result.scalars().all())
    sc_chars = [c for c in all_chars if not c.hardcore]
    hc_chars = [c for c in all_chars if c.hardcore]

    highest_level_sc = max((c.level for c in sc_chars), default=None)
    highest_level_hc = max((c.level for c in hc_chars), default=None)

    gold_result = await session.execute(select(GoldVault))
    gold_map = {g.hardcore: g.amount for g in gold_result.scalars().all()}

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

    days_elapsed = 0
    if season.started_at:
        started = season.started_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        days_elapsed = (datetime.now(timezone.utc) - started).days

    grail_progress_pct = round(
        (grail_uniques_sc + grail_sets_sc) / grail_catalog_total * 100, 1
    ) if grail_catalog_total > 0 else 0.0

    return SeasonStatsOut(
        season_id=season.id,
        season_name=season.name,
        status=season.status,
        started_at=season.started_at.isoformat() if season.started_at else None,
        scheduled_end_at=_scheduled_end_at(season),
        days_elapsed=days_elapsed,
        highest_level_sc=highest_level_sc,
        highest_level_hc=highest_level_hc,
        characters_sc=[CharacterStatEntry(**{k: getattr(c, k) for k in ("name", "class_name", "level", "ever_died", "difficulty_active")}) for c in sc_chars],
        characters_hc=[CharacterStatEntry(**{k: getattr(c, k) for k in ("name", "class_name", "level", "ever_died", "difficulty_active")}) for c in hc_chars],
        total_gold_vault_sc=gold_map.get(False, 0),
        total_gold_vault_hc=gold_map.get(True, 0),
        grail_uniques_sc=grail_uniques_sc,
        grail_sets_sc=grail_sets_sc,
        grail_uniques_hc=grail_uniques_hc,
        grail_sets_hc=grail_sets_hc,
        grail_catalog_total=grail_catalog_total,
        grail_progress_pct=grail_progress_pct,
    )


@router.get("/seasons/active/stats", response_model=SeasonStatsOut)
async def get_active_season_stats(session: AsyncSession = Depends(get_session)):
    """Live metrics for the active season, computed from current DB data."""
    result = await session.execute(select(Season).where(Season.status == "active"))
    season = result.scalar_one_or_none()
    if season is None:
        raise HTTPException(404, "No active season")
    return await _live_stats_out(session, season)


@router.get("/seasons/{season_id}/stats", response_model=SeasonStatsOut)
async def get_season_stats(season_id: int, session: AsyncSession = Depends(get_session)):
    """Finalized metrics for a completed season from the SeasonStats snapshot."""
    season = await session.get(Season, season_id)
    if season is None:
        raise HTTPException(404, "Season not found")

    # For active seasons, return live data
    if season.status == "active":
        return await _live_stats_out(session, season)

    stats_result = await session.execute(
        select(SeasonStats).where(SeasonStats.season_id == season_id)
    )
    stats = stats_result.scalar_one_or_none()
    if stats is None:
        raise HTTPException(404, "No stats snapshot found for this season")

    days_elapsed = stats.days_played or 0
    grail_progress_pct = round(
        (stats.grail_uniques_sc + stats.grail_sets_sc) / stats.grail_catalog_total * 100, 1
    ) if stats.grail_catalog_total > 0 else 0.0

    return SeasonStatsOut(
        season_id=season.id,
        season_name=season.name,
        status=season.status,
        started_at=season.started_at.isoformat() if season.started_at else None,
        scheduled_end_at=_scheduled_end_at(season),
        days_elapsed=days_elapsed,
        highest_level_sc=stats.highest_level_sc,
        highest_level_hc=stats.highest_level_hc,
        characters_sc=[CharacterStatEntry(**c) for c in (stats.characters_sc or [])],
        characters_hc=[CharacterStatEntry(**c) for c in (stats.characters_hc or [])],
        total_gold_vault_sc=stats.total_gold_vault_sc,
        total_gold_vault_hc=stats.total_gold_vault_hc,
        grail_uniques_sc=stats.grail_uniques_sc,
        grail_sets_sc=stats.grail_sets_sc,
        grail_uniques_hc=stats.grail_uniques_hc,
        grail_sets_hc=stats.grail_sets_hc,
        grail_catalog_total=stats.grail_catalog_total,
        grail_progress_pct=grail_progress_pct,
    )


@router.post("/seasons", response_model=SeasonOut)
async def create_season(body: SeasonCreate, session: AsyncSession = Depends(get_session)):
    if body.duration_weeks is not None and not (1 <= body.duration_weeks <= 26):
        raise HTTPException(400, "duration_weeks must be between 1 and 26")

    season = Season(
        name=body.name,
        status="setup",
        notes=body.notes,
        duration_weeks=body.duration_weeks,
        created_at=datetime.now(timezone.utc),
    )
    session.add(season)
    await session.flush()  # get season.id

    for ms_in in body.milestones:
        if ms_in.time_limit_hours is not None and ms_in.time_limit_hours <= 0:
            raise HTTPException(400, f"time_limit_hours must be positive for milestone '{ms_in.name}'")

        reward_bytes: bytes | None = None
        if ms_in.reward_item_hex:
            try:
                reward_bytes = _hex_to_bytes(ms_in.reward_item_hex)
            except ValueError as e:
                raise HTTPException(400, f"Invalid hex for milestone '{ms_in.name}': {e}")

        ms = SeasonMilestone(
            season_id=season.id,
            name=ms_in.name,
            milestone_type=ms_in.milestone_type,
            level_target=ms_in.level_target,
            reward_item_bytes=reward_bytes,
            reward_item_name=ms_in.reward_item_name,
            reward_item_code=ms_in.reward_item_code,
            time_limit_hours=ms_in.time_limit_hours,
            sort_order=ms_in.sort_order,
        )
        session.add(ms)

    await session.commit()
    return await _season_out(session, season)


@router.get("/seasons/{season_id}", response_model=SeasonOut)
async def get_season(season_id: int, session: AsyncSession = Depends(get_session)):
    season = await session.get(Season, season_id)
    if season is None:
        raise HTTPException(404, "Season not found")
    return await _season_out(session, season)


@router.delete("/seasons/{season_id}")
async def delete_season(season_id: int, session: AsyncSession = Depends(get_session)):
    season = await session.get(Season, season_id)
    if season is None:
        raise HTTPException(404, "Season not found")
    if season.status == "active":
        raise HTTPException(400, "Cannot delete an active season; end it first")

    await session.execute(
        delete(SeasonAchievement).where(SeasonAchievement.season_id == season_id)
    )
    await session.execute(
        delete(SeasonMilestone).where(SeasonMilestone.season_id == season_id)
    )
    await session.delete(season)
    await session.commit()
    return {"success": True}


@router.post("/seasons/{season_id}/start", response_model=SeasonOut)
async def start_season(
    season_id: int,
    session: AsyncSession = Depends(get_session),
):
    from backend.services.seasons_service import start_season as _start_season

    try:
        season = await _start_season(session=session, season_id=season_id)
    except ValueError as e:
        raise HTTPException(400, str(e))

    return await _season_out(session, season)


@router.post("/seasons/{season_id}/end", response_model=SeasonOut)
async def end_season(season_id: int, session: AsyncSession = Depends(get_session)):
    from backend.services.seasons_service import compute_and_save_season_stats

    season = await session.get(Season, season_id)
    if season is None:
        raise HTTPException(404, "Season not found")
    if season.status != "active":
        raise HTTPException(400, "Season is not active")

    # Snapshot metrics before marking completed
    await compute_and_save_season_stats(session, season)

    season.status = "completed"
    season.ended_at = datetime.now(timezone.utc)
    await session.commit()
    return await _season_out(session, season)


@router.get("/seasons/{season_id}/achievements", response_model=list[AchievementOut])
async def get_achievements(season_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(SeasonAchievement)
        .where(SeasonAchievement.season_id == season_id)
        .order_by(SeasonAchievement.achieved_at)
    )
    return [_ach_out(a) for a in result.scalars().all()]


@router.post("/seasons/milestones/validate-item", response_model=ValidateItemResponse)
async def validate_item(body: ValidateItemRequest):
    """Parse hex bytes and return item preview info."""
    try:
        item_bytes = _hex_to_bytes(body.reward_item_hex)
    except ValueError as e:
        raise HTTPException(400, f"Invalid hex: {e}")

    try:
        from backend.services.item_parsing.item_flags import read_item_flags
        from backend.services.item_parsing.item_fields import read_item_fields
        from backend.services.item_parsing.item_names import resolve_name, base_name

        flags = read_item_flags(item_bytes, byte_start=0)
        fields = read_item_fields(item_bytes, flags, byte_start=0)
        display_name, _ = resolve_name(
            fields.item_type, fields.quality, flags.is_simple, flags.is_ear,
            fields.unique_id, fields.set_id,
            fields.magic_prefix_id, fields.magic_suffix_id,
            fields.rare_name1, fields.rare_name2,
        )
        b_name = base_name(fields.item_type)

        return ValidateItemResponse(
            item_name=display_name or b_name,
            item_code=fields.item_type.strip(),
            quality=fields.quality,
        )
    except Exception as e:
        log.warning("validate-item parse error: %s", e)
        return ValidateItemResponse(item_name=None, item_code=None, quality=None)


@router.post("/seasons/achievements/{achievement_id}/claim")
async def claim_achievement(
    achievement_id: int,
    session: AsyncSession = Depends(get_session),
):
    from backend.services.seasons_service import claim_reward

    # Determine target machine — prefer PC if online, else Deck
    machine = "pc"
    try:
        conn = await _get_conn_kwargs(session, machine)
        save_dir = await _get_setting(session, f"{machine}_save_path") or ""

        def _check_online():
            with ssh_mod.get_sftp(**conn) as (_ssh, _sftp):
                pass
        import asyncio
        await asyncio.to_thread(_check_online)
    except Exception:
        machine = "deck"
        try:
            conn = await _get_conn_kwargs(session, machine)
            save_dir = await _get_setting(session, f"{machine}_save_path") or ""
        except Exception as e:
            raise HTTPException(400, f"Cannot connect to any machine: {e}")

    is_windows = machine == "pc"

    try:
        achievement = await claim_reward(
            session=session,
            achievement_id=achievement_id,
            machine=machine,
            conn=conn,
            save_dir=save_dir,
            is_windows=is_windows,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(409, str(e))

    return {"success": True, "claimed_at": achievement.claimed_at.isoformat()}


# ─── Milestone editing ────────────────────────────────────────────────────────

async def _editable_season_and_milestone(
    season_id: int,
    milestone_id: int,
    session: AsyncSession,
) -> tuple[Season, SeasonMilestone]:
    """Shared guard: season exists, is not completed, milestone belongs to it."""
    season = await session.get(Season, season_id)
    if season is None:
        raise HTTPException(404, "Season not found")
    if season.status == "completed":
        raise HTTPException(400, "Cannot edit milestones on a completed season")
    ms = await session.get(SeasonMilestone, milestone_id)
    if ms is None or ms.season_id != season_id:
        raise HTTPException(404, "Milestone not found")
    return season, ms


@router.post("/seasons/{season_id}/milestones", response_model=MilestoneOut)
async def add_milestone(
    season_id: int,
    body: MilestoneIn,
    session: AsyncSession = Depends(get_session),
):
    """Add a single milestone to an active or setup season."""
    season = await session.get(Season, season_id)
    if season is None:
        raise HTTPException(404, "Season not found")
    if season.status == "completed":
        raise HTTPException(400, "Cannot add milestones to a completed season")
    if body.time_limit_hours is not None and body.time_limit_hours <= 0:
        raise HTTPException(400, "time_limit_hours must be positive")

    # Append after existing milestones
    max_order_result = await session.execute(
        select(func.max(SeasonMilestone.sort_order))
        .where(SeasonMilestone.season_id == season_id)
    )
    max_order = max_order_result.scalar() or 0
    sort_order = body.sort_order if body.sort_order > max_order else max_order + 1

    reward_bytes: bytes | None = None
    if body.reward_item_hex:
        try:
            reward_bytes = _hex_to_bytes(body.reward_item_hex)
        except ValueError as e:
            raise HTTPException(400, f"Invalid hex: {e}")

    ms = SeasonMilestone(
        season_id=season_id,
        name=body.name,
        milestone_type=body.milestone_type,
        level_target=body.level_target,
        reward_item_bytes=reward_bytes,
        reward_item_name=body.reward_item_name,
        reward_item_code=body.reward_item_code,
        time_limit_hours=body.time_limit_hours,
        sort_order=sort_order,
    )
    session.add(ms)
    await session.commit()
    return _ms_out(ms, season.started_at)


@router.patch("/seasons/{season_id}/milestones/{milestone_id}", response_model=MilestoneOut)
async def patch_milestone(
    season_id: int,
    milestone_id: int,
    body: MilestonePatch,
    session: AsyncSession = Depends(get_session),
):
    """
    Partially update a milestone. Only fields present in the request body are
    changed — absent fields are left untouched (model_fields_set semantics).

    Reward handling:
      - reward_item_hex not provided  → keep existing reward bytes
      - reward_item_hex = "" or null  → clear reward (bytes + name + code)
      - reward_item_hex = "<hex>"     → replace reward bytes
    Time limit:
      - time_limit_hours not provided → keep existing
      - time_limit_hours = null       → clear (no time limit)
    """
    season, ms = await _editable_season_and_milestone(season_id, milestone_id, session)
    fields = body.model_fields_set

    if "name" in fields and body.name is not None:
        ms.name = body.name

    if "milestone_type" in fields and body.milestone_type is not None:
        ms.milestone_type = body.milestone_type

    if "level_target" in fields:
        ms.level_target = body.level_target

    if "reward_item_hex" in fields:
        if not body.reward_item_hex:
            ms.reward_item_bytes = None
            ms.reward_item_name = None
            ms.reward_item_code = None
        else:
            try:
                ms.reward_item_bytes = _hex_to_bytes(body.reward_item_hex)
            except ValueError as e:
                raise HTTPException(400, f"Invalid hex: {e}")
            if "reward_item_name" in fields:
                ms.reward_item_name = body.reward_item_name
    elif "reward_item_name" in fields:
        ms.reward_item_name = body.reward_item_name

    if "time_limit_hours" in fields:
        ms.time_limit_hours = body.time_limit_hours

    await session.commit()
    return _ms_out(ms, season.started_at)


@router.delete("/seasons/{season_id}/milestones/{milestone_id}")
async def delete_milestone(
    season_id: int,
    milestone_id: int,
    session: AsyncSession = Depends(get_session),
):
    """
    Delete a milestone and cascade-delete all of its achievements.
    Returns the number of achievement records removed so the caller can warn
    the user if any claimed rewards are affected.
    """
    _season, ms = await _editable_season_and_milestone(season_id, milestone_id, session)

    ach_result = await session.execute(
        select(func.count(SeasonAchievement.id))
        .where(SeasonAchievement.milestone_id == milestone_id)
    )
    achievements_deleted = ach_result.scalar() or 0

    await session.execute(
        delete(SeasonAchievement).where(SeasonAchievement.milestone_id == milestone_id)
    )
    await session.delete(ms)
    await session.commit()

    return {"success": True, "achievements_deleted": achievements_deleted}
