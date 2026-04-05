"""
Item display name resolution for D2R Modern stash items.

Resolves the best human-readable name for an item based on its type,
quality, and quality-specific IDs.
"""
from __future__ import annotations

import logging

from .tables.item_types import ITEM_TYPES
from .tables.affixes import MAGIC_PREFIXES, MAGIC_SUFFIXES, CHARM_PREFIX_TABLE
from .tables.rare_names import RARE_NAMES, SKILLTAB_PREFIX_NAMES
from .tables.runewords import RUNEWORD_NAMES
from .tables.unique_set_names import UNIQUE_NAMES, SET_NAMES

log = logging.getLogger(__name__)

# Quality name suffixes for fallback display
QUALITY_LABELS: dict[int, str] = {
    0: "",          # unused/unknown
    1: " (inferior)",
    2: "",          # normal: no suffix
    3: " (superior)",
    4: " (magic)",
    5: " (set)",
    6: " (rare)",
    7: " (unique)",
    8: " (crafted)",
}


def base_name(item_type: str) -> str | None:
    """Return the human-readable base name for a 4-char item type code, or None."""
    return ITEM_TYPES.get(item_type.strip())


def _magic_name(
    prefix_id: int | None,
    suffix_id: int | None,
    item_type: str,
) -> str | None:
    """
    Build "Prefix Base of Suffix" name for magic items.
    Returns None if neither prefix nor suffix is known.
    """
    bname = base_name(item_type)
    prefix = MAGIC_PREFIXES.get(prefix_id) if prefix_id else None
    suffix = MAGIC_SUFFIXES.get(suffix_id) if suffix_id else None

    parts: list[str] = []
    if prefix:
        parts.append(prefix)
    if bname:
        parts.append(bname)
    if suffix:
        parts.append(suffix)

    return " ".join(parts) if (prefix or suffix) and parts else None


def _charm_prefix_name(
    item_type: str,
    stat_list: list[tuple[int, int, int]],
) -> str | None:
    """
    Look up charm prefix name from stat list (bypasses stored prefix_id).

    For charms, Classic D2 and D2R use different magicprefix.txt row numbers,
    making stored prefix IDs unreliable. We match against actual stat values.
    """
    charm_itype_map = {"cm1": "scha", "cm2": "mcha", "cm3": "lcha"}
    itype = charm_itype_map.get(item_type.strip())
    if not itype:
        return None

    itype_table = CHARM_PREFIX_TABLE.get(itype, {})
    for stat_id, param, stored_val in stat_list:
        # Grand Charm skill-tab bonus: stat 188
        if stat_id == 188 and itype == "lcha":
            class_id = param >> 3
            tab = param & 7
            if tab <= 2:
                name = SKILLTAB_PREFIX_NAMES.get(class_id * 3 + tab)
                if name:
                    return name
            continue
        ranges = itype_table.get(stat_id)
        if not ranges:
            continue
        for stored_min, stored_max, name in ranges:
            if stored_min <= stored_val <= stored_max:
                return name
    return None


def _rare_name(rare_name1: int, rare_name2: int) -> str | None:
    """Build the combined rare/crafted name from two word IDs (D2R unified table)."""
    p = RARE_NAMES.get(rare_name1, "")
    s = RARE_NAMES.get(rare_name2, "")
    combined = f"{p} {s}".strip()
    return combined or None


def resolve_name(
    item_type: str,
    quality: int,
    is_simple: bool,
    is_ear: bool,
    unique_id: int | None = None,
    set_id: int | None = None,
    magic_prefix_id: int | None = None,
    magic_suffix_id: int | None = None,
    rare_name1: int = 0,
    rare_name2: int = 0,
    catalog_name: str | None = None,
    stat_list: list[tuple[int, int, int]] | None = None,
    is_runeword: bool = False,
    runeword_id: int | None = None,
) -> tuple[str, str | None]:
    """
    Resolve the display name and rare_name for an item.

    Returns (display_name, rare_name) where:
      - display_name: best available name (catalog > magic > rare > base > fallback)
      - rare_name: the raw rare/crafted word pair (None for non-rare items)

    If catalog_name is provided (from GrailCatalog lookup), it wins for unique/set.
    stat_list is used for charm prefix lookup.
    """
    bname = base_name(item_type)

    # Runeword: look up by runeword_id; log unknown IDs so the table can be extended
    if is_runeword:
        if runeword_id is not None:
            rw_name = RUNEWORD_NAMES.get(runeword_id)
            if rw_name:
                return rw_name, None
            log.warning(
                "Unknown runeword_id=%d for base item '%s' — "
                "add this ID to tables/runewords.py to get the proper name.",
                runeword_id, bname or item_type.strip(),
            )
        return (bname or item_type.strip()) + " (runeword)", None

    # Catalog name takes priority for unique/set
    if catalog_name:
        return catalog_name, None

    rare = None
    if quality == 4:
        # Magic: "Prefix Base of Suffix"
        # For charms, override stored prefix_id with stat-based lookup
        if stat_list and item_type.strip() in ("cm1", "cm2", "cm3"):
            charm_prefix = _charm_prefix_name(item_type, stat_list)
            if charm_prefix:
                magic_prefix_id = None  # use resolved name directly
                suffix = MAGIC_SUFFIXES.get(magic_suffix_id) if magic_suffix_id else None
                parts = [p for p in [charm_prefix, bname, suffix] if p]
                display = " ".join(parts)
                return display, None

        full = _magic_name(magic_prefix_id, magic_suffix_id, item_type)
        if full:
            return full, None
        # Fallback: base name + quality label
        fallback = (bname or item_type.strip()) + QUALITY_LABELS.get(quality, "")
        return fallback, None

    elif quality in (6, 8) and rare_name1:
        rare = _rare_name(rare_name1, rare_name2)
        if rare:
            return rare, rare
        # Fallback
        fallback = (bname or item_type.strip()) + QUALITY_LABELS.get(quality, "")
        return fallback, None

    elif quality == 7 and unique_id is not None:
        # Unique without catalog entry — try static table from D2R data files
        static_name = UNIQUE_NAMES.get(unique_id)
        if static_name:
            return static_name, None
        fallback = (bname or item_type.strip()) + " (unique)"
        return fallback, None

    elif quality == 5 and set_id is not None:
        # Set without catalog entry — try static table from D2R data files
        static_name = SET_NAMES.get(set_id)
        if static_name:
            return static_name, None
        fallback = (bname or item_type.strip()) + " (set)"
        return fallback, None

    elif bname:
        label = QUALITY_LABELS.get(quality, "")
        return bname + label, None

    else:
        # Absolute fallback
        return item_type.strip() + QUALITY_LABELS.get(quality, ""), None
