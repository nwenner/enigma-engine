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
    is_runeword: bool  # bit 26 (byte 3 bit 2)
    is_socketed: bool   # bit 11 (byte 1 bit 3)
    position_x: int   # 4-bit grid column (bits 42–45)
    position_y: int   # 4-bit grid row    (bits 46–49)


def read_item_flags(data: bytes | bytearray, byte_start: int) -> ItemFlags:
    """
    Extract item flags from the fixed-position bits (0–52) of a Modern item.

    Uses direct byte indexing for performance rather than BitReader.

    D2R (v1.15+) bit layout within the 53-bit flags block:
      bit  4           = is_identified
      bit 16           = is_ear
      bit 21           = is_simple
      bit 22           = is_ethereal
      bit 26           = is_runeword
      bits 32-34       = version (3 bits)
      bits 35-37       = location_id (3 bits)
      bits 38-41       = equipped_id (4 bits)
      bits 42-45       = position_x  (4 bits)  ← byte 5 bits 2-5
      bits 46-49       = position_y  (4 bits)  ← byte 5 bits 6-7, byte 6 bits 0-1
      bits 50-52       = alt_position_id (3 bits)
    """
    b0 = data[byte_start]     if byte_start     < len(data) else 0
    b1 = data[byte_start + 1] if byte_start + 1 < len(data) else 0
    b2 = data[byte_start + 2] if byte_start + 2 < len(data) else 0
    b3 = data[byte_start + 3] if byte_start + 3 < len(data) else 0
    b5 = data[byte_start + 5] if byte_start + 5 < len(data) else 0
    b6 = data[byte_start + 6] if byte_start + 6 < len(data) else 0

    return ItemFlags(
        is_identified=bool((b0 >> 4) & 1),          # bit 4
        is_ear=bool(b2 & 1),                         # bit 16 (byte2 bit0)
        is_simple=bool((b2 >> 5) & 1),               # bit 21 (byte2 bit5)
        is_ethereal=bool((b2 >> 6) & 1),             # bit 22 (byte2 bit6)
        is_runeword=bool((b3 >> 2) & 1),             # bit 26 (byte3 bit2)
        is_socketed=bool((b1 >> 3) & 1),             # bit 11 (byte1 bit3)
        position_x=(b5 >> 2) & 0xF,                  # bits 42-45
        position_y=((b5 >> 6) & 0x3) | ((b6 & 0x3) << 2),  # bits 46-49
    )
