from __future__ import annotations

from pathlib import Path

from backend.services.item_parsing import ParsedStash, parse_stash, serialize_stash

FIXTURE_SC = Path(__file__).parent / "fixtures" / "ModernSharedStashSoftCoreV2.d2i"


def test_page_count(stash: ParsedStash) -> None:
    """Modern stash always has 6 pages (5 tabs + 1 terminal page)."""
    assert len(stash.pages) == 6


def test_gold_is_non_negative(stash: ParsedStash) -> None:
    assert stash.gold >= 0


def test_hardcore_flag(stash: ParsedStash) -> None:
    assert stash.hardcore is False


def test_round_trip_identity(stash: ParsedStash) -> None:
    """Serialize → parse must give bit-for-bit identical bytes."""
    original = FIXTURE_SC.read_bytes()
    serialized = serialize_stash(stash)
    assert serialized == original, (
        f"Round-trip mismatch: original={len(original)} bytes, "
        f"serialized={len(serialized)} bytes"
    )


def test_item_counts_non_negative(stash: ParsedStash) -> None:
    for i, page in enumerate(stash.pages):
        assert page.gold >= 0, f"Page {i} gold is negative"
        assert len(page.items) >= 0


def test_total_items(stash: ParsedStash) -> None:
    """Stash has at least some items across all pages."""
    total = sum(len(p.items) for p in stash.pages)
    assert total > 0, "Expected at least one item in fixture stash"
