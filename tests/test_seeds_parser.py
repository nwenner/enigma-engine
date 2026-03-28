from __future__ import annotations

"""
Unit tests for read_map_seed() in backend.services.d2s_parser.

No SQLAlchemy dependency — pure Python.
Run locally: python3 -m pytest tests/test_seeds_parser.py -v
"""

import struct
from pathlib import Path

import pytest

from backend.services.d2s_parser import (
    D2SParseError,
    MAGIC,
    read_map_seed,
    write_map_seed,
)
from backend.services.d2s_utils import _calculate_checksum


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_v100_seed_file(seed: int) -> bytes:
    """Create a minimal v100+ .d2s file with the given seed at offset 0x9B."""
    size = 0x9B + 12
    buf = bytearray(size)
    struct.pack_into("<I", buf, 0, MAGIC)      # magic
    struct.pack_into("<I", buf, 4, 105)         # version = 105 (v100+)
    struct.pack_into("<I", buf, 0x9B, seed)     # seed at v100+ offset
    return bytes(buf)


def _make_v99_seed_file(seed: int) -> bytes:
    """Create a minimal v99 .d2s file with the given seed at offset 0xAB."""
    size = 0xAB + 12
    buf = bytearray(size)
    struct.pack_into("<I", buf, 0, MAGIC)      # magic
    struct.pack_into("<I", buf, 4, 99)          # version = 99 (v96-99)
    struct.pack_into("<I", buf, 0xAB, seed)     # seed at v99 offset
    return bytes(buf)


# ─── Tests ────────────────────────────────────────────────────────────────────

class TestReadMapSeed:
    def test_v100_seed_read_correctly(self) -> None:
        """v100+ file with seed 0x01C73932 at offset 0x9B returns 0x01C73932."""
        data = _make_v100_seed_file(0x01C73932)
        assert read_map_seed(data) == 0x01C73932

    def test_v99_seed_read_correctly(self) -> None:
        """v99 file with seed 0xDEADBEEF at offset 0xAB returns 0xDEADBEEF."""
        data = _make_v99_seed_file(0xDEADBEEF)
        assert read_map_seed(data) == 0xDEADBEEF

    def test_tald_fixture_returns_known_seed(self) -> None:
        """Tald.d2s fixture (v105) returns seed == 0x01C73932 (confirmed from hex dump)."""
        fixture = Path(__file__).parent / "fixtures" / "Tald.d2s"
        data = fixture.read_bytes()
        assert read_map_seed(data) == 0x01C73932

    def test_file_too_small_raises_parse_error(self) -> None:
        """File with only 4 bytes raises D2SParseError('file too small to read version')."""
        data = b"\x00" * 4
        with pytest.raises(D2SParseError, match="file too small to read version"):
            read_map_seed(data)

    def test_v105_truncated_raises_parse_error(self) -> None:
        """v105 file of only 16 bytes raises D2SParseError (seed offset 0x9B unreachable)."""
        buf = bytearray(16)
        struct.pack_into("<I", buf, 0, MAGIC)
        struct.pack_into("<I", buf, 4, 105)
        with pytest.raises(D2SParseError):
            read_map_seed(bytes(buf))


# ─── TestWriteMapSeed ─────────────────────────────────────────────────────────

class TestWriteMapSeed:
    def test_v100_seed_written_correctly(self) -> None:
        """write_map_seed on v100+ file writes seed at 0x9B; read_map_seed reads it back."""
        data = _make_v100_seed_file(0x00000000)
        result = write_map_seed(data, 0xDEADBEEF)
        assert read_map_seed(result) == 0xDEADBEEF

    def test_v99_seed_written_correctly(self) -> None:
        """write_map_seed on v99 file writes seed at 0xAB; read_map_seed reads it back."""
        data = _make_v99_seed_file(0x00000000)
        result = write_map_seed(data, 0x01C73932)
        assert read_map_seed(result) == 0x01C73932

    def test_file_size_unchanged(self) -> None:
        """write_map_seed must not change the file size."""
        data = _make_v100_seed_file(0x12345678)
        result = write_map_seed(data, 0xABCDEF01)
        assert len(result) == len(data)

    def test_checksum_recalculated(self) -> None:
        """After write_map_seed, zeroing checksum field and recalculating must match stored value."""
        data = _make_v100_seed_file(0x00000000)
        result = write_map_seed(data, 0xDEADBEEF)

        # Extract stored checksum from offset 12
        stored_checksum = struct.unpack_from("<I", result, 12)[0]

        # Recalculate: zero the checksum field first, then compute
        recalc_buf = bytearray(result)
        struct.pack_into("<I", recalc_buf, 12, 0)
        expected = _calculate_checksum(bytes(recalc_buf))

        assert stored_checksum == expected

    def test_truncated_raises_parse_error(self) -> None:
        """A 4-byte file raises D2SParseError from write_map_seed."""
        with pytest.raises(D2SParseError):
            write_map_seed(b"\x00" * 4, 0xDEADBEEF)
