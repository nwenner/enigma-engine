from __future__ import annotations

from backend.services.item_parsing import ParsedItem, ParsedStash


def _all_items(stash: ParsedStash) -> list[ParsedItem]:
    return [item for page in stash.pages for item in page.items]


def test_items_have_type_codes(stash: ParsedStash) -> None:
    """Every parsed item must have a 4-char type code."""
    for item in _all_items(stash):
        assert len(item.item_type) == 4, (
            f"Bad item_type {item.item_type!r} — expected 4 chars"
        )


def test_qualities_in_range(stash: ParsedStash) -> None:
    """Quality values must be 0–8."""
    for item in _all_items(stash):
        assert 0 <= item.quality <= 8, (
            f"Quality {item.quality} out of range for item {item.item_type!r}"
        )


def test_unique_items_have_unique_id(stash: ParsedStash) -> None:
    """Unique items (quality=7) must have a unique_id."""
    for item in _all_items(stash):
        if item.quality == 7:
            assert item.unique_id is not None, (
                f"Unique item {item.item_type!r} missing unique_id"
            )


def test_set_items_have_set_id(stash: ParsedStash) -> None:
    """Set items (quality=5) must have a set_id."""
    for item in _all_items(stash):
        if item.quality == 5:
            assert item.set_id is not None, (
                f"Set item {item.item_type!r} missing set_id"
            )


def test_item_levels_in_range(stash: ParsedStash) -> None:
    """Non-simple items must have item_level in 1–127; simple items may be 0."""
    for item in _all_items(stash):
        if not item.is_simple and not item.is_ear:
            assert 1 <= item.item_level <= 127, (
                f"Item {item.item_type!r} has item_level={item.item_level}"
            )


def test_display_names_non_empty(stash: ParsedStash) -> None:
    """Every item must have a non-empty display_name."""
    for item in _all_items(stash):
        assert item.display_name, (
            f"Empty display_name for item_type={item.item_type!r} quality={item.quality}"
        )


def test_runes_are_normal_quality(stash: ParsedStash) -> None:
    """Rune items (r01–r33) are simple items with quality=0."""
    for item in _all_items(stash):
        if item.item_type.strip().startswith("r") and item.item_type.strip()[1:].isdigit():
            assert item.is_simple, (
                f"Rune {item.item_type!r} should be simple"
            )
            assert item.quality == 0, (
                f"Rune {item.item_type!r} should have quality=0, got {item.quality}"
            )


def test_charms_are_not_simple(stash: ParsedStash) -> None:
    """Charm items (cm1/cm2/cm3) are always complex items."""
    for item in _all_items(stash):
        if item.item_type.strip() in ("cm1", "cm2", "cm3"):
            assert not item.is_simple, (
                f"Charm {item.item_type!r} should not be simple"
            )


def test_base_names_for_known_types(stash: ParsedStash) -> None:
    """Well-known item types must resolve to their correct base names."""
    expected = {
        "cm1 ": "Small Charm",
        "cm2 ": "Large Charm",
        "cm3 ": "Grand Charm",
        "rin ": "Ring",
        "amu ": "Amulet",
    }
    for item in _all_items(stash):
        if item.item_type in expected:
            assert item.base_name == expected[item.item_type], (
                f"item_type={item.item_type!r}: expected base_name={expected[item.item_type]!r}, "
                f"got {item.base_name!r}"
            )
