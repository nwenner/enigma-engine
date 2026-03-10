import uuid as _uuid
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean, JSON, BigInteger, Float, ForeignKey, LargeBinary, UniqueConstraint, Index, text
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class SyncOperation(Base):
    __tablename__ = "sync_operations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    direction = Column(String, nullable=False)  # "pc_to_deck" | "deck_to_pc"
    status = Column(String, nullable=False, default="pending")  # pending | running | success | failed
    error_message = Column(String, nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    file_count = Column(Integer, default=0)


class SyncFileRecord(Base):
    __tablename__ = "sync_file_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sync_operation_id = Column(Integer, nullable=False)
    filename = Column(String, nullable=False)
    source_machine = Column(String, nullable=False)  # "pc" | "deck"
    dest_machine = Column(String, nullable=False)
    bytes_transferred = Column(BigInteger, default=0)
    success = Column(Boolean, default=True)
    error_message = Column(String, nullable=True)
    char_snapshot = Column(JSON, nullable=True)  # D2SCharacter data at time of sync
    synced_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class BackupSnapshot(Base):
    __tablename__ = "backup_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_machine = Column(String, nullable=False)  # "pc" | "deck" - machine that was backed up
    snapshot_path = Column(String, nullable=False)  # relative path under data/backups/
    file_count = Column(Integer, default=0)
    characters = Column(JSON, nullable=True)  # list of D2SCharacter dicts at snapshot time
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    sync_operation_id = Column(Integer, nullable=True)
    label = Column(String, nullable=False, default="pre_sync")  # "pre_sync" | "game_close" | "manual" | "pre_grail_deposit" | "pre_grail_retrieve"


class Character(Base):
    __tablename__ = "characters"

    id = Column(Integer, primary_key=True, autoincrement=True)
    uuid = Column(String, nullable=False, unique=True, default=lambda: str(_uuid.uuid4()))
    filename = Column(String, nullable=False, index=True)
    # null = currently active character; set to season.id when season ends/new season starts
    season_id = Column(Integer, ForeignKey("seasons.id"), nullable=True, index=True)
    name = Column(String, nullable=False)
    class_id = Column(Integer, nullable=False)
    class_name = Column(String, nullable=False)
    level = Column(Integer, nullable=False)
    hardcore = Column(Boolean, default=False)
    ever_died = Column(Boolean, default=False)
    expansion = Column(Boolean, default=True)
    difficulty_active = Column(Integer, nullable=False, default=0)  # 0=Normal, 1=Nightmare, 2=Hell
    modified_at = Column(Float, nullable=False)
    last_updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        # Active chars: unique filename per slot (season_id IS NULL)
        Index("uq_active_character_filename", "filename", unique=True,
              sqlite_where=text("season_id IS NULL")),
        # Archived chars: unique filename within a season
        Index("uq_archived_character_filename_season", "filename", "season_id", unique=True,
              sqlite_where=text("season_id IS NOT NULL")),
    )


