#!/usr/bin/env python3
"""
Generate grail_catalog.json from D2R data files.

Usage:
    python scripts/generate_grail_catalog.py --data-dir /path/to/d2r/excel

The --data-dir should contain:
    uniqueitems.txt
    setitems.txt

These are the tab-separated files extracted from D2R's CASC archive
(data/global/excel/) using a tool like CascView.

Output: grail_catalog.json in the current directory (or --output path).
"""

import argparse
import csv
import json
import sys
from pathlib import Path


def read_tsv(path: Path) -> list[dict]:
    if not path.exists():
        print(f"ERROR: {path} not found", file=sys.stderr)
        sys.exit(1)
    with path.open(encoding="utf-8", errors="replace") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def generate_uniques(data_dir: Path) -> list[dict]:
    items = []
    for row in read_tsv(data_dir / "uniqueitems.txt"):
        name = row.get("index", "").strip()
        if not name:
            continue
        disabled = row.get("disabled", "").strip()
        if disabled and disabled != "0":
            continue
        uid = row.get("*ID", "").strip()
        if not uid:
            continue
        code = row.get("code", "").strip()
        base = row.get("*ItemName", "").strip() or code
        items.append({
            "item_code": code.ljust(4),
            "name": name,
            "base_item": base,
            "quality": "unique",
            "unique_id": int(uid),
            "set_id": None,
            "set_name": None,
            "sort_order": int(uid),
        })
    return items


def generate_sets(data_dir: Path) -> list[dict]:
    items = []
    for row in read_tsv(data_dir / "setitems.txt"):
        name = row.get("index", "").strip()
        if not name:
            continue
        disabled = row.get("disabled", "").strip()
        if disabled and disabled != "0":
            continue
        sid = row.get("*ID", "").strip()
        if not sid:
            continue
        code = row.get("item", "").strip()
        base = row.get("*ItemName", "").strip() or code
        set_name = row.get("set", "").strip() or None
        items.append({
            "item_code": code.ljust(4),
            "name": name,
            "base_item": base,
            "quality": "set",
            "unique_id": None,
            "set_id": int(sid),
            "set_name": set_name,
            "sort_order": int(sid),
        })
    return items


def main():
    parser = argparse.ArgumentParser(description="Generate grail_catalog.json from D2R data files")
    parser.add_argument("--data-dir", required=True, help="Directory containing uniqueitems.txt and setitems.txt")
    parser.add_argument("--output", default="grail_catalog.json", help="Output path (default: grail_catalog.json)")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.is_dir():
        print(f"ERROR: {data_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    uniques = generate_uniques(data_dir)
    sets = generate_sets(data_dir)
    catalog = uniques + sets

    print(f"Uniques: {len(uniques)}, Set items: {len(sets)}, Total: {len(catalog)}")

    output = Path(args.output)
    output.write_text(json.dumps(catalog, indent=2, ensure_ascii=False))
    print(f"Written to {output}")


if __name__ == "__main__":
    main()
