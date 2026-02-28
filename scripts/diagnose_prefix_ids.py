"""
Diagnose magic prefix/suffix ID numbering in D2R vs Classic D2.

The stored prefix_id in .d2i save files may use a different numbering than
D2R's current magicprefix.txt row numbers (line_number - 1).

This script checks three hypotheses:
  A) Stored ID = D2R line_number - 1 (all rows including version=100)
  B) Stored ID = Classic-only row index: only version=0 rows, numbered 1..N
  C) Stored ID = some other scheme (group number, etc.)

For each hypothesis, prints what ID 167 maps to, and where "Rainbow" appears.

Usage: python scripts/diagnose_prefix_ids.py
"""

import csv
import sys
from pathlib import Path

EXCEL = Path("data/tmp/excel")
PREFIX_FILE = EXCEL / "magicprefix.txt"
SUFFIX_FILE = EXCEL / "magicsuffix.txt"

KNOWN_BAD = {
    # stored_id: (wrong_name, expected_name)
    167: ("Scarlet", "Rainbow"),
}


def load_table(path: Path):
    rows = []
    with open(path, encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            rows.append(row)
    return rows


def scheme_a(rows):
    """ID = position in all rows (1-indexed, including blank row 1)."""
    return {i + 1: row.get("Name", "") for i, row in enumerate(rows)}


def scheme_b(rows):
    """ID = position among version=0 rows only (1-indexed)."""
    result = {}
    n = 0
    for row in rows:
        if row.get("version", "").strip() == "0":
            n += 1
            result[n] = row.get("Name", "")
    return result


def scheme_c(rows):
    """ID = absolute line number in file minus 1 (header = line 1)."""
    # This is identical to scheme_a since DictReader already skips the header
    # Row 0 in rows[] = file line 2 → ID = 2-1 = 1
    return {i + 2: row.get("Name", "") for i, row in enumerate(rows)}


def analyze(label, table, known_bad):
    print(f"\n=== {label} ===")
    for stored_id, (wrong, expected) in known_bad.items():
        got = table.get(stored_id, "<missing>")
        ok = "✓" if got == expected else "✗"
        print(f"  ID {stored_id}: got={got!r}  expected={expected!r}  {ok}")
    # Where does "Rainbow" appear?
    rainbow_ids = [k for k, v in table.items() if "Rainbow" in v]
    print(f"  'Rainbow' found at IDs: {rainbow_ids[:10]}")
    # What is at the first few IDs
    print(f"  ID 1={table.get(1)!r}  ID 2={table.get(2)!r}  ID 3={table.get(3)!r}")


def main():
    if not PREFIX_FILE.exists():
        print(f"ERROR: {PREFIX_FILE} not found", file=sys.stderr)
        sys.exit(1)

    rows = load_table(PREFIX_FILE)
    print(f"Loaded {len(rows)} rows from {PREFIX_FILE.name}")
    print(f"Rows with version=0: {sum(1 for r in rows if r.get('version','').strip()=='0')}")
    print(f"Rows with version=100: {sum(1 for r in rows if r.get('version','').strip()=='100')}")

    a = scheme_a(rows)
    b = scheme_b(rows)
    c = scheme_c(rows)

    analyze("Scheme A: 1-indexed (all rows)", a, KNOWN_BAD)
    analyze("Scheme B: version=0 rows only, 1-indexed", b, KNOWN_BAD)
    analyze("Scheme C: line_number-1 (header=1)", c, KNOWN_BAD)

    # Also check what the all-rows Rainbow entries look like:
    print("\n=== Raw Rainbow entries in magicprefix.txt ===")
    for i, row in enumerate(rows):
        if "Rainbow" in row.get("Name", ""):
            line_num = i + 2  # +1 for 1-indexing, +1 for header line
            print(f"  line {line_num} (1-idx pos {i+1}): "
                  f"version={row.get('version')}  "
                  f"itype1={row.get('itype1')}  "
                  f"mod1code={row.get('mod1code')}  "
                  f"group={row.get('group')}")

    # Print entries around ID 167 in all-rows scheme
    print("\n=== All-rows entries around ID 167 (line 167-170) ===")
    for i, row in enumerate(rows):
        pos = i + 1  # 1-indexed position in rows[] (not file line)
        if 165 <= pos <= 172:
            print(f"  pos={pos} version={row.get('version')} "
                  f"name={row.get('Name')!r} "
                  f"group={row.get('group')} "
                  f"mod1code={row.get('mod1code')}")


if __name__ == "__main__":
    main()
