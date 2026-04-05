"""
Unit and integration tests for magic/rare item name resolution.

Unit tests exercise item_names.py directly with known inputs so they don't
depend on the stash fixture and run instantly.

Integration tests scan the parsed stash fixture and assert that named-quality
items (magic/rare/set/unique/crafted) never fall back to generic labels like
"Small Charm (magic)" — i.e. every named item has a real resolved name.
"""
from __future__ import annotations

import pytest

from backend.services.item_parsing import ParsedItem, ParsedStash
from backend.services.item_parsing.item_names import (
    _charm_prefix_name,
    _magic_name,
    _rare_name,
    base_name,
    resolve_name,
)
from backend.services.item_parsing.tables.rare_names import RARE_NAMES
from backend.services.item_parsing.tables.unique_set_names import UNIQUE_NAMES, SET_NAMES


# ─── helpers ──────────────────────────────────────────────────────────────────

def _all_items(stash: ParsedStash) -> list[ParsedItem]:
    return [item for page in stash.pages for item in page.items]

_FALLBACK_SUFFIXES = (" (magic)", " (rare)", " (crafted)", " (set)", " (unique)")


# ─── base_name ────────────────────────────────────────────────────────────────

class TestBaseName:
    def test_known_types(self):
        assert base_name("cm1 ") == "Small Charm"
        assert base_name("cm2 ") == "Large Charm"
        assert base_name("cm3 ") == "Grand Charm"
        assert base_name("rin ") == "Ring"
        assert base_name("amu ") == "Amulet"

    def test_strips_whitespace(self):
        # base_name strips the code before lookup
        assert base_name("rin ") == base_name("rin")

    def test_unknown_returns_none(self):
        assert base_name("zzzz") is None


# ─── _magic_name ──────────────────────────────────────────────────────────────

class TestMagicName:
    def test_prefix_and_suffix(self):
        # prefix 96 = "Viridian", suffix 61 = "of Balance", base = "Small Charm"
        result = _magic_name(96, 61, "cm1 ")
        assert result == "Viridian Small Charm of Balance"

    def test_prefix_only(self):
        # prefix 85 = "Tangerine", no suffix
        result = _magic_name(85, None, "cm1 ")
        assert result == "Tangerine Small Charm"

    def test_suffix_only(self):
        # no prefix, suffix 4 = "of Life"
        result = _magic_name(None, 4, "cm1 ")
        assert result == "Small Charm of Life"

    def test_unknown_ids_return_none(self):
        # Neither ID is in the tables → no name can be formed
        result = _magic_name(99999, 99999, "cm1 ")
        assert result is None

    def test_prefix_unknown_suffix_known(self):
        # Unknown prefix, known suffix — suffix alone produces a name
        result = _magic_name(99999, 4, "cm1 ")
        assert result == "Small Charm of Life"

    def test_prefix_known_suffix_unknown(self):
        # Known prefix, unknown suffix — prefix alone produces a name
        result = _magic_name(85, 99999, "cm1 ")
        assert result == "Tangerine Small Charm"

    def test_ring(self):
        # prefix 64 = "Prismatic", suffix 61 = "of Balance", base = "Ring"
        result = _magic_name(64, 61, "rin ")
        assert result == "Prismatic Ring of Balance"

    def test_both_none_returns_none(self):
        result = _magic_name(None, None, "cm1 ")
        assert result is None


# ─── _rare_name ───────────────────────────────────────────────────────────────

class TestRareName:
    def test_both_words_known(self):
        # 162 = "Blood", 161 = "Skull"
        result = _rare_name(162, 161)
        assert result == "Blood Skull"

    def test_word1_missing_returns_word2_only(self):
        # name1 not in table — only word2 visible
        result = _rare_name(99999, 161)
        assert result == "Skull"

    def test_word2_missing_returns_word1_only(self):
        result = _rare_name(162, 99999)
        assert result == "Blood"

    def test_both_missing_returns_none(self):
        result = _rare_name(99999, 99999)
        assert result is None

    def test_d2r_patch_additions(self):
        # Entries confirmed from user-reported in-game items
        assert RARE_NAMES[210] == "Turn"    # "Wraith Turn" ring
        assert RARE_NAMES[226] == "Beads"   # "Blood Beads" ring
        assert RARE_NAMES[242] == "Clasp"   # "Death Clasp" amulet
        assert RARE_NAMES[246] == "Gyre"    # "Wraith Gyre" ring
        assert RARE_NAMES[173] == "Cobalt"  # gloves prefix
        assert RARE_NAMES[184] == "Stone"   # helmet prefix

    def test_wraith_turn_ring(self):
        # rare_name1 from "Wraith" family, rare_name2=210 "Turn"
        result = _rare_name(168, 210)  # 168 = "Shadow"
        assert result == "Shadow Turn"

    def test_blood_beads_ring(self):
        result = _rare_name(162, 226)  # 162 = "Blood", 226 = "Beads"
        assert result == "Blood Beads"

    def test_death_clasp_amulet(self):
        result = _rare_name(167, 242)  # 167 = "Death", 242 = "Clasp"
        assert result == "Death Clasp"


