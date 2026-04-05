"""
generate_affixes.py — Generate MAGIC_PREFIXES and MAGIC_SUFFIXES tables from D2R data files.

Reads magicprefix.txt and magicsuffix.txt (tab-separated, from D2R extracted excel data),
then overwrites backend/services/item_parsing/tables/affixes.py with the generated dicts
while preserving the hand-curated CHARM_PREFIX_TABLE at the end of the file.

Usage:
    python3 scripts/generate_affixes.py
"""
from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data" / "tmp" / "excel"
AFFIXES_PY = REPO_ROOT / "backend" / "services" / "item_parsing" / "tables" / "affixes.py"

PREFIX_FILE = DATA_DIR / "magicprefix.txt"
SUFFIX_FILE = DATA_DIR / "magicsuffix.txt"


def parse_tsv(path: Path) -> dict[int, str]:
    """Parse a tab-separated D2R affix file into {id: name}.

    The first line is the header. Each subsequent data row gets an ID
    equal to its 1-based row index (first data row = ID 1). Rows with
    an empty Name column are skipped.
    """
    result: dict[int, str] = {}
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()

    # Skip header (line 0)
    for row_index, line in enumerate(lines[1:], start=1):
        cols = line.rstrip("\n").split("\t")
        name = cols[0].strip() if cols else ""
        if name:
            result[row_index] = name

    return result


def extract_charm_prefix_table(path: Path) -> str:
    """Read the existing affixes.py and extract everything from CHARM_PREFIX_TABLE onward."""
    text = path.read_text(encoding="utf-8")
    marker = "CHARM_PREFIX_TABLE"
    idx = text.find(marker)
    if idx == -1:
        raise RuntimeError(f"Could not find {marker} in {path}")
    return text[idx:]


def format_dict(name: str, type_hint: str, entries: dict[int, str]) -> str:
    """Format a dict as a multi-line Python assignment, one entry per line, sorted by key."""
    lines = [f"{name}: {type_hint} = {{"]
    for key in sorted(entries):
        lines.append(f"    {key}: {entries[key]!r},")
    lines.append("}")
    return "\n".join(lines)


def main() -> None:
    logging.basicConfig(level=logging.INFO)

    # Parse input files
    log.info("Parsing %s", PREFIX_FILE)
    prefixes = parse_tsv(PREFIX_FILE)
    log.info("Found %d prefixes with names", len(prefixes))

    log.info("Parsing %s", SUFFIX_FILE)
    suffixes = parse_tsv(SUFFIX_FILE)
    log.info("Found %d suffixes with names", len(suffixes))

    # Preserve the hand-curated CHARM_PREFIX_TABLE from the existing file
    log.info("Extracting CHARM_PREFIX_TABLE from %s", AFFIXES_PY)
    charm_table = extract_charm_prefix_table(AFFIXES_PY)

    # Build the output
    header = '"""\nMagic item prefix/suffix lookup tables and charm prefix lookup.\n\nMIGRATED from backend/services/_d2i_tables.py.\n"""\nfrom __future__ import annotations\n'

    prefixes_str = format_dict("MAGIC_PREFIXES", "dict[int, str]", prefixes)
    suffixes_str = format_dict("MAGIC_SUFFIXES", "dict[int, str]", suffixes)

    output = f"{header}\n{prefixes_str}\n\n{suffixes_str}\n\n{charm_table}"

    # Write the output
    log.info("Writing %s", AFFIXES_PY)
    AFFIXES_PY.write_text(output, encoding="utf-8")
    log.info("Done. Wrote %d prefix entries and %d suffix entries.", len(prefixes), len(suffixes))


if __name__ == "__main__":
    main()
