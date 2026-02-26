#!/usr/bin/env python3
"""
Create the actual modified file that deposit would create, save it, and compare.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.services.d2i_parser import parse_d2i, serialize_d2i, remove_items_from_page

QUALITY_SET = 5
QUALITY_UNIQUE = 7


def create_and_compare(file_path: Path, output_dir: Path):
    """Create modified stash and save for analysis."""
    print(f"\n{'='*80}")
    print("Creating Modified Stash File")
    print(f"{'='*80}\n")

    # Parse original
    stash = parse_d2i(file_path)
    original_bytes = file_path.read_bytes()

    # Modify tab 5 (same as deposit does)
    PORTAL_TAB = 4
    portal_page = stash.pages[PORTAL_TAB]

    print(f"Original tab 5: {portal_page.item_count} items")

    # Find items to remove
    indices_to_remove = []
    for idx, item in enumerate(portal_page.items):
        if item.quality in (QUALITY_UNIQUE, QUALITY_SET):
            indices_to_remove.append(idx)

    print(f"Removing {len(indices_to_remove)} unique/set items...")

    # Modify
    modified_page = remove_items_from_page(portal_page, indices_to_remove)
    stash.pages[PORTAL_TAB] = modified_page

    print(f"Modified tab 5: {modified_page.item_count} items")

    # Serialize
    modified_bytes = serialize_d2i(stash)

    # Save files
    output_dir.mkdir(parents=True, exist_ok=True)
    original_out = output_dir / "original.d2i"
    modified_out = output_dir / "modified.d2i"

    original_out.write_bytes(original_bytes)
    modified_out.write_bytes(modified_bytes)

    print(f"\n📁 Files saved:")
    print(f"  Original:  {original_out}")
    print(f"  Modified:  {modified_out}")

    # Quick comparison
    print(f"\n📊 Comparison:")
    print(f"  Original size: {len(original_bytes)}")
    print(f"  Modified size: {len(modified_bytes)}")
    print(f"  Difference:    {len(modified_bytes) - len(original_bytes):+d} bytes")

    if original_bytes == modified_bytes:
        print(f"  ⚠️  FILES ARE IDENTICAL - No items were removed?")
    else:
        # Find first difference
        for i in range(min(len(original_bytes), len(modified_bytes))):
            if original_bytes[i] != modified_bytes[i]:
                print(f"  First difference at offset: 0x{i:04X} ({i})")
                break

    print(f"\n💡 Next steps:")
    print(f"  1. Hex compare the files: hexdump -C original.d2i > original.hex")
    print(f"  2. Or use: diff <(xxd original.d2i) <(xxd modified.d2i) | head -50")
    print(f"  3. Upload modified.d2i to Deck (BACKUP FIRST!) and test")

    print(f"\n{'='*80}\n")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("/tmp/grail_test"))
    args = parser.parse_args()

    create_and_compare(args.file, args.output)
