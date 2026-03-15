from __future__ import annotations

"""
Parse a single D2R Modern item from raw bytes (byte_start=0).

Works for:
  - Hero Editor single-item .d2i exports (raw item bytes, no header)
  - Individual item blobs extracted from a stash page

No FastAPI or SQLAlchemy dependency — safe to import anywhere.
"""
import logging

log = logging.getLogger(__name__)

QUALITY_NAMES: dict[int, str] = {
    1: "inferior", 2: "normal", 3: "superior", 4: "magic",
    5: "set", 6: "rare", 7: "unique", 8: "crafted", 9: "tempered",
}


def parse_item_bytes(raw: bytes) -> dict:
    """
    Parse raw item bytes starting at offset 0.

    Returns a dict with:
      item_name, item_code, quality, quality_name, item_level,
      is_ethereal, valid, error
    """
    try:
        from backend.services.item_parsing.item_flags import read_item_flags
        from backend.services.item_parsing.item_fields import read_item_fields
        from backend.services.item_parsing.item_names import resolve_name, base_name as _base_name

        flags = read_item_flags(raw, byte_start=0)
        fields = read_item_fields(raw, flags, byte_start=0)
        display_name, _ = resolve_name(
            fields.item_type, fields.quality, flags.is_simple, flags.is_ear,
            fields.unique_id, fields.set_id,
            fields.magic_prefix_id, fields.magic_suffix_id,
            fields.rare_name1, fields.rare_name2,
            is_runeword=flags.is_runeword,
            runeword_id=fields.runeword_id,
        )
        b_name = _base_name(fields.item_type)

        return {
            "item_name": display_name or b_name,
            "item_code": fields.item_type.strip() if fields.item_type else None,
            "unique_id": fields.unique_id,   # needed for GrailCatalog name lookup (quality=7)
            "set_id": fields.set_id,         # needed for GrailCatalog name lookup (quality=5)
            "quality": fields.quality,
            "quality_name": QUALITY_NAMES.get(fields.quality, "unknown"),
            "item_level": fields.item_level,
            "is_ethereal": flags.is_ethereal,
            "is_runeword": flags.is_runeword,
            "valid": True,
            "error": None,
        }
    except Exception as e:
        log.warning("Item parse error: %s", e)
        return {
            "item_name": None, "item_code": None, "unique_id": None, "set_id": None, "quality": None,
            "quality_name": None, "item_level": None, "is_ethereal": False,
            "valid": False, "error": str(e),
        }
