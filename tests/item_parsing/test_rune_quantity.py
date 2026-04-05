from __future__ import annotations

"""
Unit tests for rune quantity parsing in backend/services/item_parsing/stash_format.py.

Coverage:
  _read_simple_item_quantity  → skips 2 bits then reads 8-bit quantity; El rune → 11
  _parse_page_items           → quantity stays 1 when no rune section present
  _parse_page_items           → quantity read when rune section marker present; El → 11
  _parse_page_items           → last item byte_end capped at rune section marker offset
  ParsedItem.quantity default → non-simple items always have quantity == 1 (default)

Calibrated 2026-04-04 against user-confirmed ground truth:
  El=11, Eth=24, Thul=14, Mal=2, Pul=1, Gul=1, Ohm=1

Bit layout after Huffman type code (rune-tab simple items only):
  +0:   socket_count  (1 bit, always 0)
  +1:   unknown_flag  (1 bit, always 1)
  +2-9: quantity      (8 bits) ← real stack count
"""

import pytest

from backend.services.item_parsing.stash_format import (
    _parse_page_items,
    _read_simple_item_quantity,
)
from backend.services.item_parsing.models import ParsedItem

# ---------------------------------------------------------------------------
# Known-good El rune bytes from a real backup.
# Bytes:  10 00 A0 00 05 2C F4 7C 7F 72 01
# item_type = "r01 " (El Rune), is_simple=True (byte2 bit5 = 1 → 0xA0 >> 5 & 1)
# 8-bit quantity field immediately after Huffman type = 46
# ---------------------------------------------------------------------------
EL_RUNE_BYTES = bytes([0x10, 0x00, 0xA0, 0x00, 0x05, 0x2C, 0xF4, 0x7C, 0x7F, 0x72, 0x01])
_RUNE_MARKER = bytes([0x55, 0xAA, 0x55, 0xAA])


# ─── Test 1: _read_simple_item_quantity direct call ──────────────────────────

def test_read_simple_item_quantity_el_rune() -> None:
    """
    Calling _read_simple_item_quantity on the known El rune byte sequence
    must return 11 — the 8 bits at offset +2 after the Huffman "r01 " type code
    (skipping 1 socket_count bit + 1 unknown_flag bit first).

    Calibrated against user ground truth 2026-04-04: El = 11.
    """
    raw = EL_RUNE_BYTES
    result = _read_simple_item_quantity(raw, byte_start=0, byte_end=len(raw))
    assert result == 11


# ─── Test 2: no rune section → quantity stays at default 1 ───────────────────

def test_parse_page_items_without_rune_section_quantity_is_1() -> None:
    """
    A page with no 55 AA 55 AA marker must leave quantity == 1 on all items,
    regardless of whether the item is simple.
    """
    raw = bytearray(EL_RUNE_BYTES)
    items = _parse_page_items(raw, item_count=1)

    assert len(items) == 1
    assert items[0].quantity == 1


# ─── Test 3: rune section present → quantity read for simple items ────────────

def test_parse_page_items_with_rune_section_reads_quantity() -> None:
    """
    When the rune section marker (55 AA 55 AA) follows the items on a page,
    _parse_page_items must call _read_simple_item_quantity for each simple item
    and store the result in item.quantity.

    El rune bytes are known to contain quantity=11 (at bit offset +2 after type code).
    Calibrated against user ground truth 2026-04-04.
    """
    # Build raw: El rune item + rune section marker + enough padding to be ignored
    padding = bytes(64)  # arbitrary trailing bytes beyond the marker
    raw = bytearray(EL_RUNE_BYTES + _RUNE_MARKER + padding)

    items = _parse_page_items(raw, item_count=1)

    assert len(items) == 1
    assert items[0].quantity == 11


# ─── Test 4: last item byte_end capped at rune section start ─────────────────

def test_byte_end_capped_at_rune_section() -> None:
    """
    When a rune section follows the items, the last (and only) item's byte_end
    must be capped at the rune section marker offset — not at len(raw).

    El rune is 11 bytes; the marker starts at offset 11, so byte_end must be 11.
    """
    padding = bytes(64)
    raw = bytearray(EL_RUNE_BYTES + _RUNE_MARKER + padding)
    expected_marker_offset = len(EL_RUNE_BYTES)  # == 11

    items = _parse_page_items(raw, item_count=1)

    assert len(items) == 1
    assert items[0].byte_end == expected_marker_offset, (
        f"byte_end={items[0].byte_end} but expected {expected_marker_offset} "
        f"(rune section marker offset)"
    )
    # Sanity: must be less than the total raw length
    assert items[0].byte_end < len(raw)


# ─── Test 5: non-simple items retain quantity == 1 even on rune-section pages ─

def test_non_simple_item_quantity_unaffected() -> None:
    """
    The quantity field in ParsedItem defaults to 1.  _parse_page_items only
    overwrites it when has_rune_section=True AND item.is_simple=True.

    A non-simple ParsedItem must always expose quantity == 1 regardless of the
    page layout.  This test verifies the dataclass default and confirms the
    conditional guard in _parse_page_items.
    """
    # Directly instantiate a non-simple ParsedItem to confirm the default.
    non_simple_item = ParsedItem(
        item_type="rin ",
        base_name="Ring",
        quality=7,
        unique_id=None,
        set_id=None,
        magic_prefix_id=None,
        magic_suffix_id=None,
        rare_name=None,
        display_name="Ring",
        is_ethereal=False,
        is_simple=False,  # key: non-simple items are never quantity-patched
        is_ear=False,
        is_runeword=False,
        runeword_id=None,
        item_level=0,
        byte_start=0,
        byte_end=11,
    )
    assert non_simple_item.quantity == 1

    # Additionally, verify at the _parse_page_items level: if we present raw bytes
    # where the scanner finds a non-simple-flagged item (is_simple bit = 0, i.e.
    # byte2 bit5 = 0) on a page with a rune section, the resulting parsed items
    # must all have quantity == 1.
    #
    # We use a copy of the El rune bytes with the is_simple bit cleared (byte 2,
    # bit 5).  This makes the scanner classify it as non-simple (skip=15).
    # _parse_item will attempt complex parsing and may return None; if it does
    # return an item, quantity must be 1 because the is_simple guard blocks the
    # quantity read.
    non_simple_raw = bytearray(EL_RUNE_BYTES)
    non_simple_raw[2] = non_simple_raw[2] & ~(1 << 5)  # clear is_simple bit

    padding = bytes(64)
    raw = bytearray(non_simple_raw + _RUNE_MARKER + padding)
    items = _parse_page_items(raw, item_count=1)

    # Whether or not the parse succeeds, no item may have quantity != 1
    for item in items:
        assert item.quantity == 1, (
            f"Non-simple item unexpectedly got quantity={item.quantity}"
        )
