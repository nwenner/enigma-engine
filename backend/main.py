from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.database import init_db
from backend.config import get_settings
from backend.routers import characters, sync, backups, history, settings as settings_router


FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = get_settings()
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    (cfg.data_dir / "backups" / "pc").mkdir(parents=True, exist_ok=True)
    (cfg.data_dir / "backups" / "deck").mkdir(parents=True, exist_ok=True)
    cfg.keys_dir.mkdir(parents=True, exist_ok=True)
    cfg.tmp_dir.mkdir(parents=True, exist_ok=True)
    await init_db()
    yield


app = FastAPI(title="Enigma Engine", lifespan=lifespan)

# API routers
app.include_router(characters.router, prefix="/api")
app.include_router(sync.router, prefix="/api")
app.include_router(backups.router, prefix="/api")
app.include_router(history.router, prefix="/api")
app.include_router(settings_router.router, prefix="/api")

# Serve React SPA static assets
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        index = FRONTEND_DIST / "index.html"
        return FileResponse(str(index))
