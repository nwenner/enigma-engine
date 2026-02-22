from __future__ import annotations

"""
D2I stash file parser for Diablo 2 Resurrected.

Handles both the legacy format (SharedStashSoftCoreV2.d2i) and the Modern format
(ModernSharedStashSoftCoreV2.d2i, version==2).

Legacy layout (version != 2):
  [12-byte header: magic(4) + version(4) + num_pages(4)]
  [N pages, each: flags(4) + name_len(2) + name(N) + JM(2) + item_count(4) + item_bytes...]
  Each top-level item starts at its JM (0x4A 0x4D) byte marker.

Modern layout (version == 2):
  [64-byte header: magic(4) + version(4) + unknown(4) + gold(4) + page0_size(4) + zeros(44)]
  [5 pages, each preceded by 8 zero bytes (header provides them for page 0):]
    JM(2) + item_count(2, uint16 LE) + item_bytes...
  Items have NO JM prefix. Each item starts with first_byte=0x10 (identified flag at bit 4).
  Quality is at bit 111 from item start; unique_id/set_id at bit 117.
"""

import struct
from dataclasses import dataclass, field
from pathlib import Path


# ─── Bit I/O (LSB-first) ──────────────────────────────────────────────────────

class BitReader:
    """Reads LSB-first bits from a bytearray."""

    def __init__(self, data: bytes | bytearray, bit_offset: int = 0):
        self.data = data
        self.bit_offset = bit_offset

    def read(self, n: int) -> int:
        result = 0
        for i in range(n):
            byte_idx = self.bit_offset // 8
            bit_idx = self.bit_offset % 8
            if byte_idx < len(self.data):
                result |= ((self.data[byte_idx] >> bit_idx) & 1) << i
            self.bit_offset += 1
        return result

    def peek(self, n: int) -> int:
        saved = self.bit_offset
        val = self.read(n)
        self.bit_offset = saved
        return val

    def seek(self, bit_offset: int) -> None:
        self.bit_offset = bit_offset

    def tell(self) -> int:
        return self.bit_offset


# ─── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class D2IItem:
    byte_start: int        # byte offset within page's raw_bytes
    byte_end: int          # exclusive end (includes socketed sub-items for legacy)
    item_type: str         # 4-char code e.g. "uow " (empty string for Modern format)
    quality: int           # 4-bit: 5=set, 7=unique
    unique_id: int | None  # 12 bits when quality==7
    set_id: int | None     # 12 bits when quality==5
    item_level: int        # 7 bits (0 for Modern format)
    is_ethereal: bool
    socket_count: int      # filled sockets (0 for Modern format)
    is_simple: bool
    is_ear: bool


@dataclass
class D2IPage:
    flags: int
    name: str
    raw_bytes: bytearray   # item data bytes only (after JM + item_count header)
    item_count: int
    items: list[D2IItem] = field(default_factory=list)
    is_modern: bool = False


@dataclass
class D2IStash:
    magic: int
    version: int
    num_pages: int
    pages: list[D2IPage] = field(default_factory=list)
    is_modern: bool = False
    raw_header: bytes = field(default=b"")  # preserved 64-byte header for Modern format


# ─── Legacy parser constants ───────────────────────────────────────────────────

ITEM_MARKER = b"JM"

# Bit offsets within a single item's bitstream (from the start of its JM marker)
_BIT_IDENTIFIED    = 20
_BIT_SOCKETED_ITEM = 21
_BIT_EAR           = 28
_BIT_NEWBIE        = 29
_BIT_SIMPLE        = 35
_BIT_ETHEREAL      = 36
_BIT_PERSONALIZED  = 38
_BIT_RUNEWORD      = 42
_BIT_ITEM_TYPE     = 96       # 4 chars × 8 bits = 32 bits, ASCII
_BIT_SOCKET_COUNT  = 128      # 3 bits
_BIT_NID           = 131
_BIT_ILVL          = 163
_BIT_QUALITY       = 170
_BIT_QUALITY_DATA  = 174      # 12 bits


