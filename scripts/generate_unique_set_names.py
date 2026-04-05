#!/usr/bin/env python3
"""
Generate unique_set_names.py lookup tables from D2R data files.

Usage:
    python scripts/generate_unique_set_names.py

Reads:
    data/tmp/excel/uniqueitems.txt
    data/tmp/excel/setitems.txt

These are tab-separated files extracted from D2R's CASC archive
(data/global/excel/) using a tool like CascView.

Output:
    backend/services/item_parsing/tables/unique_set_names.py
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "tmp" / "excel"
OUTPUT_PATH = (
    PROJECT_ROOT
    / "backend"
    / "services"
    / "item_parsing"
    / "tables"
    / "unique_set_names.py"
)


def read_tsv(path: Path) -> list[dict]:
    if not path.exists():
        print(f"ERROR: {path} not found", file=sys.stderr)
        sys.exit(1)
    with path.open(encoding="utf-8", errors="replace") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def build_unique_names() -> dict[int, str]:
    names: dict[int, str] = {}
    for row in read_tsv(DATA_DIR / "uniqueitems.txt"):
        name = row.get("index", "").strip()
        if not name:
            continue
        disabled = row.get("disabled", "").strip()
        if disabled:
            continue
        uid = row.get("*ID", "").strip()
        if not uid:
            continue
        names[int(uid)] = name
    return dict(sorted(names.items()))


def build_set_names() -> dict[int, str]:
    names: dict[int, str] = {}
    for row in read_tsv(DATA_DIR / "setitems.txt"):
        name = row.get("index", "").strip()
        if not name:
            continue
        disabled = row.get("disabled", "").strip()
        if disabled:
            continue
        sid = row.get("*ID", "").strip()
        if not sid:
            continue
        names[int(sid)] = name
    return dict(sorted(names.items()))


def format_dict(name: str, type_hint: str, entries: dict[int, str]) -> str:
    lines = [f"{name}: {type_hint} = {{"]
    for key, value in entries.items():
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'    {key}: "{escaped}",')
    lines.append("}")
    return "\n".join(lines)


def main() -> None:
    unique_names = build_unique_names()
    set_names = build_set_names()

    print(f"Unique items: {len(unique_names)}")
    print(f"Set items:    {len(set_names)}")

    header = '''\
"""
Unique and set item name lookup tables.

Generated from D2R data files by scripts/generate_unique_set_names.py.
Maps unique_id/set_id → display name for use as fallback in item_names.resolve_name().
"""
from __future__ import annotations
'''

    unique_block = format_dict("UNIQUE_NAMES", "dict[int, str]", unique_names)
    set_block = format_dict("SET_NAMES", "dict[int, str]", set_names)

    output = f"{header}\n{unique_block}\n\n{set_block}\n"

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(output, encoding="utf-8")
    print(f"Written to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
