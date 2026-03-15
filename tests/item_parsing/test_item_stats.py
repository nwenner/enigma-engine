"""
Tests for item_stats.py — stat reading and formatting.

Unit tests use synthetic RawStat lists; integration tests parse the fixture stash.
"""
from __future__ import annotations

import pytest
from pathlib import Path

from backend.services.item_parsing.item_stats import (
    RawStat,
    format_item_stats,
    parse_standalone_stats,
    read_item_stats,
)
from backend.services.item_parsing import parse_stash

FIXTURE_SC = Path(__file__).parent / "fixtures" / "ModernSharedStashSoftCoreV2.d2i"


# ─── Unit tests: format_item_stats ────────────────────────────────────────────

class TestFormatSimpleStats:
    def test_resistances(self):
        stats = [
            RawStat(39, 0, 35),   # +35% Fire Res
            RawStat(41, 0, 25),   # +25% Lightning Res
            RawStat(43, 0, 30),   # +30% Cold Res
            RawStat(45, 0, 20),   # +20% Poison Res
        ]
        lines = format_item_stats(stats)
        assert "+35% to Fire Resistance" in lines
        assert "+25% to Lightning Resistance" in lines
        assert "+30% to Cold Resistance" in lines
        assert "+20% to Poison Resistance" in lines

    def test_life_mana(self):
        stats = [RawStat(7, 0, 40), RawStat(9, 0, 25)]
        lines = format_item_stats(stats)
        assert "+40 to Life" in lines
        assert "+25 to Mana" in lines

    def test_all_skills(self):
        lines = format_item_stats([RawStat(127, 0, 2)])
        assert "+2 to All Skills" in lines

    def test_class_skills_sorceress(self):
        lines = format_item_stats([RawStat(83, 1, 2)])  # param=1=Sorceress
        assert "+2 to Sorceress Skills" in lines

    def test_class_skills_amazon(self):
        lines = format_item_stats([RawStat(83, 0, 1)])
        assert "+1 to Amazon Skills" in lines

    def test_fcr_ias_fhr(self):
        stats = [RawStat(105, 0, 20), RawStat(93, 0, 15), RawStat(99, 0, 30)]
        lines = format_item_stats(stats)
        assert "20% Faster Cast Rate" in lines
        assert "15% Increased Attack Speed" in lines
        assert "30% Faster Hit Recovery" in lines

    def test_magic_find(self):
        lines = format_item_stats([RawStat(80, 0, 50)])
        assert "50% Better Chance of Getting Magic Items" in lines

    def test_defense(self):
        lines = format_item_stats([RawStat(31, 0, 150)])
        assert "+150 Defense" in lines

    def test_attributes(self):
        stats = [RawStat(0, 0, 10), RawStat(1, 0, 5), RawStat(2, 0, 8), RawStat(3, 0, 7)]
        lines = format_item_stats(stats)
        assert "+10 to Strength" in lines
        assert "+5 to Energy" in lines
        assert "+8 to Dexterity" in lines
        assert "+7 to Vitality" in lines

    def test_indestructible(self):
        lines = format_item_stats([RawStat(152, 0, 1)])
        assert "Indestructible" in lines

    def test_cannot_be_frozen(self):
        lines = format_item_stats([RawStat(153, 0, 1)])
        assert "Cannot Be Frozen" in lines

    def test_requirements_negative(self):
        # save_add=100, so raw=70 → value=-30 → "Requirements -30%"
        lines = format_item_stats([RawStat(91, 0, -30)])
        assert "Requirements -30%" in lines

    def test_socketed(self):
        lines = format_item_stats([RawStat(194, 0, 4)])
        assert "Socketed (4)" in lines

    def test_extra_gold(self):
        lines = format_item_stats([RawStat(79, 0, 80)])
        assert "80% Extra Gold from Monsters" in lines


class TestFormatPairedStats:
    def test_enhanced_damage(self):
        # stats 17 + 18 both carry the same value; 17 is the leader
        stats = [RawStat(17, 0, 200), RawStat(18, 0, 200)]
        lines = format_item_stats(stats)
        assert "200% Enhanced Damage" in lines
        assert len(lines) == 1  # partner should be consumed

    def test_physical_damage(self):
        stats = [RawStat(21, 0, 5), RawStat(22, 0, 10)]
        lines = format_item_stats(stats)
        assert "Adds 5-10 Damage" in lines
        assert len(lines) == 1

    def test_fire_damage(self):
        stats = [RawStat(48, 0, 15), RawStat(49, 0, 30)]
        lines = format_item_stats(stats)
        assert "Adds 15-30 Fire Damage" in lines

    def test_lightning_damage(self):
        stats = [RawStat(50, 0, 1), RawStat(51, 0, 75)]
        lines = format_item_stats(stats)
        assert "Adds 1-75 Lightning Damage" in lines

    def test_cold_damage(self):
        # stat 55 (cold max) should be consumed as pair; 56 (cold length) is silently skipped
        stats = [RawStat(54, 0, 10), RawStat(55, 0, 20), RawStat(56, 0, 50)]
        lines = format_item_stats(stats)
        assert "Adds 10-20 Cold Damage" in lines
        # cold length (56) should not appear as its own line
        assert not any("Cold" in l and "20" not in l for l in lines)
        assert len(lines) == 1

    def test_poison_damage(self):
        stats = [RawStat(57, 0, 50), RawStat(58, 0, 75), RawStat(59, 0, 100)]
        lines = format_item_stats(stats)
        assert "Adds 50-75 Poison Damage" in lines
        assert len(lines) == 1

    def test_paired_second_alone_is_skipped(self):
        # stat 22 (maxdamage) appearing without 21 should be skipped (it's a _PAIRED_SECONDS)
        lines = format_item_stats([RawStat(22, 0, 10)])
        assert lines == []


