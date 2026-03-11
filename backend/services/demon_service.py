"""
Demon Vault service — store and restore a Warlock's bound demon.

The Warlock's bound demon is stored in the `lf` section appended to the .d2s file
(after the iron golem `kf` section). When no demon is bound, the section is 4 bytes:
  6c 66 00 00  ("lf" + has_demon=0)

When a demon is bound, the section is 96 bytes followed by a 24-byte `gf` (stats) block:
  6c 66 01 00 ...94 more bytes... | 67 66 ...22 more bytes...

Total demon payload from `lf` to EOF = 120 bytes.

This format was discovered empirically by diffing Tald.d2s snapshots (2026-03-11).
No public documentation exists for this section.
"""
from __future__ import annotations

import struct
import logging

log = logging.getLogger(__name__)

_LF = b"lf"  # 0x6c 0x66


def _find_lf_offset(d2s_data: bytes) -> int:
    """Return the byte offset of the 'lf' section, or -1 if not found."""
    return d2s_data.find(_LF)


def has_bound_demon(d2s_data: bytes) -> bool:
    """Return True if a demon is currently bound in this .d2s save."""
    offset = _find_lf_offset(d2s_data)
    if offset == -1 or offset + 3 > len(d2s_data):
        return False
    return d2s_data[offset + 2] == 1


def extract_demon_bytes(d2s_data: bytes) -> bytes | None:
    """
    Extract the full demon payload (lf section + gf stats section) from the .d2s.

    Returns the raw bytes from the `lf` marker to EOF, or None if no demon is bound.
    These bytes can be stored and later passed to restore_demon_to_d2s().
    """
    offset = _find_lf_offset(d2s_data)
    if offset == -1 or offset + 3 > len(d2s_data):
        return None
    if d2s_data[offset + 2] != 1:
        return None
    return d2s_data[offset:]


def restore_demon_to_d2s(d2s_data: bytes, demon_bytes: bytes) -> bytes:
    """
    Splice stored demon bytes back into a .d2s file, replacing the current lf section.

    Updates the filesize field (offset 8) and recalculates the checksum (offset 12).
    Raises ValueError if the lf section is not found.
    """
    offset = _find_lf_offset(d2s_data)
    if offset == -1:
        raise ValueError("lf section not found in .d2s — cannot restore demon")

    new_data = bytearray(d2s_data[:offset] + demon_bytes)

    # Update filesize at offset 8
    struct.pack_into("<I", new_data, 8, len(new_data))

    # Zero checksum field then recalculate
    struct.pack_into("<I", new_data, 12, 0)
    checksum = _calculate_checksum(bytes(new_data))
    struct.pack_into("<I", new_data, 12, checksum)

    log.info("Restored demon to .d2s: %d bytes → %d bytes", len(d2s_data), len(new_data))
    return bytes(new_data)


def _calculate_checksum(data: bytes) -> int:
    """D2S rotate-and-add checksum (checksum field must be zeroed before calling)."""
    checksum = 0
    for b in data:
        checksum = ((checksum << 1) | (checksum >> 31)) & 0xFFFFFFFF
        checksum = (checksum + b) & 0xFFFFFFFF
    return checksum
