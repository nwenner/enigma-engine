"""
Huffman decoding for D2R Modern item type codes.

D2R encodes the 4-character item type as a Huffman sequence starting at bit 53
of each item (LSB-first). Each character is decoded independently using a
variable-length code (2–9 bits).
"""
from __future__ import annotations

from .bit_reader import BitReader
from .tables.huffman_codes import HUFFMAN_REVERSE


def decode_item_type(reader: BitReader) -> str:
    """
    Decode 4-char Huffman item type from the current reader position.

    Advances the reader past all consumed bits.
    Returns the 4-char string (e.g. 'cm1 ', 'rin ', 'r03 ').
    Raises ValueError if a character cannot be decoded.
    """
    code: list[str] = []
    for char_idx in range(4):
        saved = reader.tell()
        found = False
        # Try code lengths from shortest (2) to longest (9)
        for length in range(2, 10):
            if reader.remaining() < length:
                break
            reader.seek(saved)
            v = reader.read(length)
            ch = HUFFMAN_REVERSE.get((v, length))
            if ch is not None:
                code.append(ch)
                found = True
                break
        if not found:
            raise ValueError(
                f"Cannot decode Huffman char {char_idx} at bit {saved}: "
                f"no matching code"
            )
    return "".join(code)
