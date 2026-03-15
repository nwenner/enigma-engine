"""
Modern D2R stash file (.d2i) parser and serializer.

Modern layout (version == 2):
  [64-byte header: magic(4) + version(4) + unknown(4) + gold(4) + page0_size(4) + zeros(44)]
  [Page 0]: JM(2) + item_count(2, uint16 LE) + raw_item_bytes
  [Page 1+]: [64-byte separator] + JM(2) + item_count(2) + raw_item_bytes

  Separator format: magic(4)+version(4)+unk1(4)+gold=0(4)+size_field(4)+zeros(44)
    For non-terminal separators: size_field = 4 + len(raw_bytes) + 64
    Terminal separator (field at separator offset 20 != 0): preserved byte-for-byte.

Items in Modern format:
  - No JM prefix; each item starts with first_byte=0x10 (identified flag at bit 4)
  - Bits 0–52: flags (is_simple at bit 19, is_ethereal at bit 20)
  - Bits 53+: Huffman-encoded 4-char item type code
  - After type: sockets(3), id(32), level(7), quality(4), ... [if not simple/ear]
"""
from __future__ import annotations

import logging
import struct
from pathlib import Path

from .bit_reader import BitReader
from .item_flags import read_item_flags
from .item_fields import read_item_fields, read_charm_stats
from .item_names import base_name, resolve_name
from .tables.rare_names import RARE_NAMES
from .models import ParsedItem, ParsedPage, ParsedStash

log = logging.getLogger(__name__)

MODERN_HEADER_SIZE = 64   # bytes
MODERN_SEP_SIZE    = 64   # bytes (same as header)


# ─── Item start scanning ──────────────────────────────────────────────────────

def _find_item_starts(raw: bytes | bytearray, item_count: int) -> list[int]:
    """
    Locate item start byte positions in Modern format page data.

    Modern stash items reliably start with:
      first_byte = 0x10  (identified flag at bit 4)
      fourth_byte = 0x00  (normal items)
                 or 0x04  (runeword items — is_runeword flag at bit 26)

    Runeword items have bit 26 set (byte 3 bit 2 = 0x04).  Without this,
    runeword items (e.g. Enigma) are invisible and only their socketed runes
    are detected.

    After recording a match, the scanner advances by a skip distance to avoid
    false positives inside the flag block of the current item.

    The skip is adaptive based on whether the matched item is a "simple" item
    (runes, gems, keys — bit 21 of the flags block, byte 2 bit 5):

    - Simple items (is_simple=True): skip 10 bytes.  Simple items are 10–11
      bytes; their interior bytes never match the 0x10/0x00|0x04 pattern.

    - Non-simple items (is_simple=False): skip 15 bytes.  Certain non-simple
      18-byte items (e.g. ua4/ua5/pk3) have bytes at position +14 equal to
      0x10 and position +17 equal to 0x00, which matches the scanner pattern.
      Using skip=10 for these items causes the false positive at +14 to consume
      a budget slot, dropping the real next item from the result.  Skip=15
      clears the false positive.

    Returns up to item_count positions.
    """
    _SIMPLE_SKIP = 10    # minimum for 10-byte simple items (runes/gems)
    _COMPLEX_SKIP = 15   # clears false positive at byte +14 in non-simple items
    starts: list[int] = []
    i = 0
    while i + 3 < len(raw) and len(starts) < item_count:
        if raw[i] == 0x10 and raw[i + 3] in (0x00, 0x04):
            starts.append(i)
            # bit 21 of the flags block = byte 2 bit 5 = is_simple
            b2 = raw[i + 2] if i + 2 < len(raw) else 0
            is_simple = bool((b2 >> 5) & 1)
            i += _SIMPLE_SKIP if is_simple else _COMPLEX_SKIP
        else:
            i += 1
    return starts


# ─── Single item parsing ──────────────────────────────────────────────────────

