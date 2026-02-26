#!/usr/bin/env python3
"""
Analyze Modern format stash header to find validation/checksum fields.

Modern format header is 64 bytes:
  [0-3]   magic (4)
  [4-7]   version (4)
  [8-11]  unknown (4)
  [12-15] gold (4)
  [16-19] page0_size (4)
  [20-63] zeros (44)

We need to figure out what those "unknown" and "zeros" bytes actually are.
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.services.d2i_parser import parse_d2i


def analyze_header(file_path: Path):
    """Analyze a Modern format stash header."""
    print(f"\n{'='*80}")
    print(f"Analyzing Modern Format Header: {file_path.name}")
    print(f"{'='*80}\n")

    data = file_path.read_bytes()

    if len(data) < 64:
        print("ERROR: File too small for Modern format")
        return

    # Check version to confirm Modern format
    version = struct.unpack_from("<I", data, 4)[0]
    if version != 2:
        print(f"WARNING: Version is {version}, not 2 (Modern format)")
        return

    print("📋 Header Structure (64 bytes):\n")

    # Parse known fields
    magic = struct.unpack_from("<I", data, 0)[0]
    version = struct.unpack_from("<I", data, 4)[0]
    unknown1 = struct.unpack_from("<I", data, 8)[0]
    gold = struct.unpack_from("<I", data, 12)[0]
    page0_size = struct.unpack_from("<I", data, 16)[0]

    print(f"  [0-3]   Magic:          0x{magic:08X}")
    print(f"  [4-7]   Version:        {version}")
    print(f"  [8-11]  Unknown1:       {unknown1} (0x{unknown1:08X})")
    print(f"  [12-15] Gold:           {gold}")
    print(f"  [16-19] Page0_Size:     {page0_size}")

    # Check if there might be page sizes for other pages
    print(f"\n  [20-63] Remaining bytes (44 bytes):")

    # Try interpreting as uint32s
    for offset in range(20, 64, 4):
        if offset + 4 <= 64:
            val = struct.unpack_from("<I", data, offset)[0]
            if val != 0:
                print(f"    [{offset:2d}-{offset+3:2d}] = {val:10d} (0x{val:08X}) ← NON-ZERO!")
            else:
                print(f"    [{offset:2d}-{offset+3:2d}] = {val:10d}")

    # Parse the stash to get actual page sizes
    print(f"\n📊 Actual Page Sizes from parsing:\n")
    stash = parse_d2i(file_path)

    for i, page in enumerate(stash.pages):
        actual_size = len(page.raw_bytes)
        print(f"  Page {i}: {page.item_count:2d} items, {actual_size:4d} bytes raw data")

    # Check if page0_size matches
    if len(stash.pages) > 0:
        page0_actual = len(stash.pages[0].raw_bytes)
        print(f"\n🔍 Page0_Size Validation:")
        print(f"  Header says: {page0_size}")
        print(f"  Actual size: {page0_actual}")
        if page0_size == page0_actual:
            print(f"  ✅ MATCH")
        else:
            print(f"  ❌ MISMATCH - This could cause crashes!")

    # Look for any other size fields in the "zeros" section
    print(f"\n🔍 Searching for other page size fields...")
    found_sizes = False
    for i, page in enumerate(stash.pages):
        actual_size = len(page.raw_bytes)
        # Check if this size appears anywhere in header bytes 20-63
        for offset in range(20, 64, 4):
            val = struct.unpack_from("<I", data, offset)[0]
            if val == actual_size:
                print(f"  Page {i} size ({actual_size}) found at offset {offset}!")
                found_sizes = True

    if not found_sizes:
        print(f"  No other page sizes found in header")

    # Hex dump full header
    print(f"\n📄 Full Header Hex Dump:\n")
    for offset in range(0, 64, 16):
        hex_part = " ".join(f"{b:02x}" for b in data[offset:offset+16])
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in data[offset:offset+16])
        print(f"  {offset:04x}  {hex_part:<48}  {ascii_part}")

    print(f"\n{'='*80}\n")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, required=True)
    args = parser.parse_args()

    analyze_header(args.file)