# ─── _charm_prefix_name ───────────────────────────────────────────────────────

class TestCharmPrefixName:
    # Fire resistance (stat 39, save_add=200) — display_val = raw - 200
    def test_fire_resist_crimson(self):
        stat_list = [(39, 0, 5)]   # 5% fire resist → "Crimson"
        assert _charm_prefix_name("cm1 ", stat_list) == "Crimson"

    def test_fire_resist_ruby(self):
        stat_list = [(39, 0, 11)]  # 11% fire resist → "Ruby"
        assert _charm_prefix_name("cm1 ", stat_list) == "Ruby"

    # Lightning resistance (stat 41)
    def test_light_resist_tangerine(self):
        stat_list = [(41, 0, 3)]   # 3% lightning resist → "Tangerine"
        assert _charm_prefix_name("cm1 ", stat_list) == "Tangerine"

    def test_light_resist_amber(self):
        stat_list = [(41, 0, 11)]  # 11% lightning resist → "Amber"
        assert _charm_prefix_name("cm1 ", stat_list) == "Amber"

    # Cold resistance (stat 43)
    def test_cold_resist_azure(self):
        stat_list = [(43, 0, 4)]   # 4% cold resist → "Azure"
        assert _charm_prefix_name("cm1 ", stat_list) == "Azure"

    def test_cold_resist_sapphire(self):
        stat_list = [(43, 0, 10)]  # 10% cold resist → "Sapphire"
        assert _charm_prefix_name("cm1 ", stat_list) == "Sapphire"

    # Poison resistance (stat 45)
    def test_poison_resist_beryl(self):
        stat_list = [(45, 0, 3)]   # 3% poison resist → "Beryl"
        assert _charm_prefix_name("cm1 ", stat_list) == "Beryl"

    def test_poison_resist_emerald(self):
        stat_list = [(45, 0, 10)]  # 10% poison resist → "Emerald"
        assert _charm_prefix_name("cm1 ", stat_list) == "Emerald"

    # Life (stat 7, save_add=32) — display_val = raw - 32
    def test_life_lizards(self):
        stat_list = [(7, 0, 5)]    # +5 life → "Lizard's"
        assert _charm_prefix_name("cm1 ", stat_list) == "Lizard's"

    def test_life_snakes(self):
        stat_list = [(7, 0, 10)]   # +10 life → "Snake's"
        assert _charm_prefix_name("cm1 ", stat_list) == "Snake's"

    def test_life_serpents(self):
        stat_list = [(7, 0, 15)]   # +15 life → "Serpent's"
        assert _charm_prefix_name("cm1 ", stat_list) == "Serpent's"

    # Max damage (stat 22)
    def test_max_damage_jagged(self):
        stat_list = [(22, 0, 1)]   # +1 max damage → "Jagged"
        assert _charm_prefix_name("cm1 ", stat_list) == "Jagged"

    def test_max_damage_serrated(self):
        stat_list = [(22, 0, 3)]   # +3 max damage → "Serrated"
        assert _charm_prefix_name("cm1 ", stat_list) == "Serrated"

    # Min damage (stat 21)
    def test_min_damage_red(self):
        stat_list = [(21, 0, 1)]   # +1 min damage → "Red"
        assert _charm_prefix_name("cm1 ", stat_list) == "Red"

    # Large charm resistance (higher ranges)
    def test_lcha_fire_resist_crimson(self):
        stat_list = [(39, 0, 10)]  # 10% fire resist on grand charm → "Crimson"
        assert _charm_prefix_name("cm3 ", stat_list) == "Crimson"

    def test_lcha_fire_resist_ruby(self):
        stat_list = [(39, 0, 28)]  # 28% fire resist → "Ruby"
        assert _charm_prefix_name("cm3 ", stat_list) == "Ruby"

    # Out-of-range values return None
    def test_value_out_of_range_returns_none(self):
        # 2% fire resist — below all scha ranges (min is 3%)
        stat_list = [(39, 0, 2)]
        assert _charm_prefix_name("cm1 ", stat_list) is None

    # Unknown stat → skip and continue
    def test_skips_unknown_stat(self):
        # Unknown stat first, then known resistance
        stat_list = [(99999, 0, 100), (39, 0, 5)]
        assert _charm_prefix_name("cm1 ", stat_list) == "Crimson"

    # Wrong item type returns None
    def test_non_charm_returns_none(self):
        stat_list = [(39, 0, 5)]
        assert _charm_prefix_name("rin ", stat_list) is None


