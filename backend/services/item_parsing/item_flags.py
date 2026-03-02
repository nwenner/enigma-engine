"""
Item flag parsing for D2R Modern stash items.

Bits 0–52 of each item contain flags and location data.
Verified bit offsets (0-indexed from item byte start, LSB-first),
cross-referenced against dschu012/d2s TypeScript reference:

  bit 4  = is_identified    (always 1 for stash items → 0x10 first byte)
  bit 16 = is_ear           (byte 2 bit 0)
  bit 21 = is_simple        (byte 2 bit 5) — runes, gems, keys, etc.
  bit 22 = is_ethereal      (byte 2 bit 6)

Note: D2R Modern format shifted simple/ethereal 2 bits later vs legacy D2
(bits 19/20 in classic format, bits 21/22 in D2R Modern).
"""
from __future__ import annotations

from dataclasses import dataclass

# Bit offset where the Huffman type code starts (after all flag/location bits).
FLAGS_BIT_COUNT = 53


@dataclass
class ItemFlags:
    is_identified: bool
    is_ear: bool
    is_simple: bool
    is_ethereal: bool


def read_item_flags(data: bytes | bytearray, byte_start: int) -> ItemFlags:
    """
    Extract item flags from the fixed-position bits (0–52) of a Modern item.

    Uses direct byte indexing for performance rather than BitReader.
    """
    b0 = data[byte_start]     if byte_start < len(data) else 0
    b2 = data[byte_start + 2] if byte_start + 2 < len(data) else 0

    return ItemFlags(
        is_identified=bool((b0 >> 4) & 1),   # bit 4
        is_ear=bool(b2 & 1),                  # bit 16 (byte2 bit0)
        is_simple=bool((b2 >> 5) & 1),        # bit 21 (byte2 bit5)
        is_ethereal=bool((b2 >> 6) & 1),      # bit 22 (byte2 bit6)
    )
