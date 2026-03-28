"""
Shared D2S binary utilities — checksum and any future low-level helpers
shared across demon_service.py and seed_service.py.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def _calculate_checksum(data: bytes) -> int:
    """D2S rotate-and-add checksum (checksum field must be zeroed before calling)."""
    checksum = 0
    for b in data:
        checksum = ((checksum << 1) | (checksum >> 31)) & 0xFFFFFFFF
        checksum = (checksum + b) & 0xFFFFFFFF
    return checksum