def _parse_item(
    raw: bytes | bytearray,
    byte_start: int,
    byte_end: int,
    page_idx: int = 0,
) -> ParsedItem | None:
    """
    Parse one Modern format item. Returns None on parse failure.
    """
    try:
        flags = read_item_flags(raw, byte_start)
        fields = read_item_fields(raw, flags, byte_start)
    except Exception as exc:
        log.debug("item_parsing: failed to parse item at byte %d: %s", byte_start, exc)
        return None

    bname = base_name(fields.item_type)

    # For magic charms, bypass stored prefix_id (D2R uses different numbering)
    # and resolve the prefix name from the actual stat values instead.
    stat_list = None
    if (
        fields.quality == 4
        and fields.item_type.strip() in ("cm1", "cm2", "cm3")
        and fields.prop_bit_start
    ):
        stat_list = read_charm_stats(raw, fields.prop_bit_start, byte_end * 8)

    display_name, rare_name = resolve_name(
        item_type=fields.item_type,
        quality=fields.quality,
        is_simple=flags.is_simple,
        is_ear=flags.is_ear,
        unique_id=fields.unique_id,
        set_id=fields.set_id,
        magic_prefix_id=fields.magic_prefix_id,
        magic_suffix_id=fields.magic_suffix_id,
        rare_name1=fields.rare_name1,
        rare_name2=fields.rare_name2,
        stat_list=stat_list,
        is_runeword=flags.is_runeword,
        runeword_id=fields.runeword_id,
    )

    # Warn about rare/crafted name word IDs that are missing from RARE_NAMES.
    if fields.quality in (6, 8):
        for label, rid in (("rare_name1", fields.rare_name1), ("rare_name2", fields.rare_name2)):
            if rid and rid not in RARE_NAMES:
                log.warning(
                    "Unknown %s=%d for item '%s' at stash tab %d grid (%d,%d) — "
                    "please report this ID so the table can be updated.",
                    label, rid, display_name, page_idx + 1,
                    flags.position_x, flags.position_y,
                )

    # Warn when a magic/rare/crafted item fell back to base name + quality label.
    # This indicates incomplete prefix/suffix/rare-name lookup tables.
    # Unique (q=7) and set (q=5) are intentionally excluded: they always fall back at
    # parse time because catalog lookup requires a DB session and is done at the
    # service layer (stash_service.py, grail_service.py) — not a table gap.
    _FALLBACK_SUFFIXES = (" (magic)", " (rare)", " (crafted)")
    if fields.quality in (4, 6, 8) and any(display_name.endswith(s) for s in _FALLBACK_SUFFIXES):
        extra = ""
        if stat_list is not None:
            extra = f" charm_stats={stat_list[:6]}"
        log.warning(
            "Fallback name '%s' for %s item at stash tab %d grid (%d,%d) — "
            "quality=%d prefix_id=%s suffix_id=%s rare_name1=%s rare_name2=%s%s",
            display_name, fields.item_type.strip(), page_idx + 1,
            flags.position_x, flags.position_y,
            fields.quality, fields.magic_prefix_id, fields.magic_suffix_id,
            fields.rare_name1 or None, fields.rare_name2 or None, extra,
        )

    return ParsedItem(
        item_type=fields.item_type,
        base_name=bname,
        quality=fields.quality,
        unique_id=fields.unique_id,
        set_id=fields.set_id,
        magic_prefix_id=fields.magic_prefix_id,
        magic_suffix_id=fields.magic_suffix_id,
        rare_name=rare_name,
        display_name=display_name,
        is_ethereal=flags.is_ethereal,
        is_simple=flags.is_simple,
        is_ear=flags.is_ear,
        is_runeword=flags.is_runeword,
        runeword_id=fields.runeword_id,
        item_level=fields.item_level,
        byte_start=byte_start,
        byte_end=byte_end,
    )


# ─── Page item parsing ────────────────────────────────────────────────────────

def _parse_page_items(raw: bytearray, item_count: int, page_idx: int = 0) -> list[ParsedItem]:
    """Parse all items from a Modern format page's raw data."""
    if item_count == 0:
        return []

    starts = _find_item_starts(raw, item_count)
    items: list[ParsedItem] = []

    for i, byte_start in enumerate(starts):
        byte_end = starts[i + 1] if i + 1 < len(starts) else len(raw)
        item = _parse_item(raw, byte_start, byte_end, page_idx=page_idx)
        if item is not None:
            items.append(item)

    return items