# ─── resolve_name ─────────────────────────────────────────────────────────────

class TestResolveName:
    def test_magic_charm_with_prefix_and_suffix(self):
        stat_list = [(39, 0, 5)]   # "Crimson" from fire resist
        display, rare = resolve_name(
            item_type="cm1 ", quality=4, is_simple=False, is_ear=False,
            magic_prefix_id=None, magic_suffix_id=4, stat_list=stat_list,
        )
        assert display == "Crimson Small Charm of Life"
        assert rare is None

    def test_magic_non_charm_uses_prefix_table(self):
        # Ring with prefix 64 ("Prismatic") and suffix 61 ("of Balance")
        display, rare = resolve_name(
            item_type="rin ", quality=4, is_simple=False, is_ear=False,
            magic_prefix_id=64, magic_suffix_id=61,
        )
        assert display == "Prismatic Ring of Balance"
        assert rare is None

    def test_magic_fallback_when_ids_unknown(self):
        display, rare = resolve_name(
            item_type="rin ", quality=4, is_simple=False, is_ear=False,
            magic_prefix_id=99999, magic_suffix_id=99999,
        )
        assert display == "Ring (magic)"
        assert rare is None

    def test_rare_with_known_names(self):
        display, rare = resolve_name(
            item_type="rin ", quality=6, is_simple=False, is_ear=False,
            rare_name1=162, rare_name2=161,  # "Blood Skull"
        )
        assert display == "Blood Skull"
        assert rare == "Blood Skull"

    def test_rare_fallback_when_names_unknown(self):
        display, rare = resolve_name(
            item_type="rin ", quality=6, is_simple=False, is_ear=False,
            rare_name1=99999, rare_name2=99999,
        )
        assert display == "Ring (rare)"
        assert rare is None

    def test_simple_item(self):
        # Runes are simple; quality=0
        display, rare = resolve_name(
            item_type="r01 ", quality=0, is_simple=True, is_ear=False,
        )
        assert display == "El Rune"  # from ITEM_TYPES
        assert rare is None

    def test_unique_fallback_without_catalog(self):
        """unique_id not in static table → base name + '(unique)' fallback."""
        display, rare = resolve_name(
            item_type="rin ", quality=7, is_simple=False, is_ear=False,
            unique_id=9999,
        )
        assert display == "Ring (unique)"
        assert rare is None

    def test_unique_resolved_from_static_table(self):
        """unique_id=42 → resolved from UNIQUE_NAMES static table."""
        display, rare = resolve_name(
            item_type="rin ", quality=7, is_simple=False, is_ear=False,
            unique_id=42,
        )
        assert display == UNIQUE_NAMES[42]
        assert rare is None

    def test_set_fallback_without_catalog(self):
        """set_id not in static table → base name + '(set)' fallback."""
        display, rare = resolve_name(
            item_type="amu ", quality=5, is_simple=False, is_ear=False,
            set_id=9999,
        )
        assert display == "Amulet (set)"
        assert rare is None

    def test_set_resolved_from_static_table(self):
        """set_id=10 → resolved from SET_NAMES static table."""
        display, rare = resolve_name(
            item_type="amu ", quality=5, is_simple=False, is_ear=False,
            set_id=10,
        )
        assert display == SET_NAMES[10]
        assert rare is None

    def test_catalog_name_wins(self):
        # catalog_name overrides everything
        display, rare = resolve_name(
            item_type="rin ", quality=7, is_simple=False, is_ear=False,
            unique_id=42, catalog_name="Stone of Jordan",
        )
        assert display == "Stone of Jordan"
        assert rare is None

    def test_d2r_patch_rare_names(self):
        # Verify the D2R-added rare name IDs produce correct display names
        display, _ = resolve_name(
            item_type="rin ", quality=6, is_simple=False, is_ear=False,
            rare_name1=168, rare_name2=246,  # "Shadow" + "Gyre"
        )
        assert display == "Shadow Gyre"

        display, _ = resolve_name(
            item_type="amu ", quality=6, is_simple=False, is_ear=False,
            rare_name1=167, rare_name2=242,  # "Death" + "Clasp"
        )
        assert display == "Death Clasp"


