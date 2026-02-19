from __future__ import annotations

"""
SSH/SFTP client manager using paramiko.

Note: Uses AutoAddPolicy (auto-accept host keys). This is acceptable for LAN
use where you control both endpoints. Not suitable for untrusted networks.
"""
import logging
from contextlib import contextmanager
from pathlib import PurePosixPath
from typing import Generator

import paramiko

log = logging.getLogger(__name__)

CONNECT_TIMEOUT = 10
BANNER_TIMEOUT = 10
AUTH_TIMEOUT = 10


class SSHConnectionError(Exception):
    pass


def _load_private_key(key_path: str, passphrase: str | None = None) -> paramiko.PKey:
    """Try RSA → Ed25519 → ECDSA key types in sequence."""
    path = key_path
    passphrase_bytes = passphrase.encode() if passphrase else None

    for key_class in (paramiko.RSAKey, paramiko.Ed25519Key, paramiko.ECDSAKey):
        try:
            return key_class.from_private_key_file(path, password=passphrase_bytes)
        except paramiko.SSHException:
            continue
        except Exception:
            continue

    raise SSHConnectionError(f"Could not load private key from {key_path} (tried RSA, Ed25519, ECDSA)")


def _make_client(
    host: str,
    port: int,
    username: str,
    password: str | None = None,
    key_path: str | None = None,
    key_passphrase: str | None = None,
) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    connect_kwargs: dict = dict(
        hostname=host,
        port=port,
        username=username,
        timeout=CONNECT_TIMEOUT,
        banner_timeout=BANNER_TIMEOUT,
        auth_timeout=AUTH_TIMEOUT,
        look_for_keys=False,
        allow_agent=False,
    )

    if key_path:
        connect_kwargs["pkey"] = _load_private_key(key_path, key_passphrase)
    elif password:
        connect_kwargs["password"] = password
    else:
        raise SSHConnectionError("Either password or key_path must be provided")

    try:
        client.connect(**connect_kwargs)
    except paramiko.AuthenticationException as e:
        raise SSHConnectionError(f"Authentication failed for {username}@{host}:{port}: {e}") from e
    except Exception as e:
        raise SSHConnectionError(f"Could not connect to {host}:{port}: {e}") from e

    return client


@contextmanager
def get_sftp(
    host: str,
    port: int,
    username: str,
    password: str | None = None,
    key_path: str | None = None,
    key_passphrase: str | None = None,
) -> Generator[tuple[paramiko.SSHClient, paramiko.SFTPClient], None, None]:
    """Context manager that yields (ssh_client, sftp_client) and cleans up on exit."""
    client = _make_client(host, port, username, password, key_path, key_passphrase)
    try:
        sftp = client.open_sftp()
        try:
            yield client, sftp
        finally:
            sftp.close()
    finally:
        client.close()


def normalize_path(path: str) -> str:
    """Normalize Windows-style backslashes to forward slashes for SFTP."""
    return path.replace("\\", "/")


def list_d2s_files(
    sftp: paramiko.SFTPClient,
    remote_dir: str,
) -> list[dict]:
    """
    List .d2s and .d2s.bak files in remote_dir.
    Returns list of dicts with keys: filename, path, size, modified_at (epoch float).
    """
    remote_dir = normalize_path(remote_dir)
    try:
        entries = sftp.listdir_attr(remote_dir)
    except FileNotFoundError:
        raise SSHConnectionError(f"Remote directory not found: {remote_dir}")

    results = []
    for entry in entries:
        name = entry.filename
        if name.endswith(".d2s") or name.endswith(".d2s.bak"):
            results.append(
                {
                    "filename": name,
                    "path": f"{remote_dir}/{name}",
                    "size": entry.st_size or 0,
                    "modified_at": entry.st_mtime or 0.0,
                }
            )

    return results


def list_all_files(
    sftp: paramiko.SFTPClient,
    remote_dir: str,
) -> list[dict]:
    """
    List all files in remote_dir (no extension filter).
    Returns list of dicts with keys: filename, path, size, modified_at (epoch float).
    """
    remote_dir = normalize_path(remote_dir)
    try:
        entries = sftp.listdir_attr(remote_dir)
    except FileNotFoundError:
        raise SSHConnectionError(f"Remote directory not found: {remote_dir}")

    return [
        {
            "filename": entry.filename,
            "path": f"{remote_dir}/{entry.filename}",
            "size": entry.st_size or 0,
            "modified_at": entry.st_mtime or 0.0,
        }
        for entry in entries
        if entry.filename and not entry.filename.startswith(".")
    ]


def check_d2r_running(ssh: paramiko.SSHClient, is_windows: bool) -> bool:
    """Return True if D2R.exe process is currently running on the remote machine."""
    if is_windows:
        cmd = 'tasklist /FI "IMAGENAME eq D2R.exe" /NH'
    else:
        cmd = "pgrep -x D2R.exe || pgrep -x D2R"

    _stdin, stdout, _stderr = ssh.exec_command(cmd)
    output = stdout.read().decode("utf-8", errors="replace").lower()

    if is_windows:
        return "d2r.exe" in output
    else:
        # pgrep returns exit code 0 if found
        return bool(output.strip())
