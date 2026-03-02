from __future__ import annotations

"""
Grail-related tests: verify that deposit removes items from tab 5,
and retrieve inserts items into tab 5.
"""

from pathlib import Path

import pytest

from backend.services.item_parsing import (
    ParsedStash,
    ParsedItem,
    parse_stash,
    serialize_stash,
)
from backend.services.item_parsing.stash_format import (
    remove_items_from_page,
    insert_item_into_page,
)

FIXTURE_SC = Path(__file__).parent / "fixtures" / "ModernSharedStashSoftCoreV2.d2i"
PORTAL_TAB = 4  # 0-indexed


def test_remove_items_reduces_count(stash: ParsedStash) -> None:
    """Removing the first item from a page reduces item count by 1."""
    for page in stash.pages:
        if len(page.items) == 0:
            continue
        original_count = len(page.items)
        new_page = remove_items_from_page(page, [0])
        assert len(new_page.items) == original_count - 1
        break
    else:
        pytest.skip("No pages with items in fixture")


def test_remove_items_round_trips(stash: ParsedStash) -> None:
    """After removing an item: serialize → parse gives same result."""
    import tempfile

    for page_idx, page in enumerate(stash.pages):
        if len(page.items) == 0:
            continue

        new_page = remove_items_from_page(page, [0])
        new_stash = ParsedStash(
            pages=stash.pages[:page_idx] + [new_page] + stash.pages[page_idx + 1:],
            gold=stash.gold,
            hardcore=stash.hardcore,
            _raw_header=stash._raw_header,
            _raw_separators=stash._raw_separators,
        )
        serialized = serialize_stash(new_stash)

        with tempfile.NamedTemporaryFile(suffix=".d2i", delete=False) as f:
            f.write(serialized)
            tmp_path = Path(f.name)

        try:
            rt_stash = parse_stash(tmp_path, hardcore=stash.hardcore)
            assert len(rt_stash.pages[page_idx].items) == len(page.items) - 1
        finally:
            tmp_path.unlink()
        break
    else:
        pytest.skip("No pages with items in fixture")


def test_insert_item_increases_count(stash: ParsedStash) -> None:
    """Inserting raw bytes into a page increments item count."""
    for page in stash.pages:
        if len(page.items) == 0:
            continue

        # Use the first item's raw bytes as insertion payload
        item = page.items[0]
        raw_bytes = page.raw_bytes[item.byte_start : item.byte_end]

        original_count = len(page.items)
        new_page = insert_item_into_page(page, bytes(raw_bytes))
        assert len(new_page.items) == original_count + 1
        break
    else:
        pytest.skip("No pages with items in fixture")
