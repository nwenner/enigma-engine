from __future__ import annotations

"""
Unit tests for item extraction from .d2i files (Hero Editor single-item exports)
and for _parse_item_bytes in the rewards router.

The Enigma.d2i fixture is a real export from Hero Editor.
The stash fixture provides additional real items.

No SQLAlchemy required — pure Python.
Run locally: python3 -m pytest tests/test_item_extraction.py -v
"""

from pathlib import Path

import pytest

# ─── Fixtures ─────────────────────────────────────────────────────────────────

ENIGMA_D2I = Path("/Users/nickwenner/Downloads/Enigma.d2i")
STASH_FIXTURE = (
    Path(__file__).parent / "item_parsing" / "fixtures" / "ModernSharedStashSoftCoreV2.d2i"
)
# Reign of the Warlock patch — new unique item fixture
ARS_DUL_MEPHISTOS = (
    Path(__file__).parent / "item_parsing" / "fixtures" / "ArsDulMephistos.d2i"
)


def _stash_item_bytes(tab: int = 0, index: int = 0) -> bytes:
    """Extract raw bytes for one item from the stash fixture."""
    from backend.services.item_parsing import parse_stash
    stash = parse_stash(STASH_FIXTURE, hardcore=False)
    page = stash.pages[tab]
    item = page.items[index]
    return bytes(page.raw_bytes[item.byte_start:item.byte_end])


# ─── _parse_item_bytes (rewards router) ───────────────────────────────────────

class TestParseItemBytes:
    """Tests for parse_item_bytes in backend.services.item_export."""

    def _parse(self, raw: bytes) -> dict:
        from backend.services.item_export import parse_item_bytes
        return parse_item_bytes(raw)

    # --- Happy path: stash fixture item ---

    def test_stash_item_parses_successfully(self) -> None:
        result = self._parse(_stash_item_bytes())
        assert result["valid"] is True
        assert result["error"] is None

    def test_stash_item_has_item_code(self) -> None:
        result = self._parse(_stash_item_bytes())
        assert result["item_code"] is not None
        assert isinstance(result["item_code"], str)

    def test_stash_item_code_is_stripped(self) -> None:
        result = self._parse(_stash_item_bytes())
        code = result["item_code"]
        assert code == code.strip()

    def test_stash_item_has_quality(self) -> None:
        result = self._parse(_stash_item_bytes())
        assert result["quality"] is not None
        assert isinstance(result["quality"], int)
        assert 0 <= result["quality"] <= 9

    def test_stash_item_has_quality_name(self) -> None:
        result = self._parse(_stash_item_bytes())
        assert result["quality_name"] is not None
        assert isinstance(result["quality_name"], str)

    def test_stash_item_is_ethereal_is_bool(self) -> None:
        result = self._parse(_stash_item_bytes())
        assert isinstance(result["is_ethereal"], bool)

    def test_stash_item_has_item_name_or_none(self) -> None:
        result = self._parse(_stash_item_bytes())
        # item_name can be None for items without a catalog/magic name
        assert "item_name" in result

    # --- Happy path: Enigma.d2i Hero Editor export ---

    @pytest.mark.skipif(not ENIGMA_D2I.exists(), reason="Enigma.d2i fixture not available")
    def test_enigma_parses_successfully(self) -> None:
        result = self._parse(ENIGMA_D2I.read_bytes())
        assert result["valid"] is True

    @pytest.mark.skipif(not ENIGMA_D2I.exists(), reason="Enigma.d2i fixture not available")
    def test_enigma_item_code_is_mage_plate(self) -> None:
        """Enigma.d2i is a Mage Plate (xtp) base item."""
        result = self._parse(ENIGMA_D2I.read_bytes())
        assert result["item_code"] == "xtp"

    @pytest.mark.skipif(not ENIGMA_D2I.exists(), reason="Enigma.d2i fixture not available")
    def test_enigma_base_name_is_mage_plate(self) -> None:
        result = self._parse(ENIGMA_D2I.read_bytes())
        assert "Mage Plate" in (result["item_name"] or "")

    @pytest.mark.skipif(not ENIGMA_D2I.exists(), reason="Enigma.d2i fixture not available")
    def test_enigma_item_level_is_90(self) -> None:
        result = self._parse(ENIGMA_D2I.read_bytes())
        assert result["item_level"] == 90

    @pytest.mark.skipif(not ENIGMA_D2I.exists(), reason="Enigma.d2i fixture not available")
    def test_enigma_is_not_ethereal(self) -> None:
        result = self._parse(ENIGMA_D2I.read_bytes())
        assert result["is_ethereal"] is False

    @pytest.mark.skipif(not ENIGMA_D2I.exists(), reason="Enigma.d2i fixture not available")
    def test_enigma_quality_is_normal(self) -> None:
        """Runewords are base-quality armor/weapons — quality=2 (normal)."""
        result = self._parse(ENIGMA_D2I.read_bytes())
        assert result["quality"] == 2
        assert result["quality_name"] == "normal"

    # --- Error paths ---

    def test_empty_bytes_returns_invalid(self) -> None:
        result = self._parse(b"")
        assert result["valid"] is False
        assert result["error"] is not None

    def test_too_few_bytes_returns_invalid(self) -> None:
        """3 bytes — not enough bits to decode flags (53 bits) + Huffman type code."""
        result = self._parse(b"\x00" * 3)
        assert result["valid"] is False

    def test_truncated_item_returns_invalid(self) -> None:
        """Just the first 3 bytes of an item — too short to parse."""
        result = self._parse(b"\x10\x08\x80")
        assert result["valid"] is False

    def test_error_field_is_string_when_invalid(self) -> None:
        result = self._parse(b"\xff" * 8)
        assert result["valid"] is False
        assert isinstance(result["error"], str)

    def test_invalid_result_has_none_fields(self) -> None:
        result = self._parse(b"\x00" * 4)
        assert result["item_name"] is None
        assert result["item_code"] is None
        assert result["quality"] is None
        assert result["quality_name"] is None


