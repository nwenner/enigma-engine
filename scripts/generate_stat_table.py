#!/usr/bin/env python3
"""
Generate STAT_TABLE in backend/services/item_parsing/tables/stat_widths.py
from D2R's itemstatcost.txt data file.

Input:  data/tmp/excel/itemstatcost.txt  (tab-separated, header on line 1)
Output: backend/services/item_parsing/tables/stat_widths.py

Usage:
    python3 scripts/generate_stat_table.py
"""
from __future__ import annotations

import csv
import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)

# Paths relative to project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT_PATH = PROJECT_ROOT / "data" / "tmp" / "excel" / "itemstatcost.txt"
OUTPUT_PATH = (
    PROJECT_ROOT
    / "backend"
    / "services"
    / "item_parsing"
    / "tables"
    / "stat_widths.py"
)

# ---------------------------------------------------------------------------
# Empirical D2R overrides — these take precedence over the data file values.
# Each entry: stat_id -> (save_bits, save_add, save_param_bits, comment)
# ---------------------------------------------------------------------------
OVERRIDES: dict[int, tuple[int, int, int, str]] = {
    # D2R empirical overrides — data file has wrong or missing Save Bits for these
    4:   (7,  0, 0, "statpts, D2R confirmed save_bits=7 empirically from Goldwrap parsing"),
    5:   (8,  0, 0, "newskills, D2R save_bits=8; appears on unique shields"),
    6:   (8,  0, 0, "hitpoints, D2R save_bits=8; appears on unique swords/shields"),
    8:   (9,  0, 0, "mana, D2R empirically determined"),
    10:  (1,  0, 0, "D2R stat 10, empirically determined header stat on some charms"),
    12:  (9,  0, 0, "D2R stat 12, empirically determined"),
    14:  (9,  0, 0, "D2R stat 14, empirically determined; appears after stat 30 on gloves"),
    15:  (3,  0, 0, "D2R stat 15, confirmed save_bits=3 (only 3 bits remain)"),
    30:  (3,  0, 0, "D2R stat 30, confirmed save_bits=3; header stat on belts/gloves/boots"),
    84:  (3,  0, 0, "D2R stat 84, empirically determined save_bits=3; header on some armor"),
    100: (8,  0, 0, "D2R stat 100, save_bits=8; appears on unique weapons"),
    103: (8,  0, 0, "D2R stat 103, save_bits=8; appears on rare armor items"),
    129: (8,  0, 0, "D2R stat 129, save_bits=8; appears on magic amulets"),
    130: (8,  0, 0, "D2R stat 130, save_bits=8; appears on rare helms"),
    131: (11, 0, 0, "D2R stat 131, CONFIRMED save_bits=11 (leads to sentinel)"),
    166: (8,  0, 0, "D2R stat 166, save_bits=8; appears on rare jewelry"),
    210: (8,  0, 0, "D2R stat 210, save_bits=8; appears on rare rings/jewelry"),
    353: (8,  0, 0, "D2R stat 353, save_bits=8; appears on unique boots"),
    385: (8, 237, 0, "mod extra gold from monsters"),
    457: (4,  0, 0, "Reign of the Warlock patch stat, confirmed save_bits=4"),
    # Stats with empty Save Bits in data file but empirically needed for item parsing
    64:  (12, 0, 0, "stamdrainmindam, empirical; data file has empty Save Bits"),
    65:  (7,  0, 0, "stamdrainmaxdam, empirical"),
    66:  (8,  0, 0, "stunlength, empirical"),
    69:  (8,  0, 0, "unknown stat 69, empirical"),
    101: (8,  0, 0, "unknown stat 101, empirical"),
    161: (8,  0, 0, "unknown stat 161, empirical"),
    169: (8,  0, 0, "unknown stat 169, empirical"),
    172: (2,  0, 0, "alignment, empirical"),
    173: (8,  0, 0, "target0, empirical"),
    174: (8,  0, 0, "target1, empirical"),
    175: (8,  0, 0, "unknown stat 175, empirical"),
    176: (8,  0, 0, "conversion_level, empirical"),
    177: (8,  0, 0, "conversion_maxhp, empirical"),
    178: (8,  0, 0, "unit_dooverlay, empirical"),
    182: (8,  0, 0, "armor_override_percent, empirical"),
    183: (8,  0, 0, "lasthitreactframe, empirical"),
    184: (8,  0, 0, "create_season, empirical"),
    211: (8,  0, 0, "ua_defeated counter, empirical"),
    212: (8,  0, 0, "unknown stat 212, empirical"),
    260: (14, 0, 0, "unknown D2R stat 260, empirical"),
    315: (8,  0, 0, "unknown stat 315, empirical"),
    316: (8,  0, 0, "burningmin, empirical"),
    317: (9,  0, 0, "burningmax, empirical"),
    318: (7,  0, 0, "progressive_damage, empirical"),
    319: (7,  0, 0, "progressive_steal, empirical"),
    320: (7,  0, 0, "progressive_other, empirical"),
    321: (7,  0, 0, "progressive_fire, empirical"),
    322: (7,  0, 0, "progressive_cold, empirical"),
    323: (7,  0, 0, "progressive_lightning, empirical"),
    325: (7,  0, 0, "progressive_tohit, empirical"),
    326: (5,  0, 0, "poison_count, empirical"),
    327: (8,  0, 0, "damage_framerate, empirical"),
    328: (8,  0, 0, "pierce_idx, empirical"),
    363: (8,  0, 0, "unknown stat 363, empirical"),
    364: (8,  0, 0, "customization_index, empirical"),
}

