#!/usr/bin/env python3
"""
Validate D2I stash file serialization (round-trip test).

Tests parse → serialize → compare to find serialization bugs.
Run this BEFORE attempting any real stash modifications.

Usage:
    # Test with a local file
    python scripts/validate_d2i_serialization.py --file /path/to/ModernSharedStashSoftCoreV2.d2i

    # Test by downloading from a machine (requires app running)
    python scripts/validate_d2i_serialization.py --machine deck --mode sc
"""
import argparse
import sys
from pathlib import Path
from difflib import unified_diff


def hex_dump(data: bytes, offset: int = 0, length: int = 256) -> str:
    """Create a hex dump of bytes."""
    lines = []
    for i in range(offset, min(offset + length, len(data)), 16):
        hex_part = " ".join(f"{b:02x}" for b in data[i:i+16])
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in data[i:i+16])
        lines.append(f"{i:08x}  {hex_part:<48}  {ascii_part}")
    return "\n".join(lines)


def compare_bytes(original: bytes, serialized: bytes) -> dict:
    """Compare two byte arrays and return detailed diff info."""
    result = {
        "identical": original == serialized,
        "size_diff": len(serialized) - len(original),
        "original_size": len(original),
        "serialized_size": len(serialized),
        "diff_positions": [],
    }

    # Find all positions where bytes differ
    min_len = min(len(original), len(serialized))
    for i in range(min_len):
        if original[i] != serialized[i]:
            result["diff_positions"].append({
                "offset": i,
                "original": original[i],
                "serialized": serialized[i],
            })

    # If sizes differ, note the extra/missing bytes
    if len(serialized) > len(original):
        result["extra_bytes"] = serialized[len(original):]
    elif len(original) > len(serialized):
        result["missing_bytes"] = original[len(serialized):]

    return result


