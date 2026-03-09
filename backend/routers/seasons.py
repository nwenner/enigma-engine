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
  POST   /api/seasons/milestones/validate-item — parse hex bytes → item preview
  POST   /api/seasons/achievements/{id}/claim  — claim reward item
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_session
from backend.models import Season, SeasonMilestone, SeasonAchievement
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


class ValidateItemRequest(BaseModel):
    reward_item_hex: str


class ValidateItemResponse(BaseModel):
    item_name: Optional[str]
    item_code: Optional[str]
    quality: Optional[int]


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
        pc_conn = await _get_conn_kwargs(session, "pc")
        deck_conn = await _get_conn_kwargs(session, "deck")
        pc_save_dir = await _get_setting(session, "pc_save_path") or ""
        deck_save_dir = await _get_setting(session, "deck_save_path") or ""
    except Exception as e:
        raise HTTPException(400, f"Config error: {e}")

    if not pc_conn.get("host") or not deck_conn.get("host"):
        raise HTTPException(400, "Both PC and Deck must be configured to start a season")
    if not pc_save_dir or not deck_save_dir:
        raise HTTPException(400, "Save paths must be configured for both machines")

    try:
        season = await _start_season(
            session=session,
            season_id=season_id,
            pc_conn=pc_conn,
            deck_conn=deck_conn,
            pc_save_dir=pc_save_dir,
            deck_save_dir=deck_save_dir,
            pc_is_windows=True,
            deck_is_windows=False,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(409, str(e))

    return await _season_out(session, season)


@router.post("/seasons/{season_id}/end", response_model=SeasonOut)
async def end_season(season_id: int, session: AsyncSession = Depends(get_session)):
    season = await session.get(Season, season_id)
    if season is None:
        raise HTTPException(404, "Season not found")
    if season.status != "active":
        raise HTTPException(400, "Season is not active")

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