# ---------------------------------------------------------------------------
# Catch-all ranges for D2R additions not in the data file.
# Only applied for stat IDs that were NOT parsed from the data file.
# ---------------------------------------------------------------------------
CATCH_ALL_RANGES: list[tuple[range, tuple[int, int, int], str]] = [
    (range(368, 396), (8, 0, 0), "D2R additions 368-395"),
    (range(396, 397), (0, 0, 0), "unknown D2R flag"),
    (range(397, 424), (8, 0, 0), "D2R additions 397-423"),
    (range(424, 425), (0, 0, 0), "unknown D2R flag"),
    (range(425, 511), (8, 0, 0), "D2R additions 425-510"),
]


def _safe_int(value: str, default: int = 0) -> int:
    """Parse an integer from a string, returning default if empty or non-numeric."""
    value = value.strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def parse_itemstatcost(path: Path) -> dict[int, tuple[int, int, int, str]]:
    """
    Parse itemstatcost.txt and return a dict of stat_id -> (save_bits, save_add, save_param_bits, stat_name).

    Only includes rows where Save Bits is non-empty and numeric (>= 0).
    """
    entries: dict[int, tuple[int, int, int, str]] = {}

    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f, delimiter="\t")
        header = next(reader)

        # Find column indices by name for robustness
        col_stat = header.index("Stat")
        col_id = header.index("*ID")
        col_save_bits = header.index("Save Bits")
        col_save_add = header.index("Save Add")
        col_save_param = header.index("Save Param Bits")

        for row in reader:
            if len(row) <= max(col_stat, col_id, col_save_bits, col_save_add, col_save_param):
                continue

            stat_name = row[col_stat].strip()
            id_str = row[col_id].strip()
            save_bits_str = row[col_save_bits].strip()

            # Skip rows with no stat name or no ID
            if not stat_name or not id_str:
                continue

            # ID must be numeric
            try:
                stat_id = int(id_str)
            except ValueError:
                continue

            # Save Bits must be present and numeric (>= 0, including 0 for flag stats)
            if not save_bits_str:
                continue
            try:
                save_bits = int(save_bits_str)
            except ValueError:
                continue

            save_add = _safe_int(row[col_save_add])
            save_param_bits = _safe_int(row[col_save_param])

            entries[stat_id] = (save_bits, save_add, save_param_bits, stat_name)

    return entries