# ─── integration: no named-quality items should fall back ─────────────────────

class TestNoFallbacksInStash:
    """
    Regression tests: once an item is named correctly it should stay named.

    Magic items with prefix/suffix IDs beyond our Classic D2 tables (max prefix
    722, max suffix 786) are skipped — those need D2R-specific affix data and
    are expected to fall back until those tables are extended.

    Rare/crafted names use the unified RARE_NAMES table (extended for D2R) and
    must never fall back.
    """

    def test_no_magic_fallbacks_for_known_ids(self, stash: ParsedStash):
        """
        Magic items whose prefix AND suffix IDs are within our lookup tables
        must not fall back to 'Base (magic)'.

        Items with IDs outside our tables are skipped — those need D2R affix data.
        """
        from backend.services.item_parsing.tables.affixes import (
            MAGIC_PREFIXES,
            MAGIC_SUFFIXES,
        )
        fallbacks = []
        for item in _all_items(stash):
            if item.quality != 4 or not item.display_name.endswith(" (magic)"):
                continue
            # Skip non-charm items where BOTH ids exceed table coverage —
            # those are expected gaps in D2R affix data.
            prefix_known = item.magic_prefix_id is None or item.magic_prefix_id in MAGIC_PREFIXES
            suffix_known = item.magic_suffix_id is None or item.magic_suffix_id in MAGIC_SUFFIXES
            if not (prefix_known or suffix_known):
                continue  # both IDs beyond tables — expected fallback
            # At least one ID is in-table; we should have produced a name.
            fallbacks.append(item)

        if fallbacks:
            details = "\n".join(
                f"  {item.item_type.strip()!r} prefix={item.magic_prefix_id} "
                f"suffix={item.magic_suffix_id} name={item.display_name!r}"
                for item in fallbacks
            )
            pytest.fail(
                f"{len(fallbacks)} magic item(s) with known IDs fell back:\n{details}"
            )

    def test_no_rare_fallbacks(self, stash: ParsedStash):
        """Rare items must display their rare name, never 'Base (rare)'."""
        fallbacks = [
            item for item in _all_items(stash)
            if item.quality == 6 and item.display_name.endswith(" (rare)")
        ]
        if fallbacks:
            details = "\n".join(
                f"  {item.item_type.strip()!r} name={item.display_name!r}"
                for item in fallbacks
            )
            pytest.fail(f"{len(fallbacks)} rare item(s) fell back:\n{details}")

    def test_no_crafted_fallbacks(self, stash: ParsedStash):
        """Crafted items must display their rare name, never 'Base (crafted)'."""
        fallbacks = [
            item for item in _all_items(stash)
            if item.quality == 8 and item.display_name.endswith(" (crafted)")
        ]
        if fallbacks:
            details = "\n".join(
                f"  {item.item_type.strip()!r} name={item.display_name!r}"
                for item in fallbacks
            )
            pytest.fail(f"{len(fallbacks)} crafted item(s) fell back:\n{details}")

    def test_magic_charms_with_resistance_stats_are_named(self, stash: ParsedStash):
        """
        Magic charms whose prefix IDs correspond to resistance prefixes in Classic D2
        must resolve to a real name (Tangerine/Azure/Crimson/Beryl etc.).

        Charms with D2R-specific prefix IDs beyond 722 are skipped — those may give
        stat types not yet in CHARM_PREFIX_TABLE and need further data to resolve.
        """
        from backend.services.item_parsing.tables.affixes import MAGIC_PREFIXES

        # Classic D2 resistance/life/damage prefix IDs that we know we can name.
        # If a charm with one of these IDs still falls back, that's a real bug.
        fallbacks = []
        for item in _all_items(stash):
            if item.quality != 4:
                continue
            if item.item_type.strip() not in ("cm1", "cm2", "cm3"):
                continue
            if not item.display_name.endswith(" (magic)"):
                continue
            # Only flag as a failure if the prefix ID is in our table —
            # i.e. this is a Classic D2 prefix we should be able to name.
            if item.magic_prefix_id in MAGIC_PREFIXES:
                fallbacks.append(item)

        if fallbacks:
            details = "\n".join(
                f"  {item.item_type.strip()!r} prefix_id={item.magic_prefix_id} "
                f"suffix_id={item.magic_suffix_id} name={item.display_name!r}"
                for item in fallbacks
            )
            pytest.fail(
                f"{len(fallbacks)} charm(s) with known prefix IDs fell back:\n{details}"
            )

    def test_unknown_d2r_charm_ids_are_documented(self, stash: ParsedStash):
        """
        Informational test: collect magic charms with D2R-specific prefix IDs
        (beyond Classic D2 tables) so we know what data is still missing.

        This test always passes but prints a summary so it shows up in -v output.
        Add these IDs to MAGIC_PREFIXES / CHARM_PREFIX_TABLE as D2R data becomes
        available.
        """
        from backend.services.item_parsing.tables.affixes import MAGIC_PREFIXES

        unknown = [
            item for item in _all_items(stash)
            if item.quality == 4
            and item.item_type.strip() in ("cm1", "cm2", "cm3")
            and item.display_name.endswith(" (magic)")
            and item.magic_prefix_id not in MAGIC_PREFIXES
        ]
        if unknown:
            summary = ", ".join(
                f"{item.item_type.strip()}(prefix={item.magic_prefix_id},suffix={item.magic_suffix_id})"
                for item in unknown
            )
            pytest.skip(
                f"Skipping — {len(unknown)} charm(s) have D2R-specific IDs not yet in tables: {summary}"
            )