# ─── Modern format constants ───────────────────────────────────────────────────

MODERN_HEADER_SIZE = 64   # bytes
MODERN_PAGE_COUNT  = 5    # always 5 tabs in D2R shared stash

# Bit offsets for Modern format items (from item byte_start, NO JM prefix).
# Empirically confirmed via binary analysis of real stash files:
#   quality at bit 111, quality_data at bit 117 (after 2 flag bits).
_MOD_BIT_QUALITY = 111


# ─── Modern format helpers ────────────────────────────────────────────────────

def _is_modern_format(data: bytes) -> bool:
    """Return True if data is a Modern stash (version field == 2)."""
    if len(data) < 8:
        return False
    version = struct.unpack_from("<I", data, 4)[0]
    return version == 2


def _find_modern_page_jm_offsets(data: bytes) -> list[int]:
    """
    Locate page JM markers in a Modern stash file.
    Each valid page JM is preceded by at least 8 consecutive zero bytes
    (the 64-byte header ends in zeros, providing the separator for page 0).
    Returns up to MODERN_PAGE_COUNT offsets.
    """
    offsets: list[int] = []
    i = 8  # need at least 8 bytes before i to check for zeros
    while i < len(data) - 1 and len(offsets) < MODERN_PAGE_COUNT:
        if data[i] == 0x4A and data[i + 1] == 0x4D:
            zero_start = i - 8
            if zero_start >= 0 and all(data[zero_start + k] == 0 for k in range(8)):
                offsets.append(i)
                i += 2
                continue
        i += 1
    return offsets


def _find_item_starts_modern(raw: bytes | bytearray, item_count: int) -> list[int]:
    """
    Find item start byte positions in Modern format page data.
    Stash items reliably start with first_byte=0x10 (identified flag at bit 4)
    and fourth_byte=0x00. Returns up to item_count positions.
    """
    starts: list[int] = []
    i = 0
    while i + 3 < len(raw) and len(starts) < item_count:
        if raw[i] == 0x10 and raw[i + 3] == 0x00:
            starts.append(i)
            i += 4  # skip past matched bytes to avoid overlapping hits
        else:
            i += 1
    return starts


def _parse_single_item_modern(
    raw: bytes | bytearray,
    byte_start: int,
    byte_end: int,
) -> D2IItem:
    """
    Extract quality and quality_data from a Modern format item.
    Quality is at bit 111 from item start; quality_data at bit 117
    (after 2 flag bits: multiple_pictures + class_specific).
    """
    reader = BitReader(raw, byte_start * 8 + _MOD_BIT_QUALITY)
    quality = reader.read(4)

    # Two flag bits before quality_data
    mult_pics = reader.read(1)
    if mult_pics:
        reader.read(3)  # picture_id
    class_specific = reader.read(1)
    if class_specific:
        reader.read(11)  # class info

    unique_id: int | None = None
    set_id: int | None = None
    if quality == 5:    # set
        set_id = reader.read(12)
    elif quality == 7:  # unique
        unique_id = reader.read(12)

    return D2IItem(
        byte_start=byte_start,
        byte_end=byte_end,
        item_type="",
        quality=quality,
        unique_id=unique_id,
        set_id=set_id,
        item_level=0,
        is_ethereal=False,
        socket_count=0,
        is_simple=False,
        is_ear=False,
    )


def _parse_page_items_modern(raw: bytearray, item_count: int) -> list[D2IItem]:
    """Parse all items from a Modern format page's raw data."""
    if item_count == 0:
        return []

    starts = _find_item_starts_modern(raw, item_count)
    items: list[D2IItem] = []

    for i, byte_start in enumerate(starts):
        byte_end = starts[i + 1] if i + 1 < len(starts) else len(raw)
        try:
            item = _parse_single_item_modern(raw, byte_start, byte_end)
            items.append(item)
        except Exception:
            pass  # skip malformed items; grail hook is non-fatal anyway

    return items


