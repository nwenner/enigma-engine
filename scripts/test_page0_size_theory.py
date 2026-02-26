#!/usr/bin/env python3
"""
Test the theory that page0_size includes JM header + item count + raw data.
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.services.d2i_parser import parse_d2i


def test_theory(file_path: Path):
    """Test if page0_size = JM(2) + count(2) + raw_bytes + separator(8)?"""
    print(f"\n{'='*80}")
    print("Testing page0_size Field Theory")
    print(f"{'='*80}\n")

    data = file_path.read_bytes()
    stash = parse_d2i(file_path)

    # Get page0_size from header
    page0_size_header = struct.unpack_from("<I", data, 16)[0]
    print(f"📋 Header page0_size: {page0_size_header}")

    # Calculate what it SHOULD be based on serialization
    page0 = stash.pages[0]
    raw_size = len(page0.raw_bytes)

    print(f"\n🔍 Page 0 Components:")
    print(f"  Raw data:          {raw_size} bytes")
    print(f"  JM marker:         2 bytes")
    print(f"  Item count:        2 bytes")
    print(f"  8-byte separator:  8 bytes (before page 1)")
    print(f"  Total:             {2 + 2 + raw_size + 8} bytes")

    # Try different theories
    theories = {
        "JM + count + raw": 2 + 2 + raw_size,
        "raw only": raw_size,
        "JM + count + raw + sep": 2 + 2 + raw_size + 8,
        "JM + count + raw + sep - page0 included in header": 2 + 2 + raw_size + 8 - 4,
    }

    print(f"\n🧪 Testing Theories:")
    for name, calc in theories.items():
        match = "✅ MATCH!" if calc == page0_size_header else "❌"
        print(f"  {name:50s} = {calc:4d} {match}")

    # Check ACTUAL bytes in file where page 0 should be
    # Modern format: [64-byte header] [8 zeros] [JM] [count] [page0 data] [8 zeros] [JM] ...
    # Wait, page 0 doesn't have 8 zeros before it - the header ends in zeros
    print(f"\n📍 Finding Page 0 in File:")

    # Find first JM after header
    header_size = 64
    jm_pos = data.find(b"JM", header_size)
    print(f"  First JM marker at offset: {jm_pos}")

    # Find second JM (start of page 1)
    jm2_pos = data.find(b"JM", jm_pos + 2)
    print(f"  Second JM marker at offset: {jm2_pos}")

    # Distance between them
    page0_actual_span = jm2_pos - jm_pos
    print(f"  Bytes from Page0 JM to Page1 JM: {page0_actual_span}")

    # Check if there are 8 zeros before second JM
    separator = data[jm2_pos - 8:jm2_pos]
    if separator == b"\x00" * 8:
        print(f"  8-byte zero separator found before Page 1 ✓")
        page0_span_without_sep = page0_actual_span - 8
        print(f"  Page 0 span (excluding separator): {page0_span_without_sep}")

        if page0_span_without_sep == page0_size_header:
            print(f"\n✅ THEORY CONFIRMED: page0_size = JM + count + raw_data (no separator)")
        elif page0_actual_span == page0_size_header:
            print(f"\n✅ THEORY CONFIRMED: page0_size = JM + count + raw_data + separator")

    print(f"\n{'='*80}\n")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, required=True)
    args = parser.parse_args()

    test_theory(args.file)
