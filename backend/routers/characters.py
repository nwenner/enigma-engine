"""
Characters router.

Endpoints:
  GET /api/characters?source=pc|deck|all
    Returns list of characters with metadata from the remote save directories.
"""
import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_session
from backend.routers.settings import _get_conn_kwargs, _get_setting
from backend.services.ssh_client import get_sftp, list_d2s_files, SSHConnectionError
from backend.services.d2s_parser import parse_d2s, D2SParseError

log = logging.getLogger(__name__)
router = APIRouter(tags=["characters"])


class CharacterInfo(BaseModel):
    name: str
    class_name: str
    class_id: int
    level: int
    hardcore: bool
    ever_died: bool
    expansion: bool
    filename: str
    source: str          # "pc" | "deck"
    modified_at: float   # epoch seconds
    size: int            # bytes


async def _fetch_characters(session: AsyncSession, machine: str) -> list[CharacterInfo]:
    try:
        conn_kwargs = await _get_conn_kwargs(session, machine)
        save_path = await _get_setting(session, f"{machine}_save_path") or ""
    except Exception as e:
        raise HTTPException(502, f"Config error for {machine}: {e}")

    if not conn_kwargs.get("host"):
        raise HTTPException(422, f"{machine.upper()} host is not configured")
    if not save_path:
        raise HTTPException(422, f"{machine.upper()} save path is not configured")

    def _get():
        with get_sftp(**conn_kwargs) as (_ssh, sftp):
            files = list_d2s_files(sftp, save_path)
            results = []
            for f in files:
                if not f["filename"].endswith(".d2s"):
                    continue
                # Download just this file to a tmp location to parse
                with tempfile.NamedTemporaryFile(suffix=".d2s", delete=False) as tmp:
                    tmp_path = Path(tmp.name)
                try:
                    sftp.get(f["path"], str(tmp_path))
                    char = parse_d2s(tmp_path)
                    results.append(
                        CharacterInfo(
                            **char.to_dict(),
                            source=machine,
                            modified_at=f["modified_at"],
                            size=f["size"],
                        )
                    )
                except D2SParseError as e:
                    log.warning("Could not parse %s on %s: %s", f["filename"], machine, e)
                finally:
                    tmp_path.unlink(missing_ok=True)
            return results

    try:
        return await asyncio.to_thread(_get)
    except SSHConnectionError as e:
        raise HTTPException(502, f"SSH error connecting to {machine.upper()}: {e}")
    except Exception as e:
        raise HTTPException(502, f"Error fetching characters from {machine.upper()}: {e}")


@router.get("/characters", response_model=list[CharacterInfo])
async def get_characters(
    source: str = Query("all", pattern="^(pc|deck|all)$"),
    session: AsyncSession = Depends(get_session),
):
    if source == "all":
        # Fetch sequentially to avoid concurrent access on the shared DB session.
        # Partial results are returned if one machine is unreachable.
        pc_chars: list[CharacterInfo] = []
        deck_chars: list[CharacterInfo] = []

        try:
            pc_chars = await _fetch_characters(session, "pc")
        except HTTPException:
            pass

        try:
            deck_chars = await _fetch_characters(session, "deck")
        except HTTPException:
            pass

        return pc_chars + deck_chars

    return await _fetch_characters(session, source)
