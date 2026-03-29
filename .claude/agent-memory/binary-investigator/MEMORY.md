# Binary Investigator Memory — Enigma Engine

## .d2s Header Layout (d2s_parser.py)
v96-99 — struct "<IIIIi16sBBBBBBBB" (44 bytes):
  0x00 magic=0xAA55AA55, 0x04 version(96-99), 0x08 filesize, 0x0C checksum
  0x10 active_weapon(int32), 0x14 name(16s latin-1), 0x24 status, 0x28 class, 0x2B level

v100+ — struct "<IIIIiBBBBBBBB" (28 bytes):
  0x00 magic, 0x04 version(100+), 0x08 filesize, 0x0C checksum
  0x10 active_weapon(int32), 0x14 status, 0x18 class, 0x1B level
  0x12B name(16s) — moved here in v100+

## Known Section Offsets
### Map Seed
- v100+: offset 0x9B (4 bytes, uint32 LE)
- v96-99: offset 0xAB (4 bytes, uint32 LE)
- The 16-byte shift = difference in header struct sizes between versions

### Demon Section (Warlock `lf` section)
- Marker: bytes 6c 66 near end of file
- No demon: 6c 66 00 00 (4 bytes, to EOF)
- Demon present: 6c 66 01 00 + 92 bytes = 96 bytes total
  Then: 24-byte `gf` stats block (67 66 + 22 bytes)
  Total from lf marker to EOF = 120 bytes

## Item Scanning (.d2s and .d2i)
- JM section marker: 4a 4d
- Item start pattern: raw[i]==0x10 AND raw[i+3] in (0x00, 0x04)
  - 0x00 = normal identified item
  - 0x04 = is_runeword (bit 26 of flags block)

## Item Bit Stream (LSB-first via BitReader)
- Flag block: 53 bits total (item_flags.py)
  - Bit 21 = is_simple (runes, gems, charms)
  - Bit 22 = is_ethereal
  - Bit 26 = is_runeword
  - Bits 42-45 = position_x, bits 46-49 = position_y
- Huffman type code starts at bit 53 (huffman.py)
- After type: sockets(3), item_id(32), item_level(7), quality(4), ...
- Magic quality (q=4): prefix_id(11) + suffix_id(11) = 22 bits (NOT 23 — D2R dropped has_suffix flag)
- Property sentinel: 0x1FF (9-bit value marking end of property list)

## .d2i Stash Format
- Files: ModernSharedStashSoftCoreV2.d2i, ModernSharedStashHardCoreV2.d2i
- Header: size field at offset 16 (updated on serialize)
- Grid: 10 columns × 10 rows (x: 0–9, y: 0–9) — items at x≥10 or y≥10 silently discarded by D2R
- Tab 5 (index 4) = portal tab — permanent grail/reward drop zone

## Checksum Algorithm
`_calculate_checksum(data)` in d2s_utils.py:
Zero the 4-byte checksum field at offset 0x0C, then iterate all bytes:
  checksum = (rotate_left_1(checksum) + byte) & 0xFFFFFFFF

## Parser Package (backend/services/item_parsing/)
- stash_format.py: parse_stash(), serialize_stash() — round-trip preserves separator bytes
- bit_reader.py: BitReader (LSB-first), BitWriter
- item_fields.py: deterministic parsing from bit 53, _skip_quality_data() per quality type
- item_flags.py: read_item_flags() → ItemFlags (53-bit block)
- huffman.py: decode_item_type() → 4-char str
- tables/: huffman_codes.py, item_types.py, affixes.py, stat_widths.py, runewords.py

## Analysis Tools
- scripts/hex_compare.py — diff two binary files hex
- scripts/analyze_modern_header.py — .d2i header analysis
- tests/item_parsing/fixtures/ — real .d2s and .d2i fixtures
- tests/item_parsing/fixtures/ITEM_DESCRIPTIONS.md — documented item inventory
- Docker exec pattern: `docker exec enigma-engine-enigma-engine-1 python3 -c "..."`
