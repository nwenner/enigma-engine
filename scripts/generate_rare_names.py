"""
generate_rare_names.py — Generate RARE_NAMES table from D2R data files.

Reads raresuffix.txt and rareprefix.txt (tab-separated, from D2R extracted excel data),
then overwrites backend/services/item_parsing/tables/rare_names.py with the generated dict
while preserving the legacy aliases and SKILLTAB_PREFIX_NAMES at the end of the file.

D2R rare name indexing:
  raresuffix entries come FIRST  (indices 1..155)
  rareprefix entries follow      (indices 156..201)

Usage:
    python3 scripts/generate_rare_names.py
"""
from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data" / "tmp" / "excel"
RARE_NAMES_PY = REPO_ROOT / "backend" / "services" / "item_parsing" / "tables" / "rare_names.py"

SUFFIX_FILE = DATA_DIR / "raresuffix.txt"
PREFIX_FILE = DATA_DIR / "rareprefix.txt"

RARESUFFIX_COUNT = 155  # Number of data rows in raresuffix.txt


def parse_raresuffix(path: Path) -> dict[int, str]:
    """Parse raresuffix.txt into {index: TitleCasedName}.

    Each data row gets index = row_index + 1 (1-based, starting at 1).
    Names are title-cased. Rows with empty names are skipped.
    """
    result: dict[int, str] = {}
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()

    # Skip header (line 0)
    for row_index, line in enumerate(lines[1:]):
        cols = line.rstrip("\n").split("\t")
        name = cols[0].strip() if cols else ""
        if not name:
            continue
        idx = row_index + 1  # 1-based
        result[idx] = name.title()

    return result


def parse_rareprefix(path: Path, offset: int) -> dict[int, str]:
    """Parse rareprefix.txt into {index: Name}.

    Each data row gets index = offset + row_index + 1 (continuing after
    raresuffix entries). Names are already title-cased in the source file,
    but we call .title() for consistency. Rows with empty names are skipped.
    """
    result: dict[int, str] = {}
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()

    # Skip header (line 0)
    for row_index, line in enumerate(lines[1:]):
        cols = line.rstrip("\n").split("\t")
        name = cols[0].strip() if cols else ""
        if not name:
            continue
        idx = offset + row_index + 1
        result[idx] = name.title()

    return result


def format_dict(names: dict[int, str]) -> str:
    """Format RARE_NAMES dict as multi-line Python, one entry per line."""
    lines = ["RARE_NAMES: dict[int, str] = {"]
    for key in sorted(names.keys()):
        lines.append(f'    {key}: "{names[key]}",')
    lines.append("}")
    return "\n".join(lines)


def generate() -> None:
    """Generate rare_names.py from D2R data files."""
    suffix_names = parse_raresuffix(SUFFIX_FILE)
    prefix_names = parse_rareprefix(PREFIX_FILE, offset=RARESUFFIX_COUNT)

    # Merge — prefix indices should not overlap with suffix indices
    all_names: dict[int, str] = {}
    all_names.update(suffix_names)
    all_names.update(prefix_names)

    log.info(
        "Parsed %d suffix entries (indices %d-%d) and %d prefix entries (indices %d-%d)",
        len(suffix_names),
        min(suffix_names.keys()),
        max(suffix_names.keys()),
        len(prefix_names),
        min(prefix_names.keys()),
        max(prefix_names.keys()),
    )

    dict_str = format_dict(all_names)

    output = f'''\
"""
Rare and crafted item name lookup tables.

D2R uses a single rare_names array for both name words — rare_name1 and
rare_name2 both index into RARE_NAMES.

Source: generated from D2R extracted data files (raresuffix.txt + rareprefix.txt)
by scripts/generate_rare_names.py.

raresuffix entries: indices 1..{RARESUFFIX_COUNT}
rareprefix entries: indices {RARESUFFIX_COUNT + 1}..{max(all_names.keys())}
"""
from __future__ import annotations

# Single combined table: both rare_name1 and rare_name2 index here.
# Index 0 is unused (null in source). Empty/blank entries are absent.
{dict_str}

# Legacy aliases kept for any code that still imports the old names.
RARE_PREFIXES = RARE_NAMES
RARE_SUFFIXES = RARE_NAMES

SKILLTAB_PREFIX_NAMES: dict[int, str] = {{
    0: "Combat Skills", 1: "Offensive Auras", 2: "Defensive Auras",
    3: "Bow and Crossbow Skills", 4: "Passive and Magic Skills", 5: "Javelin and Spear Skills",
    6: "Curses", 7: "Poison and Bone Spells", 8: "Necromancer Summoning Spells",
    9: "Fire Skills", 10: "Lightning Skills", 11: "Cold Skills",
    12: "Warcries", 13: "Combat Skills", 14: "Masteries",
    15: "Elemental Skills", 16: "Shape Shifting Skills", 17: "Summoning Skills",
    18: "Traps", 19: "Shadow Disciplines", 20: "Martial Arts",
}}
'''

    RARE_NAMES_PY.write_text(output, encoding="utf-8")
    log.info("Wrote %s (%d entries)", RARE_NAMES_PY, len(all_names))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    generate()
