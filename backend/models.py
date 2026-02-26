from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean, JSON, BigInteger, Float, ForeignKey, LargeBinary, UniqueConstraint
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
    filename = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    class_id = Column(Integer, nullable=False)
    class_name = Column(String, nullable=False)
    level = Column(Integer, nullable=False)
    hardcore = Column(Boolean, default=False)
    ever_died = Column(Boolean, default=False)
    expansion = Column(Boolean, default=True)
    modified_at = Column(Float, nullable=False)
    last_updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


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
    tab = Column(Integer, nullable=False)                        # original page index (0-based)
    hardcore = Column(Boolean, nullable=False, default=False)
    raw_item_bytes = Column(LargeBinary, nullable=False)
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
