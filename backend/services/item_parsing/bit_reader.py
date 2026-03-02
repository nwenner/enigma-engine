"""
LSB-first bit I/O utilities for D2 save file parsing.

D2 uses little-endian bit ordering: the LSB of byte 0 is bit 0,
the MSB of byte 0 is bit 7, the LSB of byte 1 is bit 8, etc.
"""
from __future__ import annotations


class BitReader:
    """Reads LSB-first bits from a bytes-like object."""

    __slots__ = ("data", "bit_offset")

    def __init__(self, data: bytes | bytearray, bit_offset: int = 0) -> None:
        self.data = data
        self.bit_offset = bit_offset

    def read(self, n: int) -> int:
        result = 0
        for i in range(n):
            byte_idx = self.bit_offset >> 3
            bit_idx = self.bit_offset & 7
            if byte_idx < len(self.data):
                result |= ((self.data[byte_idx] >> bit_idx) & 1) << i
            self.bit_offset += 1
        return result

    def peek(self, n: int) -> int:
        saved = self.bit_offset
        val = self.read(n)
        self.bit_offset = saved
        return val

    def seek(self, bit_offset: int) -> None:
        self.bit_offset = bit_offset

    def tell(self) -> int:
        return self.bit_offset

    def remaining(self) -> int:
        return max(0, len(self.data) * 8 - self.bit_offset)


class BitWriter:
    """Writes LSB-first bits into a growing bytearray."""

    __slots__ = ("_buf", "_bit_offset")

    def __init__(self) -> None:
        self._buf: bytearray = bytearray()
        self._bit_offset: int = 0

    def write(self, value: int, n: int) -> None:
        for i in range(n):
            byte_idx = self._bit_offset >> 3
            bit_idx = self._bit_offset & 7
            if byte_idx >= len(self._buf):
                self._buf.append(0)
            if (value >> i) & 1:
                self._buf[byte_idx] |= 1 << bit_idx
            self._bit_offset += 1

    def tell(self) -> int:
        return self._bit_offset

    def to_bytes(self) -> bytes:
        return bytes(self._buf)