# ─── Legacy item parsing ───────────────────────────────────────────────────────

def _parse_single_item(raw: bytes | bytearray, byte_start: int) -> tuple[D2IItem | None, int]:
    """
    Parse one legacy item starting at byte_start (the 'J' of 'JM').
    Returns (item, next_byte_start) or (None, byte_start+2) on error.
    """
    if byte_start + 2 > len(raw):
        return None, byte_start + 2

    if raw[byte_start] != 0x4A or raw[byte_start + 1] != 0x4D:
        return None, byte_start + 2

    reader = BitReader(raw, byte_start * 8)

    reader.read(16)  # JM marker

    reader.read(4)
    _identified = reader.read(1)
    reader.read(1)
    reader.read(6)
    is_ear = bool(reader.read(1))
    _newbie = reader.read(1)
    reader.read(5)
    is_simple = bool(reader.read(1))
    is_ethereal = bool(reader.read(1))
    reader.read(1)
    _personalized = reader.read(1)
    reader.read(1)
    _runeword = bool(reader.read(1))
    reader.read(1)
    reader.read(54)  # location/position/grid

    type_bytes = bytearray(4)
    for i in range(4):
        type_bytes[i] = reader.read(8)
    item_type = type_bytes.decode("ascii", errors="replace").rstrip("\x00")

    socket_count = reader.read(3)

    quality = 0
    unique_id = None
    set_id = None
    item_level = 0

    if not is_simple and not is_ear:
        _nid = reader.read(32)
        item_level = reader.read(7)
        quality = reader.read(4)

        _multiple_pictures = reader.read(1)
        if _multiple_pictures:
            reader.read(3)

        _class_specific = reader.read(1)
        if _class_specific:
            reader.read(11)

        if quality == 1:
            reader.read(3)
        elif quality == 2:
            pass
        elif quality == 3:
            reader.read(3)
        elif quality == 4:
            reader.read(11)
            reader.read(11)
        elif quality == 5:
            set_id = reader.read(12)
        elif quality == 6:
            reader.read(8)
            reader.read(8)
        elif quality == 7:
            unique_id = reader.read(12)
        elif quality == 8:
            reader.read(8)
            reader.read(8)

    item_byte_end = (reader.tell() + 7) // 8

    item = D2IItem(
        byte_start=byte_start,
        byte_end=item_byte_end,
        item_type=item_type,
        quality=quality,
        unique_id=unique_id,
        set_id=set_id,
        item_level=item_level,
        is_ethereal=is_ethereal,
        socket_count=socket_count,
        is_simple=is_simple,
        is_ear=is_ear,
    )
    return item, item_byte_end


def _parse_page_items(raw: bytearray, item_count: int) -> list[D2IItem]:
    """
    Parse items from a legacy page's raw bytes by scanning for JM markers.
    Consumes socket_count sub-item JM blocks after each top-level item.
    """
    items: list[D2IItem] = []

    if item_count == 0:
        return items

    jm_positions: list[int] = []
    pos = 0
    while pos < len(raw) - 1:
        if raw[pos] == 0x4A and raw[pos + 1] == 0x4D:
            jm_positions.append(pos)
            pos += 2
        else:
            pos += 1

    if not jm_positions:
        return items

    jm_idx = 0
    while jm_idx < len(jm_positions) and len(items) < item_count:
        byte_start = jm_positions[jm_idx]
        item, _ = _parse_single_item(raw, byte_start)
        jm_idx += 1

        if item is None:
            continue

        subs_consumed = 0
        while subs_consumed < item.socket_count and jm_idx < len(jm_positions):
            jm_idx += 1
            subs_consumed += 1

        if jm_idx < len(jm_positions):
            item.byte_end = jm_positions[jm_idx]
        else:
            item.byte_end = len(raw)

        items.append(item)

    return items


# ─── Page serialization helpers ───────────────────────────────────────────────

