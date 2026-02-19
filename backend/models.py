from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean, JSON, BigInteger
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


class Settings(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String, unique=True, nullable=False)
    value = Column(String, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
