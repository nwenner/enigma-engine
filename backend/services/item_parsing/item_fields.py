"""
Deterministic item field parsing for D2R Modern stash items.

Layout after the 53-bit flag block (starting at bit 53):
  Huffman type code (variable, 19–36 bits)
  if !simple_item && !is_ear:
    nr_of_items_in_sockets  (3 bits)
    item_id                 (32 bits)
    item_level              (7 bits)
    quality                 (4 bits)
    multiple_pictures       (1 bit) [+ pic_id(11) if set]
    class_specific          (1 bit) [+ cs_data(11) if set]
    [quality-specific data]
      q=1 inferior: 3 bits (quality prefix index)
      q=3 magic:    prefix_id(11) + has_suffix(1) + suffix_id(11)
                    [non-class items always consume 23 bits]
      q=4 rare:     name1(8) + name2(8) + 6 affix slots (1+11 bits each)
      q=5 set:      set_id(12)
      q=6 crafted:  same as rare
      q=7 unique:   unique_id(12)
      q=8 tempered: 8+8 bits
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from .bit_reader import BitReader
from .huffman import decode_item_type
from .item_flags import FLAGS_BIT_COUNT, ItemFlags

log = logging.getLogger(__name__)


@dataclass
class ItemFields:
    """Parsed fields from a single Modern D2R stash item."""
    item_type: str            # 4-char code e.g. "cm1 "
    socket_count: int         # 0–7 (always 0 for simple items)
    item_id: int              # 32-bit ID
    item_level: int           # 7-bit ilvl
    quality: int              # 4-bit quality value
    unique_id: int | None     # 12-bit unique ID (quality==7 only)
    set_id: int | None        # 12-bit set ID (quality==5 only)
    magic_prefix_id: int | None   # 11-bit magic prefix ID (quality==3 only)
    magic_suffix_id: int | None   # 11-bit magic suffix ID (quality==3 only)
    rare_name1: int           # 8-bit rare name word 1 ID (quality 4/6 only, else 0)
    rare_name2: int           # 8-bit rare name word 2 ID (quality 4/6 only, else 0)


def _skip_quality_data(
    reader: BitReader,
    quality: int,
    class_specific: bool,
) -> tuple[int | None, int | None, int | None, int | None, int, int]:
    """
    Read quality-specific bits and return extracted IDs.

    Returns:
        (unique_id, set_id, magic_prefix_id, magic_suffix_id, rare_name1, rare_name2)
    """
    unique_id = None
    set_id = None
    magic_prefix_id = None
    magic_suffix_id = None
    rare_name1 = 0
    rare_name2 = 0

    if quality == 1:
        reader.read(3)  # quality prefix index (inferior)
    elif quality == 3:
        prefix_id = reader.read(11)
        has_suffix = reader.read(1)
        if has_suffix:
            suffix_id = reader.read(11)
        elif not class_specific:
            # Non-class items: always consume full 23 bits even when has_suffix=0
            reader.read(11)
            suffix_id = 0
        else:
            suffix_id = 0
        magic_prefix_id = prefix_id if prefix_id else None
        magic_suffix_id = suffix_id if suffix_id else None
    elif quality in (4, 6):
        rare_name1 = reader.read(8)
        rare_name2 = reader.read(8)
        for _ in range(6):  # 3 prefix + 3 suffix slots
            if reader.read(1):
                reader.read(11)
    elif quality == 5:
        set_id = reader.read(12)
    elif quality == 7:
        unique_id = reader.read(12)
    elif quality == 8:
        reader.read(8)
        reader.read(8)
    # quality 0 (normal) and 2 (superior): no quality data bits

    return unique_id, set_id, magic_prefix_id, magic_suffix_id, rare_name1, rare_name2


def read_item_fields(
    data: bytes | bytearray,
    flags: ItemFlags,
    byte_start: int,
) -> ItemFields:
    """
    Parse all item fields from a Modern D2R stash item using exact bit tracking.

    Starts at FLAGS_BIT_COUNT (bit 53) to decode the Huffman type code,
    then reads each subsequent field at its deterministic position.

    Raises ValueError if the Huffman type code cannot be decoded.
    """
    base_bit = byte_start * 8
    reader = BitReader(data, base_bit + FLAGS_BIT_COUNT)

    item_type = decode_item_type(reader)

    if flags.is_simple or flags.is_ear:
        return ItemFields(
            item_type=item_type,
            socket_count=0,
            item_id=0,
            item_level=0,
            quality=0,
            unique_id=None,
            set_id=None,
            magic_prefix_id=None,
            magic_suffix_id=None,
            rare_name1=0,
            rare_name2=0,
        )

    # Complex item fields
    socket_count = reader.read(3)
    item_id = reader.read(32)
    item_level = reader.read(7)
    quality = reader.read(4)

    # Multiple pictures flag (D2R expanded Classic D2's 3-bit pic_id to 11 bits)
    if reader.read(1):  # multiple_pictures
        reader.read(11)  # pic_id

    # Class-specific flag
    class_specific = bool(reader.read(1))
    if class_specific:
        reader.read(11)  # class_data

    unique_id, set_id, magic_prefix_id, magic_suffix_id, rare_name1, rare_name2 = (
        _skip_quality_data(reader, quality, class_specific)
    )

    return ItemFields(
        item_type=item_type,
        socket_count=socket_count,
        item_id=item_id,
        item_level=item_level,
        quality=quality,
        unique_id=unique_id,
        set_id=set_id,
        magic_prefix_id=magic_prefix_id,
        magic_suffix_id=magic_suffix_id,
        rare_name1=rare_name1,
        rare_name2=rare_name2,
    )