# ─── Page manipulation helpers ────────────────────────────────────────────────

def remove_items_from_page(page: ParsedPage, indices: list[int]) -> ParsedPage:
    """Return a new ParsedPage with items at `indices` removed."""
    if not indices:
        return page

    idx_set = set(indices)
    new_raw = bytearray()
    for i, item in enumerate(page.items):
        if i not in idx_set:
            new_raw.extend(page.raw_bytes[item.byte_start : item.byte_end])

    new_jm_count = max(0, page.jm_item_count - len(idx_set))
    new_items = _parse_page_items(new_raw, new_jm_count)
    return ParsedPage(items=new_items, gold=page.gold, raw_bytes=new_raw, jm_item_count=new_jm_count)


def _set_item_grid_position(item_bytes: bytes, x: int, y: int) -> bytes:
    """
    Update the stash grid position (bits 42–49) of an item's byte block.

    Position bits in the Modern stash item header (LSB-first):
      pos_x: bits 42–45  (bits 2–5 of byte 5)
      pos_y: bits 46–49  (bits 6–7 of byte 5, bits 0–1 of byte 6)

    Bits 40–41 (byte 5 bits 0–1) are preserved — they belong to adjacent fields.
    This only touches the leading item (the stash-level item at offset 0).
    Socket sub-items that follow in the same byte block are left untouched.
    """
    if len(item_bytes) < 7:
        return item_bytes
    arr = bytearray(item_bytes)
    # byte 5: bits 0-1 preserved | bits 2-5 = pos_x | bits 6-7 = pos_y[1:0]
    arr[5] = (arr[5] & 0x03) | ((x & 0xF) << 2) | ((y & 0x3) << 6)
    # byte 6: bits 0-1 = pos_y[3:2] | bits 2-7 preserved
    arr[6] = (arr[6] & 0xFC) | ((y >> 2) & 0x3)
    return bytes(arr)


