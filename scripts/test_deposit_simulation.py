#!/usr/bin/env python3
"""
Test deposit operation: parse → modify → serialize → validate.

This simulates what the actual deposit does to find the bug.
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.services.d2i_parser import (
    parse_d2i,
    serialize_d2i,
    remove_items_from_page,
)

# Quality constants (from grail_service.py)
QUALITY_SET = 5
QUALITY_UNIQUE = 7


def simulate_deposit(file_path: Path) -> bool:
    """Simulate deposit: remove unique/set items from tab 5."""
    print(f"\n{'='*80}")
    print(f"Simulating Deposit: {file_path.name}")
    print(f"{'='*80}\n")

    # Parse
    print("📖 Parsing stash...")
    stash = parse_d2i(file_path)
    print(f"   Pages: {len(stash.pages)}")

    PORTAL_TAB = 4
    if len(stash.pages) <= PORTAL_TAB:
        print(f"ERROR: Not enough pages (need {PORTAL_TAB + 1})")
        return False

    portal_page = stash.pages[PORTAL_TAB]
    print(f"   Tab 5 has {portal_page.item_count} items")

    # Find unique/set items to remove (like deposit does)
    indices_to_remove = []
    for idx, item in enumerate(portal_page.items):
        if item.quality in (QUALITY_UNIQUE, QUALITY_SET):
            indices_to_remove.append(idx)
            print(f"   - Item {idx}: quality={item.quality} (will remove)")

    if not indices_to_remove:
        print("   No unique/set items to remove - nothing to test")
        return True

    print(f"\n🔨 Removing {len(indices_to_remove)} items from tab 5...")

    # Modify (this is where the bug likely is)
    try:
        modified_page = remove_items_from_page(portal_page, indices_to_remove)
        stash.pages[PORTAL_TAB] = modified_page
        print(f"   New item count: {modified_page.item_count}")
        print(f"   New raw_bytes size: {len(modified_page.raw_bytes)}")
        print(f"   Original raw_bytes size: {len(portal_page.raw_bytes)}")
    except Exception as e:
        print(f"   ❌ Modification FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Serialize modified stash
    print(f"\n🔨 Serializing modified stash...")
    try:
        modified_bytes = serialize_d2i(stash)
        print(f"   Serialized size: {len(modified_bytes)} bytes")
    except Exception as e:
        print(f"   ❌ Serialization FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Parse it back to validate
    print(f"\n🔍 Round-trip validation (parse serialized bytes)...")
    try:
        # Write to temp file and parse it
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".d2i", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        tmp_path.write_bytes(modified_bytes)
        rt_stash = parse_d2i(tmp_path)
        tmp_path.unlink()

        rt_page = rt_stash.pages[PORTAL_TAB]
        expected_count = portal_page.item_count - len(indices_to_remove)

        print(f"   Round-trip item count: {rt_page.item_count}")
        print(f"   Expected item count: {expected_count}")

        if rt_page.item_count != expected_count:
            print(f"   ❌ MISMATCH: Round-trip count doesn't match!")
            return False

        print(f"   ✅ Round-trip successful!")

    except Exception as e:
        print(f"   ❌ Round-trip parse FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Size comparison
    original_size = len(file_path.read_bytes())
    print(f"\n📊 Size Analysis:")
    print(f"   Original file:  {original_size} bytes")
    print(f"   Modified file:  {len(modified_bytes)} bytes")
    print(f"   Difference:     {len(modified_bytes) - original_size:+d} bytes")

    # For Modern format, file size might need to stay constant
    if stash.is_modern and len(modified_bytes) != original_size:
        print(f"\n   ⚠️  WARNING: Modern format file size changed!")
        print(f"   This might cause D2R to crash!")
        print(f"   D2R may expect fixed file size.")

    print(f"\n{'='*80}")
    print("✅ DEPOSIT SIMULATION PASSED")
    print("   However, file size change may still cause issues in D2R")
    print(f"{'='*80}\n")
    return True


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, required=True)
    args = parser.parse_args()

    success = simulate_deposit(args.file)
    sys.exit(0 if success else 1)