def validate_file(file_path: Path) -> bool:
    """Validate a single .d2i file with round-trip test."""
    print(f"\n{'='*80}")
    print(f"Validating: {file_path.name}")
    print(f"{'='*80}\n")

    # Import here to avoid issues if running outside docker
    try:
        from backend.services.d2i_parser import parse_d2i, serialize_d2i
    except ImportError:
        print("ERROR: Cannot import d2i_parser. Run this script from project root or inside docker.")
        return False

    if not file_path.exists():
        print(f"ERROR: File not found: {file_path}")
        return False

    # Read original file
    print(f"📖 Reading original file...")
    original_bytes = file_path.read_bytes()
    print(f"   Size: {len(original_bytes)} bytes")

    # Parse
    print(f"\n🔍 Parsing stash...")
    try:
        stash = parse_d2i(file_path)
        print(f"   Format: {'Modern' if stash.is_modern else 'Legacy'}")
        print(f"   Version: {stash.version}")
        print(f"   Pages: {len(stash.pages)}")
        for i, page in enumerate(stash.pages):
            print(f"   - Page {i}: {page.item_count} items, {len(page.raw_bytes)} bytes")
    except Exception as e:
        print(f"   ❌ Parse FAILED: {e}")
        return False

    # Serialize
    print(f"\n🔨 Serializing back to bytes...")
    try:
        serialized_bytes = serialize_d2i(stash)
        print(f"   Size: {len(serialized_bytes)} bytes")
    except Exception as e:
        print(f"   ❌ Serialize FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Compare
    print(f"\n🔬 Comparing original vs serialized...")
    diff = compare_bytes(original_bytes, serialized_bytes)

    if diff["identical"]:
        print("   ✅ PERFECT MATCH - Serialization is byte-for-byte identical!")
        return True

    # Show differences
    print(f"   ❌ MISMATCH DETECTED")
    print(f"\n   Size difference: {diff['size_diff']:+d} bytes")
    print(f"   Original:   {diff['original_size']} bytes")
    print(f"   Serialized: {diff['serialized_size']} bytes")

    if diff["diff_positions"]:
        print(f"\n   First 10 byte differences:")
        for i, d in enumerate(diff["diff_positions"][:10]):
            print(f"   - Offset {d['offset']:08x}: {d['original']:02x} → {d['serialized']:02x}")
        if len(diff["diff_positions"]) > 10:
            print(f"   ... and {len(diff['diff_positions']) - 10} more differences")

    # Show hex dumps of first difference area
    if diff["diff_positions"]:
        first_diff = diff["diff_positions"][0]["offset"]
        start = max(0, first_diff - 32)

        print(f"\n   Hex dump around first difference (offset {first_diff:08x}):")
        print("\n   ORIGINAL:")
        print("   " + "\n   ".join(hex_dump(original_bytes, start, 128).split("\n")))
        print("\n   SERIALIZED:")
        print("   " + "\n   ".join(hex_dump(serialized_bytes, start, 128).split("\n")))

    if "extra_bytes" in diff:
        print(f"\n   Extra bytes at end ({len(diff['extra_bytes'])} bytes):")
        print("   " + "\n   ".join(hex_dump(diff['extra_bytes'], 0, 128).split("\n")))

    if "missing_bytes" in diff:
        print(f"\n   Missing bytes at end ({len(diff['missing_bytes'])} bytes):")
        print("   " + "\n   ".join(hex_dump(diff['missing_bytes'], 0, 128).split("\n")))

    return False


def download_and_validate(machine: str, mode: str) -> bool:
    """Download stash from machine and validate."""
    import asyncio
    import tempfile

    try:
        from backend.database import get_async_session_context
        from backend.routers.settings import _get_conn_kwargs, _get_setting
        from backend.services.ssh_client import get_sftp, normalize_path
        from backend.services.backup_manager import _sftp_download
    except ImportError:
        print("ERROR: Cannot import backend modules. Run inside docker:")
        print("  docker compose exec backend python scripts/validate_d2i_serialization.py --machine deck --mode sc")
        return False

    filename = f"ModernSharedStash{'HardCore' if mode == 'hc' else 'SoftCore'}V2.d2i"

    async def _download():
        async with get_async_session_context() as session:
            conn = await _get_conn_kwargs(session, machine)
            save_dir = await _get_setting(session, f"{machine}_save_path") or ""

            if not save_dir:
                print(f"ERROR: {machine}_save_path not configured")
                return None

            remote_path = normalize_path(f"{save_dir}/{filename}")

            with tempfile.NamedTemporaryFile(suffix=".d2i", delete=False) as tmp:
                tmp_path = Path(tmp.name)

            def _do_download():
                with get_sftp(**conn) as (_ssh, sftp):
                    _sftp_download(sftp, remote_path, tmp_path)

            await asyncio.to_thread(_do_download)
            return tmp_path

    print(f"📥 Downloading {filename} from {machine.upper()}...")
    tmp_path = asyncio.run(_download())

    if tmp_path is None:
        return False

    try:
        result = validate_file(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)

    return result


def main():
    parser = argparse.ArgumentParser(description="Validate D2I stash serialization")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", type=Path, help="Path to .d2i file to validate")
    group.add_argument("--machine", choices=["pc", "deck"], help="Download from machine")
    parser.add_argument("--mode", choices=["sc", "hc"], help="Mode (required with --machine)")

    args = parser.parse_args()

    if args.machine and not args.mode:
        parser.error("--mode required when using --machine")

    success = False
    if args.file:
        success = validate_file(args.file)
    else:
        success = download_and_validate(args.machine, args.mode)

    print(f"\n{'='*80}")
    if success:
        print("✅ VALIDATION PASSED - Serialization is correct!")
        print("='*80}\n")
        sys.exit(0)
    else:
        print("❌ VALIDATION FAILED - Serialization bug detected")
        print("   DO NOT use deposit/retrieve until this is fixed!")
        print(f"{'='*80}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