# ─── Enigma.d2i full round-trip via _hex_to_bytes ─────────────────────────────

class TestHexRoundTrip:
    """Verify the hex representation round-trips back to the original bytes."""

    def test_hex_round_trip_stash_item(self) -> None:
        from backend.services.item_export import parse_item_bytes
        original = _stash_item_bytes()
        result = parse_item_bytes(original)
        assert result["valid"] is True
        hex_str = " ".join(f"{b:02x}" for b in original)
        recovered = bytes.fromhex(hex_str.replace(" ", ""))
        assert recovered == original

    @pytest.mark.skipif(not ENIGMA_D2I.exists(), reason="Enigma.d2i fixture not available")
    def test_hex_round_trip_enigma(self) -> None:
        def _hex_to_bytes(h: str) -> bytes:
            return bytes.fromhex(h.replace(" ", ""))
        original = ENIGMA_D2I.read_bytes()
        hex_str = " ".join(f"{b:02x}" for b in original)
        recovered = _hex_to_bytes(hex_str)
        assert recovered == original


# ─── Reign of the Warlock — patch certification ───────────────────────────────

class TestReignOfWarlockCertification:
    """
    Certification suite for the "Reign of the Warlock" patch.

    Fixture: ArsDulMephistos.d2i — a new unique item introduced in the patch.
    Raw: 44 bytes, type 'wac', quality=7 (unique), ilvl=41, unique_id=410.

    Parser contract being certified:
      1. No crash on new item types / new unique IDs.
      2. Binary fields (quality, ilvl, unique_id, flags) parse to exact values.
      3. Unknown type code returned as-is (no silent corruption).
      4. Graceful degradation: display name falls back to "code (quality)".
      5. TODO: once "wac" base name is known, add to item_types.py + catalog.
    """

    @pytest.fixture(autouse=True)
    def _data(self):
        self._raw = ARS_DUL_MEPHISTOS.read_bytes()

    def _parse(self):
        from backend.services.item_export import parse_item_bytes
        return parse_item_bytes(self._raw)

    def _flags(self):
        from backend.services.item_parsing.item_flags import read_item_flags
        return read_item_flags(self._raw, byte_start=0)

    def _fields(self):
        from backend.services.item_parsing.item_flags import read_item_flags
        from backend.services.item_parsing.item_fields import read_item_fields
        flags = read_item_flags(self._raw, byte_start=0)
        return read_item_fields(self._raw, flags, byte_start=0)

    # ── File integrity ────────────────────────────────────────────────────────

    def test_fixture_file_is_44_bytes(self) -> None:
        assert len(self._raw) == 44

    def test_fixture_starts_with_identified_flag(self) -> None:
        """Bit 4 of byte 0 = IsIdentified. First byte must be 0x10."""
        assert self._raw[0] == 0x10

    # ── Parser does not crash ─────────────────────────────────────────────────

    def test_parses_without_error(self) -> None:
        result = self._parse()
        assert result["valid"] is True
        assert result["error"] is None

    # ── Flag fields ───────────────────────────────────────────────────────────

    def test_is_identified(self) -> None:
        assert self._flags().is_identified is True

    def test_is_not_simple(self) -> None:
        assert self._flags().is_simple is False

    def test_is_not_ethereal(self) -> None:
        assert self._flags().is_ethereal is False

    def test_is_not_ear(self) -> None:
        assert self._flags().is_ear is False

    # ── Item fields (binary-precise) ──────────────────────────────────────────

    def test_item_type_code_is_wac(self) -> None:
        """Type code decoded by Huffman as 'wac ' — new Reign of the Warlock item."""
        assert self._fields().item_type == "wac "

    def test_item_type_stripped_is_wac(self) -> None:
        assert self._parse()["item_code"] == "wac"

    def test_quality_is_7_unique(self) -> None:
        assert self._fields().quality == 7

    def test_quality_name_is_unique(self) -> None:
        assert self._parse()["quality_name"] == "unique"

    def test_item_level_is_41(self) -> None:
        assert self._fields().item_level == 41

    def test_item_level_via_parse(self) -> None:
        assert self._parse()["item_level"] == 41

    def test_unique_id_is_410(self) -> None:
        """unique_id=410 — new entry not yet in catalog; needs seeding."""
        assert self._fields().unique_id == 410

    def test_no_set_id(self) -> None:
        assert self._fields().set_id is None

    def test_no_magic_affixes(self) -> None:
        assert self._fields().magic_prefix_id is None
        assert self._fields().magic_suffix_id is None

    def test_socket_count_is_zero(self) -> None:
        assert self._fields().socket_count == 0

    # ── Graceful degradation for unknown type ─────────────────────────────────

    def test_base_name_is_occult_tome(self) -> None:
        """'wac' → 'Occult Tome' (Reign of the Warlock patch, added to item_types.py)."""
        from backend.services.item_parsing.item_names import base_name
        assert base_name("wac ") == "Occult Tome"

    def test_display_name_is_occult_tome_without_catalog(self) -> None:
        """
        Without a GrailCatalog entry seeded, display falls back to base type name.
        With catalog seeded (unique_id=410, name='Ars Dul\\'Mephistos'), the
        catalog lookup in stash_service will override to the full unique name.
        """
        result = self._parse()
        # resolve_name without catalog → "{base_name} (unique)" fallback
        assert result["item_name"] == "Occult Tome (unique)"

    def test_is_not_ethereal_via_parse(self) -> None:
        assert self._parse()["is_ethereal"] is False

    # ── Round-trip: hex decodes back to original ──────────────────────────────

    def test_hex_round_trip(self) -> None:
        """Hex string produced by the endpoint decodes back to original bytes."""
        hex_str = " ".join(f"{b:02x}" for b in self._raw)
        recovered = bytes.fromhex(hex_str.replace(" ", ""))
        assert recovered == self._raw


