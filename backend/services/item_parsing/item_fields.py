"""
Deterministic item field parsing for D2R Modern stash items.

Layout after the 53-bit flag block (starting at bit 53):
  Huffman type code (variable, 19–36 bits)
  if !simple_item && !is_ear:
    nr_of_items_in_sockets  (3 bits)
    item_id                 (32 bits)
    item_level              (7 bits)
    quality                 (4 bits)
    multiple_pictures       (1 bit) [+ pic_id(3) if set]
    class_specific          (1 bit) [+ cs_data(11) if set]
    [quality-specific data]
      q=1 low:      3 bits (quality prefix index)
      q=2 normal:   no data
      q=3 superior: 3 bits (file index)
      q=4 magic:    prefix_id(11) + has_suffix(1) + suffix_id(11) [always 23 bits]
      q=5 set:      set_id(12)
      q=6 rare:     name1(8) + name2(8) + 6 affix slots (1+11 bits each)
      q=7 unique:   unique_id(12)
      q=8 crafted:  same as rare

Quality enum (from dschu012/d2s TypeScript reference):
  Low=1, Normal=2, Superior=3, Magic=4, Set=5, Rare=6, Unique=7, Crafted=8
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from .bit_reader import BitReader
from .huffman import decode_item_type
from .item_flags import FLAGS_BIT_COUNT, ItemFlags
from .tables.item_categories import ARMOR_CODES, WEAPON_CODES, NODURABILITY_CODES, STACKABLE_CODES
from .tables.stat_widths import STAT_TABLE

log = logging.getLogger(__name__)

_PROP_SENTINEL = 0x1FF  # 9-bit sentinel marking end of property list

# Chained/dependent stats: when a lead stat is read, its dependent stats
# follow inline (value bits only, no 9-bit stat_id header).
# E.g., firemindam(48) is always followed by firemaxdam(49).
CHAINED_STATS: dict[int, list[int]] = {
    17: [18],         # item_maxdamage_percent → item_mindamage_percent
    48: [49],         # firemindam → firemaxdam
    50: [51],         # lightmindam → lightmaxdam
    52: [53],         # magicmindam → magicmaxdam
    54: [55, 56],     # coldmindam → coldmaxdam, coldlength
    57: [58, 59],     # poisonmindam → poisonmaxdam, poisonlength
}


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
    magic_prefix_id: int | None   # 11-bit magic prefix ID (quality==4 only)
    magic_suffix_id: int | None   # 11-bit magic suffix ID (quality==4 only)
    rare_name1: int           # 8-bit rare name word 1 ID (quality 6/8 only, else 0)
    rare_name2: int           # 8-bit rare name word 2 ID (quality 6/8 only, else 0)
    runeword_id: int | None   # 12-bit runeword ID (is_runeword only, else None)
    prop_bit_start: int       # absolute bit offset in data where property list starts (0 for simple/ear)


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
        reader.read(3)  # quality prefix index (low/inferior)
    elif quality == 3:
        reader.read(3)  # superior: file index
    elif quality == 4:
        # D2R format: prefix_id(11) + suffix_id(11) = 22 bits. No has_suffix flag.
        # Classic D2 used 23 bits (prefix + has_suffix_flag + suffix); D2R dropped the flag.
        # Source: d07RiV D2R format reference (case 4: skipbits(11); skipbits(11))
        prefix_id = reader.read(11)
        suffix_id = reader.read(11)
        magic_prefix_id = prefix_id if prefix_id else None
        magic_suffix_id = suffix_id if suffix_id else None
    elif quality in (6, 8):
        rare_name1 = reader.read(8)
        rare_name2 = reader.read(8)
        for _ in range(6):  # 3 prefix + 3 suffix slots
            if reader.read(1):
                reader.read(11)
    elif quality == 5:
        set_id = reader.read(12)
    elif quality == 7:
        unique_id = reader.read(12)
    # quality 2 (normal): no quality data bits

    return unique_id, set_id, magic_prefix_id, magic_suffix_id, rare_name1, rare_name2


def read_charm_stats(
    data: bytes | bytearray,
    prop_bit_start: int,
    item_end_bit: int,
) -> list[tuple[int, int, int]]:
    """
    Parse the property list starting at prop_bit_start, collecting
    (stat_id, param, display_val) tuples for charm prefix lookup.

    display_val = raw_bits - save_add (i.e. the in-game displayed value).
    Stops at the 0x1FF sentinel, on an unknown stat_id, or at item_end_bit.
    """
    reader = BitReader(data, prop_bit_start)
    result: list[tuple[int, int, int]] = []
    while reader.tell() + 9 <= item_end_bit:
        stat_id = reader.read(9)
        if stat_id == _PROP_SENTINEL:
            break
        entry = STAT_TABLE.get(stat_id)
        if entry is None:
            log.warning(
                "read_charm_stats: unknown stat_id=%d at bit %d; stopping property read",
                stat_id, reader.tell() - 9,
            )
            break  # unknown stat — cannot advance safely
        save_bits, save_add, save_param_bits = entry
        if reader.tell() + save_param_bits + save_bits > item_end_bit:
            break  # value bits would extend past item boundary
        param = reader.read(save_param_bits) if save_param_bits else 0
        raw_value = reader.read(save_bits) if save_bits else 0
        result.append((stat_id, param, raw_value - save_add))

        # Handle chained/dependent stats (value bits follow inline, no stat_id header)
        chained = CHAINED_STATS.get(stat_id)
        if chained:
            for dep_id in chained:
                dep_entry = STAT_TABLE.get(dep_id)
                if dep_entry is None:
                    break
                dep_bits, dep_add, dep_param_bits = dep_entry
                if reader.tell() + dep_param_bits + dep_bits > item_end_bit:
                    break
                dep_param = reader.read(dep_param_bits) if dep_param_bits else 0
                dep_raw = reader.read(dep_bits) if dep_bits else 0
                result.append((dep_id, dep_param, dep_raw - dep_add))
    return result


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
            runeword_id=None,
            prop_bit_start=0,
        )

    # Complex item fields
    socket_count = reader.read(3)
    item_id = reader.read(32)
    item_level = reader.read(7)
    quality = reader.read(4)

    # Multiple pictures flag — pic_id is 3 bits (same as Classic D2, NOT 11)
    if reader.read(1):  # multiple_pictures
        reader.read(3)  # pic_id

    # Class-specific flag
    class_specific = bool(reader.read(1))
    if class_specific:
        reader.read(11)  # class_data

    unique_id, set_id, magic_prefix_id, magic_suffix_id, rare_name1, rare_name2 = (
        _skip_quality_data(reader, quality, class_specific)
    )

    # Runeword fields: 12-bit runeword_id + 4-bit property_list_count
    runeword_id = None
    if flags.is_runeword:
        runeword_id = reader.read(12)
        reader.read(4)  # property_list_count (number of stat lists that follow)

    # ── Intermediate fields between quality data and property list ──────────
    # These depend on item category (armor/weapon/misc) and flags.
    code = item_type.strip()
    is_armor = code in ARMOR_CODES
    is_weapon = code in WEAPON_CODES
    has_durability = (is_armor or is_weapon) and code not in NODURABILITY_CODES

    # Prefix bit 1: always present (legacy HasRealmData, always 0 in D2R)
    reader.read(1)

    # Prefix bit 2: only for non-armor, non-weapon items (misc: charms, rings, etc.)
    if not is_armor and not is_weapon:
        reader.read(1)

    # Defense: 11 bits if armor
    if is_armor:
        reader.read(11)  # armorclass: display = raw - 10

    # Durability: max(8) + current(10 if max > 0)
    if has_durability:
        max_durability = reader.read(8)
        if max_durability > 0:
            reader.read(10)  # current durability

    # Quantity: 9 bits if stackable (rare for complex/identified items)
    if code in STACKABLE_CODES:
        reader.read(9)

    # Total sockets: 4 bits if IsSocketed flag is set
    if flags.is_socketed:
        reader.read(4)

    # Set item mask: 5 bits if quality == Set
    if quality == 5:
        reader.read(5)  # bitmask for active partial set bonuses

    prop_bit_start = reader.tell()

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
        runeword_id=runeword_id,
        prop_bit_start=prop_bit_start,
    )
