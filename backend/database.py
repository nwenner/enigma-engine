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


async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