def remove_items_from_page(page: D2IPage, indices: list[int]) -> D2IPage:
    """Return a new D2IPage with items at `indices` removed."""
    if not indices:
        return page

    idx_set = set(indices)
    new_raw = bytearray()
    for i, item in enumerate(page.items):
        if i not in idx_set:
            new_raw.extend(page.raw_bytes[item.byte_start:item.byte_end])

    new_count = max(0, page.item_count - len(idx_set))

    if page.is_modern:
        # For Modern format, preserve the original byte buffer size.
        # D2R appears to rely on a consistent file size — shrinking the file causes
        # a crash-to-desktop on character launch. Zero-padding the unused space is
        # safe because D2R reads exactly item_count items and ignores what follows.
        original_size = len(page.raw_bytes)
        if len(new_raw) < original_size:
            new_raw += b"\x00" * (original_size - len(new_raw))
        new_page = D2IPage(
            flags=0,
            name="",
            raw_bytes=new_raw,
            item_count=new_count,
            items=[],
            is_modern=True,
        )
        if new_count > 0:
            new_page.items = _parse_page_items_modern(new_raw, new_count)
    else:
        new_page = D2IPage(
            flags=page.flags,
            name=page.name,
            raw_bytes=new_raw,
            item_count=new_count,
            items=[],
            is_modern=False,
        )
        new_page.items = _parse_page_items(new_raw, new_count)

    return new_page


def insert_item_into_page(page: D2IPage, item_bytes: bytes) -> D2IPage:
    """Append item bytes to end of page, increment item_count."""
    new_raw = bytearray(page.raw_bytes) + bytearray(item_bytes)
    new_count = page.item_count + 1

    new_page = D2IPage(
        flags=page.flags,
        name=page.name,
        raw_bytes=new_raw,
        item_count=new_count,
        items=[],
        is_modern=page.is_modern,
    )
    if page.is_modern:
        new_page.items = _parse_page_items_modern(new_raw, new_count)
    else:
        new_page.items = _parse_page_items(new_raw, new_count)
    return new_page


# ─── File I/O ─────────────────────────────────────────────────────────────────

def parse_d2i(path: Path) -> D2IStash:
    """Parse a .d2i stash file (legacy or Modern format)."""
    data = path.read_bytes()
    if len(data) < 12:
        raise ValueError(f"File too short: {len(data)} bytes")

    magic, version = struct.unpack_from("<II", data, 0)

    if _is_modern_format(data):
        return _parse_d2i_modern(data, magic, version)
    else:
        return _parse_d2i_legacy(data, magic, version)


def _parse_d2i_legacy(data: bytes, magic: int, version: int) -> D2IStash:
    """Parse legacy format stash."""
    num_pages = struct.unpack_from("<I", data, 8)[0]
    offset = 12

    stash = D2IStash(magic=magic, version=version, num_pages=num_pages)

    for page_idx in range(num_pages):
        if offset + 10 > len(data):
            raise ValueError(f"Truncated at page {page_idx}")

        flags = struct.unpack_from("<I", data, offset)[0]
        offset += 4

        name_len = struct.unpack_from("<H", data, offset)[0]
        offset += 2
        name = data[offset:offset + name_len].decode("utf-8", errors="replace")
        offset += name_len

        if data[offset:offset + 2] != b"JM":
            raise ValueError(
                f"Expected JM at page {page_idx}, offset {offset}, got {data[offset:offset+2]!r}"
            )
        offset += 2

        item_count = struct.unpack_from("<I", data, offset)[0]
        offset += 4

        raw_start = offset
        remaining = bytearray(data[raw_start:])
        items = _parse_page_items(remaining, item_count)

        if items:
            raw_end = items[-1].byte_end
        else:
            raw_end = 0

        raw_bytes = remaining[:raw_end]
        offset = raw_start + raw_end

        page = D2IPage(
            flags=flags,
            name=name,
            raw_bytes=bytearray(raw_bytes),
            item_count=item_count,
            items=items,
            is_modern=False,
        )
        stash.pages.append(page)

    return stash