# ─── Static name table tests ────────────────────────────────────────────────

class TestStaticUniqueNames:
    """Tests for UNIQUE_NAMES/SET_NAMES fallback in resolve_name()."""

    def test_unique_name_from_static_table(self):
        """unique_id=0 → 'The Gnasher' without catalog_name."""
        name, _ = resolve_name(
            item_type="hax ", quality=7, is_simple=False, is_ear=False,
            unique_id=0,
        )
        assert name == "The Gnasher"

    def test_unique_name_catalog_takes_priority(self):
        """catalog_name overrides static table."""
        name, _ = resolve_name(
            item_type="hax ", quality=7, is_simple=False, is_ear=False,
            unique_id=0, catalog_name="Custom Catalog Name",
        )
        assert name == "Custom Catalog Name"

    def test_unique_name_unknown_id_falls_back(self):
        """Unknown unique_id falls back to base_name + '(unique)'."""
        name, _ = resolve_name(
            item_type="rin ", quality=7, is_simple=False, is_ear=False,
            unique_id=9999,
        )
        assert "(unique)" in name

    def test_set_name_from_static_table(self):
        """set_id=0 → "Civerb's Ward" without catalog_name."""
        name, _ = resolve_name(
            item_type="lrg ", quality=5, is_simple=False, is_ear=False,
            set_id=0,
        )
        assert name == "Civerb's Ward"

    def test_set_name_catalog_takes_priority(self):
        """catalog_name overrides static table for sets."""
        name, _ = resolve_name(
            item_type="lrg ", quality=5, is_simple=False, is_ear=False,
            set_id=0, catalog_name="Override Set Name",
        )
        assert name == "Override Set Name"

    def test_set_name_unknown_id_falls_back(self):
        """Unknown set_id falls back to base_name + '(set)'."""
        name, _ = resolve_name(
            item_type="lrg ", quality=5, is_simple=False, is_ear=False,
            set_id=9999,
        )
        assert "(set)" in name

    def test_unique_names_table_has_expected_entries(self):
        """Spot-check UNIQUE_NAMES table has known items."""
        assert UNIQUE_NAMES[0] == "The Gnasher"
        assert UNIQUE_NAMES[1] == "Deathspade"
        assert len(UNIQUE_NAMES) > 400

    def test_set_names_table_has_expected_entries(self):
        """Spot-check SET_NAMES table has known items."""
        assert SET_NAMES[0] == "Civerb's Ward"
        assert SET_NAMES[1] == "Civerb's Icon"
        assert len(SET_NAMES) > 100