def build_stat_table(
    data_entries: dict[int, tuple[int, int, int, str]],
) -> list[tuple[int, int, int, int, str]]:
    """
    Build the final ordered list of (stat_id, save_bits, save_add, save_param_bits, comment).

    Order of precedence:
    1. Data file entries (base)
    2. Catch-all ranges for IDs not in the data file
    3. Empirical overrides (always win)
    """
    # Start with data file entries
    result: dict[int, tuple[int, int, int, str]] = {}
    for stat_id, (sb, sa, sp, name) in data_entries.items():
        result[stat_id] = (sb, sa, sp, name)

    # Add catch-all ranges for IDs NOT already present from data file
    for id_range, (sb, sa, sp), comment in CATCH_ALL_RANGES:
        for stat_id in id_range:
            if stat_id not in result:
                result[stat_id] = (sb, sa, sp, comment)

    # Apply empirical overrides (always win)
    for stat_id, (sb, sa, sp, comment) in OVERRIDES.items():
        # Preserve the stat name from data file if we have it, append override reason
        if stat_id in data_entries:
            original_name = data_entries[stat_id][3]
            result[stat_id] = (sb, sa, sp, f"{original_name} — D2R override: {comment}")
        else:
            result[stat_id] = (sb, sa, sp, f"D2R override: {comment}")

    # Convert to sorted list
    return [
        (stat_id, *vals)
        for stat_id, vals in sorted(result.items())
    ]


def format_entry(stat_id: int, save_bits: int, save_add: int, save_param_bits: int, comment: str) -> str:
    """Format a single STAT_TABLE entry as a Python dict line."""
    # Pad stat_id for alignment
    sid = f"{stat_id}:"
    # Format the tuple
    tup = f"({save_bits:>2}, {save_add:>3}, {save_param_bits:>2})"
    return f"    {sid:<6} {tup},   # {comment}"


def generate_output(entries: list[tuple[int, int, int, int, str]]) -> str:
    """Generate the complete stat_widths.py file content."""
    lines = [
        '"""',
        "Item stat bit-width table for property list skipping.",
        "",
        "STAT_WIDTHS maps stat_id → total bits to consume per stat entry",
        "  = save_param_bits + save_bits",
        "Used by skip_properties() to advance past the property list to the 0x1FF sentinel.",
        "",
        "Format of source data: stat_id → (save_bits, save_add, save_param_bits)",
        "STAT_WIDTHS pre-computes save_param_bits + save_bits for each entry.",
        "",
        "Auto-generated by scripts/generate_stat_table.py from data/tmp/excel/itemstatcost.txt",
        "with empirical D2R overrides applied on top.",
        '"""',
        "from __future__ import annotations",
        "",
        "# (save_bits, save_add, save_param_bits) for each stat_id.",
        "# Preserved for any code that needs raw widths or save_add.",
        "STAT_TABLE: dict[int, tuple[int, int, int]] = {",
    ]

    for stat_id, save_bits, save_add, save_param_bits, comment in entries:
        lines.append(format_entry(stat_id, save_bits, save_add, save_param_bits, comment))

    lines.append("}")
    lines.append("")
    lines.append("# Derived: stat_id → total bits to consume (save_param_bits + save_bits)")
    lines.append("STAT_WIDTHS: dict[int, int] = {")
    lines.append("    sid: (bits[2] + bits[0]) for sid, bits in STAT_TABLE.items()")
    lines.append("}")
    lines.append("")
    lines.append("# Stat IDs that are character/entity values — cannot legitimately appear in")
    lines.append("# an item property list. Seeing one signals a mis-detected quality offset.")
    lines.append("PROPERTY_BLOCKLIST: frozenset[int] = frozenset(")
    lines.append("    {4, 5, 6, 8, 10, 12, 13, 14, 15, 29, 30, 353, 354}")
    lines.append(")")
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if not INPUT_PATH.exists():
        log.error("Input file not found: %s", INPUT_PATH)
        sys.exit(1)

    log.info("Parsing %s", INPUT_PATH)
    data_entries = parse_itemstatcost(INPUT_PATH)
    log.info("Parsed %d stats from data file", len(data_entries))

    entries = build_stat_table(data_entries)
    log.info("Final table has %d entries (after overrides + catch-all ranges)", len(entries))

    output = generate_output(entries)

    OUTPUT_PATH.write_text(output, encoding="utf-8")
    log.info("Wrote %s (%d lines)", OUTPUT_PATH, output.count("\n") + 1)


if __name__ == "__main__":
    main()