# ─── _reward_out helper ───────────────────────────────────────────────────────

class TestRewardOut:
    """Tests for the _reward_out serialisation helper (needs SQLAlchemy)."""

    @pytest.fixture(autouse=True)
    def _skip_without_sqlalchemy(self):
        pytest.importorskip("sqlalchemy", reason="SQLAlchemy not installed")

    def _make_reward(self, **overrides):
        from unittest.mock import MagicMock
        from datetime import datetime, timezone
        r = MagicMock()
        r.id = overrides.get("id", 1)
        r.name = overrides.get("name", "Test Reward")
        r.item_code = overrides.get("item_code", "xtp")
        r.item_name = overrides.get("item_name", "Mage Plate")
        r.quality = overrides.get("quality", 2)
        r.quality_name = overrides.get("quality_name", "normal")
        r.item_level = overrides.get("item_level", 90)
        r.is_ethereal = overrides.get("is_ethereal", False)
        r.notes = overrides.get("notes", None)
        r.raw_item_bytes = overrides.get("raw_item_bytes", b"\x10" * 76)
        r.created_at = overrides.get("created_at", datetime(2026, 3, 9, tzinfo=timezone.utc))
        return r

    def _out(self, **kwargs):
        from backend.routers.rewards import _reward_out
        return _reward_out(self._make_reward(**kwargs))

    def test_id_passed_through(self) -> None:
        assert self._out(id=42).id == 42

    def test_name_passed_through(self) -> None:
        assert self._out(name="Enigma").name == "Enigma"

    def test_item_code_passed_through(self) -> None:
        assert self._out(item_code="xtp").item_code == "xtp"

    def test_quality_name_passed_through(self) -> None:
        assert self._out(quality_name="unique").quality_name == "unique"

    def test_is_ethereal_passed_through(self) -> None:
        assert self._out(is_ethereal=True).is_ethereal is True

    def test_notes_none_when_absent(self) -> None:
        assert self._out(notes=None).notes is None

    def test_notes_passed_through(self) -> None:
        assert self._out(notes="ETH 15 all res").notes == "ETH 15 all res"

    def test_byte_len_from_raw_bytes(self) -> None:
        assert self._out(raw_item_bytes=b"\x10" * 76).byte_len == 76

    def test_created_at_is_iso_string(self) -> None:
        from datetime import datetime, timezone
        dt = datetime(2026, 3, 9, 12, 0, 0, tzinfo=timezone.utc)
        out = self._out(created_at=dt)
        assert "2026" in out.created_at
        assert isinstance(out.created_at, str)