def _parse_d2i_modern(data: bytes, magic: int, version: int) -> D2IStash:
    """Parse Modern format stash (version == 2)."""
    if len(data) < MODERN_HEADER_SIZE:
        raise ValueError(f"Modern stash too short: {len(data)} bytes")

    raw_header = bytes(data[:MODERN_HEADER_SIZE])
    stash = D2IStash(
        magic=magic,
        version=version,
        num_pages=MODERN_PAGE_COUNT,
        is_modern=True,
        raw_header=raw_header,
    )

    jm_offsets = _find_modern_page_jm_offsets(data)
    if len(jm_offsets) < MODERN_PAGE_COUNT:
        raise ValueError(
            f"Modern stash: expected {MODERN_PAGE_COUNT} pages, "
            f"found {len(jm_offsets)} (offsets={jm_offsets})"
        )

    for page_idx in range(MODERN_PAGE_COUNT):
        jm_off = jm_offsets[page_idx]
        if jm_off + 4 > len(data):
            raise ValueError(f"Truncated at Modern page {page_idx}")

        item_count = struct.unpack_from("<H", data, jm_off + 2)[0]
        data_start = jm_off + 4

        # data_end: before the 8-zero separator of the next page, or EOF for last page
        if page_idx + 1 < MODERN_PAGE_COUNT:
            data_end = jm_offsets[page_idx + 1] - 8
        else:
            data_end = len(data)

        raw_bytes = bytearray(data[data_start:data_end])
        items = _parse_page_items_modern(raw_bytes, item_count)

        page = D2IPage(
            flags=0,
            name="",
            raw_bytes=raw_bytes,
            item_count=item_count,
            items=items,
            is_modern=True,
        )
        stash.pages.append(page)

    return stash


def serialize_d2i(stash: D2IStash) -> bytes:
    """Reconstruct .d2i bytes from a D2IStash."""
    if stash.is_modern:
        return _serialize_d2i_modern(stash)
    else:
        return _serialize_d2i_legacy(stash)


def _serialize_d2i_legacy(stash: D2IStash) -> bytes:
    out = bytearray()
    out += struct.pack("<III", stash.magic, stash.version, stash.num_pages)
    for page in stash.pages:
        out += struct.pack("<I", page.flags)
        name_bytes = page.name.encode("utf-8")
        out += struct.pack("<H", len(name_bytes))
        out += name_bytes
        out += b"JM"
        out += struct.pack("<I", page.item_count)
        out += page.raw_bytes
    return bytes(out)


def _serialize_d2i_modern(stash: D2IStash) -> bytes:
    """
    Reconstruct Modern format stash bytes.
    Layout: 64-byte header + for each page: [8 zero separator (except page 0)] + JM + item_count(2) + raw_bytes.
    Page 0 gets its separator from the zeros at the end of the 64-byte header.
    """
    out = bytearray(stash.raw_header)  # 64 bytes, ends in zeros (provides separator for page 0)
    for page_idx, page in enumerate(stash.pages):
        if page_idx > 0:
            out += b"\x00" * 8  # 8-byte separator before pages 1-4
        out += b"JM"
        out += struct.pack("<H", page.item_count)
        out += page.raw_bytes
    return bytes(out)


# ─── Validation ───────────────────────────────────────────────────────────────

def validate_page_items(page: D2IPage) -> bool:
    """
    Verify that item byte ranges are consistent with raw_bytes length.
    Returns True if valid, False if there's a mismatch.
    """
    if not page.items:
        return True

    for item in page.items:
        if item.byte_start < 0 or item.byte_end > len(page.raw_bytes):
            return False
        if item.byte_start >= item.byte_end:
            return False

    sorted_items = sorted(page.items, key=lambda i: i.byte_start)
    for i in range(len(sorted_items) - 1):
        if sorted_items[i].byte_end > sorted_items[i + 1].byte_start:
            return False

    return True
