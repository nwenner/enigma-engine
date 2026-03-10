"""
Data models for the item_parsing package.

No logic here — just dataclass definitions.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ParsedItem:
    """A single parsed item from a Modern D2R stash page."""
    item_type: str            # 4-char Huffman-decoded code, e.g. "cm1 ", "rin "
    base_name: str | None     # Human-readable base type, e.g. "Small Charm"
    quality: int              # 0=normal, 1=inferior, 2=superior, 3=magic, 4=rare,
                              # 5=set, 6=crafted, 7=unique, 8=tempered
    unique_id: int | None     # 12-bit unique ID (quality==7 only)
    set_id: int | None        # 12-bit set ID (quality==5 only)
    magic_prefix_id: int | None   # 11-bit magic prefix ID (quality==3 only)
    magic_suffix_id: int | None   # 11-bit magic suffix ID (quality==3 only)
    rare_name: str | None     # Resolved rare/crafted name, e.g. "Death Knell"
    display_name: str         # Best display name for the item
    is_ethereal: bool
    is_simple: bool           # Simple item (rune/gem/etc.) — no complex fields
    is_ear: bool
    item_level: int           # 7-bit ilvl (0 for simple items)
    # Raw byte range within the containing page's raw_bytes
    byte_start: int           # byte offset within page raw_bytes
    byte_end: int             # exclusive end byte offset


@dataclass
class ParsedPage:
    """A single page (tab) from a Modern D2R stash."""
    items: list[ParsedItem]
    gold: int                 # per-page gold (always 0 in Modern stash; header has gold)
    raw_bytes: bytearray      # raw item bytes for this page
    # True top-level item count as recorded in the JM header. This is the
    # authoritative count for serialization — do NOT use len(items), which
    # only reflects what our byte-pattern scanner could detect.
    jm_item_count: int = 0


@dataclass
class ParsedStash:
    """A parsed Modern D2R shared stash file."""
    pages: list[ParsedPage]   # always 6 for Modern format (5 tabs + terminal)
    gold: int                 # header gold (bytes 12–15)
    hardcore: bool
    _raw_header: bytes        # preserved 64-byte header for round-trip serialize
    _raw_separators: list[bytes]  # preserved 64-byte separators (one per page > 0)
