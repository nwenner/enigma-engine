"""
D2S respec: refund invested stat and skill points in-place.

Reads the bit-packed stats section, computes invested points vs base stats,
zeroes the 30-byte skill allocation array, refunds to free pools, and
recalculates the file checksum.
"""
import struct
from pathlib import Path

# Base stats (str, dex, vit, ene) per class_id
BASE_STATS: dict[int, tuple[int, int, int, int]] = {
    0: (20, 25, 20, 15),  # Amazon
    1: (10, 25, 10, 35),  # Sorceress
    2: (15, 25, 15, 25),  # Necromancer
    3: (25, 20, 25, 15),  # Paladin
    4: (30, 20, 25, 10),  # Barbarian
    5: (15, 20, 25, 20),  # Druid
    6: (20, 20, 20, 25),  # Assassin
    7: (25, 25, 15, 10),  # Warlock (best-guess)
}

# stat_id → bit width (D2/D2R save format)
STAT_BITS: dict[int, int] = {
    0: 10,   # Strength
    1: 10,   # Energy
    2: 10,   # Dexterity
    3: 10,   # Vitality
    4: 10,   # Free stat points
    5: 8,    # Free skill points
    6: 21,   # Current HP (8.13 fixed-point)
    7: 21,   # Max HP
    8: 21,   # Current Mana
    9: 21,   # Max Mana
    10: 21,  # Current Stamina
    11: 21,  # Max Stamina
    12: 7,   # Level
    13: 32,  # Experience
    14: 25,  # Gold in belt
    15: 25,  # Gold in stash
}


class BitReader:
    """Reads LSB-first bits from a bytearray."""

    def __init__(self, data: bytearray, bit_offset: int = 0):
        self.data = data
        self.bit_offset = bit_offset

    def read(self, n: int) -> int:
        result = 0
        for i in range(n):
            byte_idx = self.bit_offset // 8
            bit_idx = self.bit_offset % 8
            if byte_idx < len(self.data):
                result |= ((self.data[byte_idx] >> bit_idx) & 1) << i
            self.bit_offset += 1
        return result

    def seek(self, bit_offset: int) -> None:
        self.bit_offset = bit_offset


class BitWriter:
    """Writes LSB-first bits into a bytearray."""

    def __init__(self, data: bytearray, bit_offset: int = 0):
        self.data = data
        self.bit_offset = bit_offset

    def write(self, value: int, n: int) -> None:
        for i in range(n):
            byte_idx = self.bit_offset // 8
            bit_idx = self.bit_offset % 8
            if byte_idx < len(self.data):
                bit = (value >> i) & 1
                if bit:
                    self.data[byte_idx] |= 1 << bit_idx
                else:
                    self.data[byte_idx] &= ~(1 << bit_idx)
            self.bit_offset += 1

    def seek(self, bit_offset: int) -> None:
        self.bit_offset = bit_offset


def respec_character(path: Path, class_id: int) -> None:
    """
    Modify a .d2s file in-place to refund all invested stat and skill points.

    Reads stat/skill allocations, resets base stats to class minimums, adds
    invested points back to the free pools, zeroes skill allocations, and
    recalculates the file checksum.
    """
    data = bytearray(path.read_bytes())

    # --- 1. Find stats section ('gf' marker) ---
    gf_byte = data.index(b"gf") + 2
    reader = BitReader(data, gf_byte * 8)

    stats: dict[int, int] = {}
    stat_order: list[int] = []

    while True:
        stat_id = reader.read(9)
        if stat_id == 0x1FF:  # end-of-section sentinel
            break
        if stat_id not in STAT_BITS:
            break  # unknown stat ID; bail out
        bits = STAT_BITS[stat_id]
        value = reader.read(bits)
        stats[stat_id] = value
        stat_order.append(stat_id)

    # --- 2. Compute stat refund ---
    base_str, base_dex, base_vit, base_ene = BASE_STATS.get(class_id, (10, 10, 10, 10))
    invested = (
        max(0, stats.get(0, base_str) - base_str)
        + max(0, stats.get(2, base_dex) - base_dex)
        + max(0, stats.get(3, base_vit) - base_vit)
        + max(0, stats.get(1, base_ene) - base_ene)
    )
    new_free_stats = stats.get(4, 0) + invested

    # --- 3. Find skills section ('if' marker) and compute skill refund ---
    sk_byte = data.index(b"if") + 2
    invested_skills = sum(data[sk_byte : sk_byte + 30])
    new_free_skills = stats.get(5, 0) + invested_skills
    data[sk_byte : sk_byte + 30] = bytes(30)

    # --- 4. Apply respec: reset base stats, update free pools ---
    stats[0] = base_str
    stats[1] = base_ene
    stats[2] = base_dex
    stats[3] = base_vit
    stats[4] = new_free_stats
    stats[5] = new_free_skills

    # --- 5. Write stats back at same offset, same order ---
    writer = BitWriter(data, gf_byte * 8)
    for sid in stat_order:
        writer.write(sid, 9)
        writer.write(stats[sid], STAT_BITS[sid])
    writer.write(0x1FF, 9)  # re-write end sentinel

    # --- 6. Recalculate file checksum ---
    data[0x0C:0x10] = b"\x00\x00\x00\x00"
    acc = 0
    for byte in data:
        acc = ((acc << 1) | (acc >> 31)) & 0xFFFFFFFF
        acc = (acc + byte) & 0xFFFFFFFF
    struct.pack_into("<I", data, 0x0C, acc)

    path.write_bytes(data)
