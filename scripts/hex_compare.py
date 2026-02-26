#!/usr/bin/env python3
"""
Detailed hex comparison of two binary files.
"""
import sys
from pathlib import Path


def hex_dump_line(data: bytes, offset: int) -> str:
    """Format a single line of hex dump."""
    hex_part = " ".join(f"{b:02x}" for b in data)
    ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in data)
    return f"{offset:08x}  {hex_part:<48}  {ascii_part}"


def compare_files(file1: Path, file2: Path):
    """Compare two files byte-by-byte."""
    print(f"\n{'='*80}")
    print(f"Hex Comparing:")
    print(f"  File 1: {file1.name}")
    print(f"  File 2: {file2.name}")
    print(f"{'='*80}\n")

    data1 = file1.read_bytes()
    data2 = file2.read_bytes()

    print(f"📊 Size Comparison:")
    print(f"  File 1: {len(data1)} bytes")
    print(f"  File 2: {len(data2)} bytes")
    print(f"  Diff:   {len(data2) - len(data1):+d} bytes")

    if data1 == data2:
        print(f"\n✅ FILES ARE IDENTICAL\n")
        return

    print(f"\n❌ FILES DIFFER\n")

    # Find all differences
    min_len = min(len(data1), len(data2))
    diff_ranges = []
    in_diff = False
    diff_start = 0

    for i in range(min_len):
        if data1[i] != data2[i]:
            if not in_diff:
                diff_start = i
                in_diff = True
        else:
            if in_diff:
                diff_ranges.append((diff_start, i))
                in_diff = False

    if in_diff:
        diff_ranges.append((diff_start, min_len))

    # Handle size difference
    if len(data1) != len(data2):
        if len(data2) > len(data1):
            diff_ranges.append((len(data1), len(data2)))
        else:
            diff_ranges.append((len(data2), len(data1)))

    print(f"🔍 Found {len(diff_ranges)} difference region(s):\n")

    # Show first 10 differences in detail
    for idx, (start, end) in enumerate(diff_ranges[:10]):
        print(f"  Difference #{idx + 1}: offset 0x{start:04X} - 0x{end:04X} ({end - start} bytes)")

        # Show context (16 bytes before, diff region, 16 bytes after)
        context_start = max(0, start - 16)
        context_end = min(min_len, end + 16)

        print(f"\n  File 1 ({file1.name}):")
        for offset in range(context_start, context_end, 16):
            chunk_end = min(offset + 16, len(data1))
            chunk = data1[offset:chunk_end]
            line = hex_dump_line(chunk, offset)

            # Mark the diff region
            if start <= offset < end or (offset < start < offset + 16):
                print(f"  → {line}")
            else:
                print(f"    {line}")

        print(f"\n  File 2 ({file2.name}):")
        for offset in range(context_start, min(context_end, len(data2)), 16):
            chunk_end = min(offset + 16, len(data2))
            chunk = data2[offset:chunk_end]
            line = hex_dump_line(chunk, offset)

            # Mark the diff region
            if start <= offset < end or (offset < start < offset + 16):
                print(f"  → {line}")
            else:
                print(f"    {line}")

        print()

    if len(diff_ranges) > 10:
        print(f"  ... and {len(diff_ranges) - 10} more difference regions")

    print(f"{'='*80}\n")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("file1", type=Path)
    parser.add_argument("file2", type=Path)
    args = parser.parse_args()

    compare_files(args.file1, args.file2)