def insert_item_into_page(page: ParsedPage, item_bytes: bytes) -> ParsedPage:
    """Append item bytes to the end of a page, incrementing item count.

    Items are laid out in a 5-column grid to avoid visual overlap from large
    items (e.g. armor that spans 4 rows).  Layout per insertion index:

      index 0–4: row y=0, columns x=0,2,4,6,8
      index 5–9: row y=5, columns x=0,2,4,6,8

    Spacing of 2 columns and 5 rows ensures even 2×4 armor pieces don't
    cover adjacent reward slots.  Supports up to 10 simultaneous rewards.
    """
    idx = page.jm_item_count
    x = (idx % 5) * 2   # 0, 2, 4, 6, 8
    y = (idx // 5) * 5  # 0 for first 5 items, 5 for next 5
    item_bytes = _set_item_grid_position(item_bytes, x, y)
    new_raw = bytearray(page.raw_bytes) + bytearray(item_bytes)
    new_jm_count = page.jm_item_count + 1
    new_items = _parse_page_items(new_raw, new_jm_count)
    return ParsedPage(items=new_items, gold=page.gold, raw_bytes=new_raw, jm_item_count=new_jm_count)


def validate_page_items(page: ParsedPage) -> bool:
    """Verify item byte ranges are consistent with raw_bytes length."""
    if not page.items:
        return True
    for item in page.items:
        if item.byte_start < 0 or item.byte_end > len(page.raw_bytes):
            return False
        if item.byte_start >= item.byte_end:
            return False
    sorted_items = sorted(page.items, key=lambda it: it.byte_start)
    for i in range(len(sorted_items) - 1):
        if sorted_items[i].byte_end > sorted_items[i + 1].byte_start:
            return False
    return True


# ─── Page navigation ──────────────────────────────────────────────────────────

def _find_page_jm_offsets(data: bytes) -> list[int]:
    """
    Locate all page JM markers using forward navigation.

    Page 0 starts immediately after the 64-byte header. Each subsequent page
    is found by reading size_field from the preceding separator.
    """
    if len(data) < MODERN_HEADER_SIZE + 4:
        return []

    page0_size = struct.unpack_from("<I", data, 16)[0]
    offsets: list[int] = [MODERN_HEADER_SIZE]

    cur = MODERN_HEADER_SIZE + page0_size
    while cur + 1 < len(data):
        if data[cur : cur + 2] != b"JM":
            break
        offsets.append(cur)
        sep_start = cur - MODERN_SEP_SIZE
        if sep_start < 0:
            break
        slot_size = struct.unpack_from("<I", data, sep_start + 16)[0]
        if slot_size == 0:
            break
        cur += slot_size

    return offsets


# ─── Top-level parse / serialize ─────────────────────────────────────────────

def parse_stash(path_or_data: Path | bytes, hardcore: bool) -> ParsedStash:
    """
    Parse a Modern D2R stash file.

    Args:
        path_or_data: Path to .d2i file, or raw bytes.
        hardcore: Whether this is a HC stash (stored in ParsedStash).

    Raises:
        ValueError: If the file is not a Modern format stash (version != 2).
    """
    if isinstance(path_or_data, Path):
        data: bytes = path_or_data.read_bytes()
    else:
        data = path_or_data

    if len(data) < 8:
        raise ValueError(f"Stash too short: {len(data)} bytes")

    version = struct.unpack_from("<I", data, 4)[0]
    if version != 2:
        raise ValueError(
            f"Only Modern format (version=2) is supported; got version={version}"
        )

    if len(data) < MODERN_HEADER_SIZE:
        raise ValueError(f"Modern stash too short: {len(data)} bytes")

    raw_header = bytes(data[:MODERN_HEADER_SIZE])
    gold = struct.unpack_from("<I", data, 12)[0]

    jm_offsets = _find_page_jm_offsets(data)
    if not jm_offsets:
        raise ValueError("No pages found in Modern stash")

    pages: list[ParsedPage] = []
    raw_separators: list[bytes] = []

    for page_idx, jm_off in enumerate(jm_offsets):
        if jm_off + 4 > len(data):
            raise ValueError(f"Truncated at page {page_idx}")

        item_count = struct.unpack_from("<H", data, jm_off + 2)[0]
        data_start = jm_off + 4

        if page_idx + 1 < len(jm_offsets):
            data_end = jm_offsets[page_idx + 1] - MODERN_SEP_SIZE
        else:
            data_end = len(data)

        raw_bytes = bytearray(data[data_start:data_end])
        items = _parse_page_items(raw_bytes, item_count, page_idx=page_idx)

        if page_idx > 0:
            sep_start = jm_off - MODERN_SEP_SIZE
            raw_separators.append(bytes(data[sep_start : jm_off]))
        # page 0 has no preceding separator

        pages.append(ParsedPage(items=items, gold=0, raw_bytes=raw_bytes, jm_item_count=item_count))

    return ParsedStash(
        pages=pages,
        gold=gold,
        hardcore=hardcore,
        _raw_header=raw_header,
        _raw_separators=raw_separators,
    )


def serialize_stash(stash: ParsedStash) -> bytes:
    """
    Reconstruct Modern format .d2i bytes from a ParsedStash.

    Non-terminal separators: preserve stored bytes but update the size_field
    (offset 16–19 within the separator) if page content has changed.
    Terminal separator (field at offset 20 != 0): preserved byte-for-byte.
    """
    out = bytearray(stash._raw_header)
    # Write current gold into header bytes 12–15
    struct.pack_into("<I", out, 12, stash.gold)

    for page_idx, page in enumerate(stash.pages):
        if page_idx > 0:
            sep = bytearray(stash._raw_separators[page_idx - 1])
            terminal = len(sep) >= 24 and struct.unpack_from("<I", sep, 20)[0] != 0
            if terminal:
                out += sep
            else:
                # Preserve the stored separator bytes byte-for-byte, but update
                # the size_field (offset 16–19) to match current page content.
                # Slot size = JM(2) + count(2) + raw_bytes + trailing separator(64).
                slot_size = 4 + len(page.raw_bytes) + MODERN_SEP_SIZE
                struct.pack_into("<I", sep, 16, slot_size)
                out += sep

        out += b"JM"
        out += struct.pack("<H", page.jm_item_count)
        out += page.raw_bytes

    return bytes(out)
