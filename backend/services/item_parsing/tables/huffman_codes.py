"""
Huffman reverse lookup table for D2R Modern item type codes.

Maps (bit_value, bit_length) → character.
Derived from dschu012/d2s TypeScript reference.
D2R Modern stash uses LSB-first Huffman-encoded 4-char item type codes.
"""
from __future__ import annotations

# Maps (value, bit_length) → character
HUFFMAN_REVERSE: dict[tuple[int, int], str] = {
    (1, 2): ' ',
    (10, 4): 'b', (4, 4): 's',
    (15, 5): 'a', (2, 5): 'c', (11, 5): 'g', (24, 5): 'h', (23, 5): 'l',
    (22, 5): 'm', (19, 5): 'p', (7, 5): 'r', (6, 5): 't', (16, 5): 'u',
    (0, 5): 'w', (28, 5): 'x', (30, 5): '7', (14, 5): '9',
    (12, 6): '2', (8, 6): '8', (35, 6): 'd', (3, 6): 'e', (50, 6): 'f',
    (18, 6): 'k', (44, 6): 'n',
    (31, 7): '1', (91, 7): '3', (123, 7): '6', (63, 7): 'i', (127, 7): 'o',
    (59, 7): 'v', (40, 7): 'y',
    (223, 8): '0', (95, 8): '4', (104, 8): '5', (155, 8): 'q', (27, 8): 'z',
    (232, 9): 'j',
}

# Bit offset from item byte_start where the Huffman code begins.
# Confirmed empirically across cm1/cm2/cm3/rin/r03/fhl.
HUFFMAN_CODE_START_BIT = 53
