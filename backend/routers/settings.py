from __future__ import annotations

"""
Settings router.

Stores SSH connection config in the DB (Settings table), encrypting passwords
at rest using Fernet symmetric encryption.

Endpoints:
  GET  /api/settings           - Return current settings (passwords/keys redacted)
  PUT  /api/settings           - Update settings
  POST /api/settings/test-connection  - Test SSH to pc or deck
  POST /api/settings/upload-key/{machine} - Upload SSH private key file
"""
import logging
from pathlib import Path
from typing import Literal, Optional

from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.config import get_settings
from backend.database import get_session
from backend.models import Settings
from backend.services.ssh_client import get_sftp, SSHConnectionError

log = logging.getLogger(__name__)
router = APIRouter(tags=["settings"])

SETTING_KEYS = [
    "pc_host", "pc_port", "pc_username", "pc_password", "pc_auth_type",
    "pc_save_path", "deck_host", "deck_port", "deck_username", "deck_password",
    "deck_auth_type", "deck_save_path",
]


def _fernet() -> Fernet:
    key = get_settings().secret_key
    # Fernet requires a 32-byte URL-safe base64 key; derive one from the secret
    import base64, hashlib
    derived = base64.urlsafe_b64encode(hashlib.sha256(key.encode()).digest())
    return Fernet(derived)


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except (InvalidToken, Exception):
        return ""


async def _get_setting(session: AsyncSession, key: str) -> str | None:
    result = await session.execute(select(Settings).where(Settings.key == key))
    row = result.scalar_one_or_none()
    return row.value if row else None


async def _set_setting(session: AsyncSession, key: str, value: str) -> None:
    result = await session.execute(select(Settings).where(Settings.key == key))
    row = result.scalar_one_or_none()
    if row:
        row.value = value
    else:
        session.add(Settings(key=key, value=value))


# ─── Schema ────────────────────────────────────────────────────────────────────

class MachineSettings(BaseModel):
    host: str = ""
    port: int = 22
    username: str = ""
    password: str = ""       # write-only; read returns redacted
    auth_type: str = "password"  # "password" | "key"
    save_path: str = ""
    key_uploaded: bool = False   # read-only indicator


class SettingsResponse(BaseModel):
    pc: MachineSettings
    deck: MachineSettings


class SettingsUpdate(BaseModel):
    pc: Optional[MachineSettings] = None
    deck: Optional[MachineSettings] = None


# ─── Helpers ───────────────────────────────────────────────────────────────────

async def _load_machine_settings(session: AsyncSession, prefix: str) -> MachineSettings:
    cfg = get_settings()
    key_path = cfg.keys_dir / f"{prefix}.pem"
    password_raw = await _get_setting(session, f"{prefix}_password") or ""

    # Decrypt password if set
    password_display = "***SET***" if password_raw else ""

    return MachineSettings(
        host=await _get_setting(session, f"{prefix}_host") or "",
        port=int(await _get_setting(session, f"{prefix}_port") or "22"),
        username=await _get_setting(session, f"{prefix}_username") or "",
        password=password_display,
        auth_type=await _get_setting(session, f"{prefix}_auth_type") or "password",
        save_path=await _get_setting(session, f"{prefix}_save_path") or "",
        key_uploaded=key_path.exists(),
    )


async def _save_machine_settings(session: AsyncSession, prefix: str, data: MachineSettings) -> None:
    await _set_setting(session, f"{prefix}_host", data.host)
    await _set_setting(session, f"{prefix}_port", str(data.port))
    await _set_setting(session, f"{prefix}_username", data.username)
    await _set_setting(session, f"{prefix}_auth_type", data.auth_type)
    await _set_setting(session, f"{prefix}_save_path", data.save_path)

    # Only update password if caller sent a real value (not the redacted placeholder)
    if data.password and data.password != "***SET***":
        await _set_setting(session, f"{prefix}_password", encrypt(data.password))


async def _get_conn_kwargs(session: AsyncSession, prefix: str) -> dict:
    """Build connection kwargs for ssh_client.get_sftp()."""
    cfg = get_settings()
    host = await _get_setting(session, f"{prefix}_host") or ""
    port = int(await _get_setting(session, f"{prefix}_port") or "22")
    username = await _get_setting(session, f"{prefix}_username") or ""
    auth_type = await _get_setting(session, f"{prefix}_auth_type") or "password"
    password_enc = await _get_setting(session, f"{prefix}_password") or ""
    password = decrypt(password_enc) if password_enc else None

    key_path = cfg.keys_dir / f"{prefix}.pem"

    kwargs = dict(host=host, port=port, username=username)
    if auth_type == "key" and key_path.exists():
        kwargs["key_path"] = str(key_path)
    else:
        kwargs["password"] = password

    return kwargs


# ─── Routes ────────────────────────────────────────────────────────────────────

@router.get("/settings", response_model=SettingsResponse)
async def get_settings_route(session: AsyncSession = Depends(get_session)):
    pc = await _load_machine_settings(session, "pc")
    deck = await _load_machine_settings(session, "deck")
    return SettingsResponse(pc=pc, deck=deck)


@router.put("/settings", response_model=SettingsResponse)
async def update_settings(body: SettingsUpdate, session: AsyncSession = Depends(get_session)):
    if body.pc is not None:
        await _save_machine_settings(session, "pc", body.pc)
    if body.deck is not None:
        await _save_machine_settings(session, "deck", body.deck)
    await session.commit()

    pc = await _load_machine_settings(session, "pc")
    deck = await _load_machine_settings(session, "deck")
    return SettingsResponse(pc=pc, deck=deck)


class TestConnectionRequest(BaseModel):
    machine: Literal["pc", "deck"]


class TestConnectionResponse(BaseModel):
    success: bool
    message: str


@router.post("/settings/test-connection", response_model=TestConnectionResponse)
async def test_connection(body: TestConnectionRequest, session: AsyncSession = Depends(get_session)):
    import asyncio
    prefix = body.machine
    try:
        kwargs = await _get_conn_kwargs(session, prefix)
    except Exception as e:
        return TestConnectionResponse(success=False, message=f"Config error: {e}")

    def _test():
        with get_sftp(**kwargs) as (_ssh, sftp):
            sftp.listdir(".")
        return "Connection successful"

    try:
        msg = await asyncio.to_thread(_test)
        return TestConnectionResponse(success=True, message=msg)
    except SSHConnectionError as e:
        return TestConnectionResponse(success=False, message=str(e))
    except Exception as e:
        return TestConnectionResponse(success=False, message=f"Unexpected error: {e}")


@router.post("/settings/upload-key/{machine}")
async def upload_key(
    machine: Literal["pc", "deck"],
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
):
    cfg = get_settings()
    cfg.keys_dir.mkdir(parents=True, exist_ok=True)
    key_path = cfg.keys_dir / f"{machine}.pem"

    content = await file.read()
    if not content:
        raise HTTPException(400, "Uploaded file is empty")

    key_path.write_bytes(content)
    key_path.chmod(0o600)

    # Mark auth_type as key
    await _set_setting(session, f"{machine}_auth_type", "key")
    await session.commit()

    return {"success": True, "message": f"Key uploaded for {machine}"}
