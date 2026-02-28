"""
Debug magic item prefix/suffix parsing for a .d2i stash file.

Prints every magic-quality item found, showing:
  - item_code (huffman decoded)
  - q_bit offset used (from Phase 2 scan)
  - raw prefix_id / suffix_id bits read
  - mapped prefix name / suffix name
  - prop_end position and max_bit

Usage: python3 scripts/debug_magic_items.py path/to/stash.d2i
"""

import sys
import struct
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from services.d2i_parser import (
    _find_item_starts_modern,
    _decode_huffman_item_code,
    _MAGIC_PREFIXES,
    _MAGIC_SUFFIXES,
    BitReader,
    _skip_quality_data,
    _full_property_list_valid,
    _is_valid_property_list,
    _property_list_end,
    _parse_property_list,
)

_MOD_QUALITY_SCAN_START = 104
_MOD_QUALITY_SCAN_END_WIDE = 145
_b82_byte_offset = 10
_b82_bit = 2


def parse_modern_pages(data: bytes):
    """Yield (page_index, page_raw) for each page in a Modern stash."""
    if len(data) < 16:
        return
    sig = data[:4]
    if sig not in (b'\x55\xAA\x55\xAA', b'D2ST'):
        print(f"Unknown signature: {sig!r}")

    version = struct.unpack_from('<I', data, 4)[0]
    page_count = struct.unpack_from('<H', data, 10)[0]
    print(f"Signature={sig!r} version={version} pages={page_count}")

    # Modern format: after 14-byte main header, pages follow
    # Each page has a small header then item data
    # The exact layout: use the same logic as _parse_stash_modern
    # Simplified: just find items across the whole file
    return data


def debug_file(path: Path):
    raw = bytearray(path.read_bytes())
    print(f"\n=== {path} ({len(raw)} bytes) ===")

    # Find all item starts using the JM marker
    # Items are marked by 0x4A 0x4D ("JM") in the raw bytes
    # Collect all byte offsets where "JM" appears
    item_starts = []
    i = 0
    while i < len(raw) - 1:
        if raw[i] == 0x4A and raw[i+1] == 0x4D:
            item_starts.append(i)
        i += 1

    print(f"Found {len(item_starts)} 'JM' markers")

    for byte_start in item_starts:
        # Try to determine item end (next JM or file end)
        idx = item_starts.index(byte_start)
        if idx + 1 < len(item_starts):
            byte_end = item_starts[idx + 1]
        else:
            byte_end = len(raw)

        max_bit = byte_end * 8
        base = byte_start * 8

        item_code = _decode_huffman_item_code(raw, byte_start)
        if not item_code or item_code.strip() == '':
            continue

        # Check bit 82 guard
        b82_byte = byte_start + _b82_byte_offset
        _b82 = bool((raw[b82_byte] >> _b82_bit) & 1) if b82_byte < len(raw) else True

        # Run Phase 2 scan for this item
        reader = BitReader(raw, base)

        candidates = []
        for q_bit in range(_MOD_QUALITY_SCAN_START, _MOD_QUALITY_SCAN_END_WIDE):
            reader.seek(base + q_bit)
            q = reader.read(4)
            if q not in (0, 1, 2, 3, 4, 6, 8):
                continue
            if q != 0 and not _b82:
                continue

            ilvl = BitReader(raw, base + q_bit - 7).read(7)
            max_ilvl = 127 if q == 3 else 99
            if not (1 <= ilvl <= max_ilvl):
                continue

            reader.seek(base + q_bit + 4)
            mult_pics = reader.read(1)
            if mult_pics:
                reader.read(11)
            class_specific = reader.read(1)
            if class_specific:
                reader.read(11)

            qd = _skip_quality_data(reader, q, class_specific=bool(class_specific))
            props_start = reader.tell()
            if props_start >= max_bit:
                continue

            is_full = _full_property_list_valid(raw, props_start, max_bit, min_stats=1)
            if not is_full and not _is_valid_property_list(raw, props_start, max_bit):
                continue

            prop_end = (
                _property_list_end(raw, props_start, max_bit, min_stats=1)
                if is_full and q == 3 else -1
            )

            candidates.append({
                'q_bit': q_bit,
                'q': q,
                'ilvl': ilvl,
                'is_full': is_full,
                'prop_end': prop_end,
                'props_start': props_start,
                'qd': qd,
            })

        # Only print items that have magic quality (q=3) candidates
        magic_candidates = [c for c in candidates if c['q'] == 3]
        if not magic_candidates:
            continue

        print(f"\n--- Item: {item_code!r} @ byte {byte_start} (max_bit={max_bit}) ---")
        print(f"  b82={_b82}  item_code={item_code!r}")
        for c in candidates:
            q = c['q']
            pid = c['qd'].get('magic_prefix_id', 0)
            sid = c['qd'].get('magic_suffix_id', 0)
            pname = _MAGIC_PREFIXES.get(pid, f'<unknown:{pid}>') if pid else ''
            sname = _MAGIC_SUFFIXES.get(sid, f'<unknown:{sid}>') if sid else ''
            print(f"  q_bit={c['q_bit']}  q={q}  ilvl={c['ilvl']}  full={c['is_full']}  "
                  f"prop_end={c['prop_end']}  max_bit={max_bit}")
            if q == 3:
                print(f"         pid={pid}→{pname!r}  sid={sid}→{sname!r}")
            elif q in (4, 6):
                n1 = c['qd'].get('rare_name1', 0)
                n2 = c['qd'].get('rare_name2', 0)
                print(f"         rare_name1={n1}  rare_name2={n2}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        # Try to find a .d2i file
        candidates = list(Path("data").rglob("*.d2i"))
        if not candidates:
            print("Usage: python3 scripts/debug_magic_items.py path/to/stash.d2i")
            sys.exit(1)
        path = candidates[0]
        print(f"Auto-selected: {path}")
    else:
        path = Path(sys.argv[1])

    debug_file(path)