class TestFormatSkillStats:
    def test_skill_tab(self):
        # stat 188, tab_id=3 (Fire Spells)
        lines = format_item_stats([RawStat(188, 3, 2)])
        assert "+2 to Fire Spells" in lines

    def test_skill_tab_cold(self):
        lines = format_item_stats([RawStat(188, 5, 1)])
        assert "+1 to Cold Spells" in lines

    def test_skill_tab_unknown(self):
        lines = format_item_stats([RawStat(188, 99, 1)])
        assert "+1 to Skill Tab 99" in lines

    def test_single_skill(self):
        # stat 107, param encodes skill_id (bits 0-5) + class_id (bits 6-8)
        # class_id=1 (Sorceress), skill_id=3 → param = (1<<6)|3 = 67 → Ice Bolt
        lines = format_item_stats([RawStat(107, 67, 3)])
        assert "+3 to Ice Bolt" in lines

    def test_single_skill_unknown_id(self):
        # Unknown skill_id falls back to bracketed format
        # class_id=1 (Sorceress), skill_id=63 → param = (1<<6)|63 = 127
        lines = format_item_stats([RawStat(107, 127, 1)])
        assert "+1 to [Skill 63] (Sorceress)" in lines

    def test_unknown_stat_skipped(self):
        # stat_id not in STAT_TABLE → read_charm_stats stops, so it won't appear at all
        # But if we construct a RawStat manually with an unknown ID not in templates, it should be skipped
        lines = format_item_stats([RawStat(69, 0, 5)])  # unknown template
        assert lines == []

    def test_empty_stats(self):
        assert format_item_stats([]) == []


# ─── Integration tests: real fixture stash ────────────────────────────────────

class TestReadItemStatsFromFixture:
    """Parse real item bytes from the fixture stash and verify stat reading."""

    def _get_non_simple_items(self, stash):
        """Collect all non-simple, non-ear items from the stash."""
        items = []
        for page in stash.pages[:5]:
            for item in page.items:
                if not item.is_simple and not item.is_ear and item.prop_bit_start > 0:
                    items.append((page, item))
        return items

    def test_all_complex_items_have_prop_bit_start(self, stash):
        items = self._get_non_simple_items(stash)
        assert len(items) > 0, "Expected at least one complex item in fixture stash"
        for page, item in items:
            assert item.prop_bit_start > 0, f"prop_bit_start not set for {item.display_name}"

    def test_stats_parseable_without_exception(self, stash):
        """Every complex item's stat list must parse without error."""
        items = self._get_non_simple_items(stash)
        for page, item in items:
            raw_stats = read_item_stats(page.raw_bytes, item.prop_bit_start, item.byte_end * 8)
            formatted = format_item_stats(raw_stats)
            # formatted may be empty (runewords have multiple prop lists; we only read the first)
            assert isinstance(formatted, list)

    def test_goldwrap_has_mf(self, stash):
        """Goldwrap (unique belt, tab 1, unique_id=115) should have MF and extra gold."""
        page = stash.pages[0]
        # Goldwrap's display_name resolves via catalog at service time; match by unique_id instead
        goldwrap = next(
            (item for item in page.items if item.unique_id == 115),
            None,
        )
        assert goldwrap is not None, "Goldwrap (unique_id=115) not found in tab 1"
        assert goldwrap.prop_bit_start > 0
        raw_stats = read_item_stats(page.raw_bytes, goldwrap.prop_bit_start, goldwrap.byte_end * 8)
        formatted = format_item_stats(raw_stats)
        # Goldwrap has Extra Gold and MF as key properties
        assert any("Gold" in line for line in formatted), f"No gold stat in Goldwrap stats: {formatted}"
        assert any("Magic Items" in line for line in formatted), f"No MF in Goldwrap stats: {formatted}"


class TestParseStandaloneStats:
    """Test parse_standalone_stats using bytes extracted from the fixture."""

    def test_simple_item_returns_empty(self, stash):
        """Simple items (runes/gems) should return no stats."""
        # Tir Rune is in tab 1 (first item)
        page = stash.pages[0]
        simple = next((item for item in page.items if item.is_simple), None)
        if simple is None:
            pytest.skip("No simple item found in tab 1")
        item_bytes = bytes(page.raw_bytes[simple.byte_start:simple.byte_end])
        assert parse_standalone_stats(item_bytes) == []

    def test_complex_item_returns_stats(self, stash):
        """A complex non-simple item should return at least some stats when parsed standalone."""
        page = stash.pages[0]
        goldwrap = next(
            (item for item in page.items if item.unique_id == 115),
            None,
        )
        if goldwrap is None:
            pytest.skip("Goldwrap (unique_id=115) not found in fixture")
        item_bytes = bytes(page.raw_bytes[goldwrap.byte_start:goldwrap.byte_end])
        result = parse_standalone_stats(item_bytes)
        assert isinstance(result, list)
        assert len(result) > 0, f"Expected stats from Goldwrap standalone, got: {result}"

    def test_empty_bytes_returns_empty(self):
        assert parse_standalone_stats(b"") == []
        assert parse_standalone_stats(b"\x00\x00\x00") == []