class Settings(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String, unique=True, nullable=False)
    value = Column(String, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class GrailCatalog(Base):
    __tablename__ = "grail_catalog"

    id = Column(Integer, primary_key=True)
    item_code = Column(String(4), nullable=False, index=True)  # 4-char D2R type code
    name = Column(String, nullable=False)                       # "Windforce"
    base_item = Column(String, nullable=False)                  # "Hydra Bow"
    quality = Column(String, nullable=False)                    # "unique" | "set"
    set_name = Column(String, nullable=True)                    # set family name or null
    unique_id = Column(Integer, nullable=True, index=True)      # 12-bit quality_data (unique items)
    set_id = Column(Integer, nullable=True, index=True)         # 12-bit quality_data (set items)
    sort_order = Column(Integer, default=0)


class VaultItem(Base):
    """An item stored in the virtual item vault (removed from stash, preserved for retrieval)."""
    __tablename__ = "vault_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    item_code = Column(String(4), nullable=False, default="")   # 4-char type code (empty for Modern items)
    name = Column(String, nullable=True)                         # from GrailCatalog, or None
    base_item = Column(String, nullable=True)                    # from GrailCatalog, or None
    quality = Column(Integer, nullable=False)                    # raw quality value (7=unique, 5=set, etc.)
    item_level = Column(Integer, nullable=False, default=0)      # ilvl from bitstream
    is_ethereal = Column(Boolean, nullable=False, default=False) # ethereal flag (bit 20 from item start)
    tab = Column(Integer, nullable=False)                        # original page index (0-based)
    hardcore = Column(Boolean, nullable=False, default=False)
    raw_item_bytes = Column(LargeBinary, nullable=False)
    properties = Column(JSON, nullable=False, default=list)  # parsed stat strings e.g. ["+7% Poison Resist"]
    stored_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    notes = Column(String, nullable=True)
    catalog_id = Column(Integer, ForeignKey("grail_catalog.id"), nullable=True)


class GoldVault(Base):
    """Gold deposited from stash into the app (bypasses 12.5M stash cap)."""
    __tablename__ = "gold_vault"

    id = Column(Integer, primary_key=True, autoincrement=True)
    hardcore = Column(Boolean, nullable=False, unique=True)
    amount = Column(BigInteger, nullable=False, default=0)
    last_updated = Column(DateTime, default=datetime.utcnow, nullable=False)


class GrailEntry(Base):
    __tablename__ = "grail_entries"

    id = Column(Integer, primary_key=True)
    catalog_id = Column(Integer, ForeignKey("grail_catalog.id"), nullable=False, index=True)
    hardcore = Column(Boolean, nullable=False, default=False)
    found_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    find_count = Column(Integer, default=1, nullable=False)
    last_found_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    raw_item_bytes = Column(LargeBinary, nullable=True)   # full item bytes for retrieval
    raw_item_bit_len = Column(Integer, nullable=True)     # exact bit length of item
    is_deposited = Column(Boolean, nullable=False, default=False)  # True if tab 5 was cleared

    __table_args__ = (UniqueConstraint("catalog_id", "hardcore", name="uq_grail_entry"),)


# ─── Seasons ──────────────────────────────────────────────────────────────────

class Season(Base):
    __tablename__ = "seasons"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)                       # "Season 1: Ladder Reset"
    status = Column(String, nullable=False, default="setup")    # "setup" | "active" | "completed"
    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    archive_snapshot_id = Column(Integer, ForeignKey("backup_snapshots.id"), nullable=True)
    notes = Column(String, nullable=True)
    duration_weeks = Column(Integer, nullable=True)             # null = no time limit; 1-26
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class SeasonMilestone(Base):
    __tablename__ = "season_milestones"

    id = Column(Integer, primary_key=True, autoincrement=True)
    season_id = Column(Integer, ForeignKey("seasons.id"), nullable=False, index=True)
    name = Column(String, nullable=False)                       # "Cleared Normal", "Hit Level 50"
    milestone_type = Column(String, nullable=False)             # "level" | "cleared_normal" | "cleared_nightmare"
    level_target = Column(Integer, nullable=True)               # for milestone_type="level" only
    reward_item_bytes = Column(LargeBinary, nullable=True)
    reward_item_name = Column(String, nullable=True)            # display name
    reward_item_code = Column(String(4), nullable=True)         # 4-char type code for UI
    time_limit_hours = Column(Integer, nullable=True)           # null = no time limit; e.g. 48 = 2 days
    sort_order = Column(Integer, nullable=False, default=0)


class SeasonAchievement(Base):
    __tablename__ = "season_achievements"

    id = Column(Integer, primary_key=True, autoincrement=True)
    season_id = Column(Integer, ForeignKey("seasons.id"), nullable=False, index=True)
    milestone_id = Column(Integer, ForeignKey("season_milestones.id"), nullable=False, index=True)
    character_name = Column(String, nullable=False)
    character_class = Column(String, nullable=False)
    character_level = Column(Integer, nullable=False)
    achieved_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    claimed_at = Column(DateTime, nullable=True)                # null = reward not yet claimed

    __table_args__ = (UniqueConstraint("milestone_id", "character_name", name="uq_season_achievement"),)


# ─── Season Stats (finalized metrics snapshot at season end/start) ────────────

class SeasonStats(Base):
    __tablename__ = "season_stats"

    id                   = Column(Integer, primary_key=True, autoincrement=True)
    season_id            = Column(Integer, ForeignKey("seasons.id"), unique=True, nullable=False)
    highest_level_sc     = Column(Integer, nullable=True)
    highest_level_hc     = Column(Integer, nullable=True)
    characters_sc        = Column(JSON, nullable=False, default=list)
    # [{name, class_name, level, ever_died, difficulty_active}]
    characters_hc        = Column(JSON, nullable=False, default=list)
    total_gold_vault_sc  = Column(BigInteger, nullable=False, default=0)
    total_gold_vault_hc  = Column(BigInteger, nullable=False, default=0)
    grail_uniques_sc     = Column(Integer, nullable=False, default=0)
    grail_sets_sc        = Column(Integer, nullable=False, default=0)
    grail_uniques_hc     = Column(Integer, nullable=False, default=0)
    grail_sets_hc        = Column(Integer, nullable=False, default=0)
    grail_catalog_total  = Column(Integer, nullable=False, default=0)
    days_played          = Column(Integer, nullable=True)
    snapshot_at          = Column(DateTime, default=datetime.utcnow, nullable=False)


# ─── Season Reward Library ────────────────────────────────────────────────────

class SeasonReward(Base):
    """User-curated library of items to use as season milestone rewards."""
    __tablename__ = "season_rewards"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)           # User-defined label, e.g. "Harlequin Crest"
    item_code = Column(String(4), nullable=True)    # 4-char Huffman type code from parsing
    item_name = Column(String, nullable=True)       # Parsed display name
    quality = Column(Integer, nullable=True)        # Raw quality int (7=unique, 5=set, etc.)
    quality_name = Column(String, nullable=True)    # e.g. "unique"
    item_level = Column(Integer, nullable=True)     # Parsed ilvl
    is_ethereal = Column(Boolean, nullable=False, default=False)
    raw_item_bytes = Column(LargeBinary, nullable=False)
    notes = Column(String, nullable=True)           # Optional user notes
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
