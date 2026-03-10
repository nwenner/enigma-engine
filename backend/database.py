from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text
from backend.models import Base

DATA_DIR = Path("/app/data")
DB_PATH = DATA_DIR / "db.sqlite"

# Allow override for local dev
import os
_db_url = os.environ.get("DATABASE_URL", f"sqlite+aiosqlite:///{DB_PATH}")

engine = create_async_engine(_db_url, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    """Create all tables if they don't exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Runtime migration: add label column if not present (for existing installs)
        try:
            await conn.execute(text("ALTER TABLE backup_snapshots ADD COLUMN label TEXT DEFAULT 'pre_sync'"))
        except Exception:
            pass  # column already exists
        try:
            await conn.execute(text("ALTER TABLE vault_items ADD COLUMN item_level INTEGER DEFAULT 0"))
        except Exception:
            pass
        try:
            await conn.execute(text("ALTER TABLE vault_items ADD COLUMN is_ethereal BOOLEAN DEFAULT 0"))
        except Exception:
            pass
        try:
            await conn.execute(text("ALTER TABLE vault_items ADD COLUMN properties JSON DEFAULT '[]'"))
        except Exception:
            pass

        # ── Seasons feature migrations ──────────────────────────────────────
        # characters: difficulty_active
        try:
            await conn.execute(text("ALTER TABLE characters ADD COLUMN difficulty_active INTEGER NOT NULL DEFAULT 0"))
        except Exception:
            pass

        # characters: uuid + season_id (table recreation required to drop old unique index on filename)
        needs_char_migration = False
        try:
            await conn.execute(text("SELECT uuid FROM characters LIMIT 1"))
        except Exception:
            needs_char_migration = True

        if needs_char_migration:
            await conn.execute(text("""
                CREATE TABLE characters_new (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    uuid        TEXT NOT NULL DEFAULT '',
                    filename    TEXT NOT NULL,
                    season_id   INTEGER REFERENCES seasons(id),
                    name        TEXT NOT NULL,
                    class_id    INTEGER NOT NULL,
                    class_name  TEXT NOT NULL,
                    level       INTEGER NOT NULL,
                    hardcore    BOOLEAN DEFAULT 0,
                    ever_died   BOOLEAN DEFAULT 0,
                    expansion   BOOLEAN DEFAULT 1,
                    difficulty_active INTEGER NOT NULL DEFAULT 0,
                    modified_at REAL NOT NULL,
                    last_updated_at DATETIME
                )
            """))
            await conn.execute(text("""
                INSERT INTO characters_new
                    (id, uuid, filename, season_id, name, class_id, class_name, level,
                     hardcore, ever_died, expansion, difficulty_active, modified_at, last_updated_at)
                SELECT
                    id,
                    lower(hex(randomblob(16))),
                    filename, NULL, name, class_id, class_name, level,
                    hardcore, ever_died, expansion, difficulty_active, modified_at, last_updated_at
                FROM characters
            """))
            await conn.execute(text("DROP TABLE characters"))
            await conn.execute(text("ALTER TABLE characters_new RENAME TO characters"))
            await conn.execute(text(
                "CREATE UNIQUE INDEX uq_active_character_filename "
                "ON characters(filename) WHERE season_id IS NULL"
            ))
            await conn.execute(text(
                "CREATE UNIQUE INDEX uq_archived_character_filename_season "
                "ON characters(filename, season_id) WHERE season_id IS NOT NULL"
            ))
            await conn.execute(text(
                "CREATE UNIQUE INDEX uq_character_uuid ON characters(uuid)"
            ))

        # seasons: duration_weeks
        try:
            await conn.execute(text("ALTER TABLE seasons ADD COLUMN duration_weeks INTEGER"))
        except Exception:
            pass

        # season_milestones: time_limit_hours
        try:
            await conn.execute(text("ALTER TABLE season_milestones ADD COLUMN time_limit_hours INTEGER"))
        except Exception:
            pass

        # season_milestones: numeric_target (for quantity-based milestones e.g. gold_vault)
        try:
            await conn.execute(text("ALTER TABLE season_milestones ADD COLUMN numeric_target INTEGER"))
        except Exception:
            pass


async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
