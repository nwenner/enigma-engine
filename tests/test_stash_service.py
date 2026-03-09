from __future__ import annotations

"""
Unit tests for stash_service.fetch_stash_local.

This function was added in the 2026-03-09 refactor: it reads a .d2i stash file
from a local snapshot directory instead of downloading via SFTP.

Strategy:
- Use the real SC fixture for stash parsing (same fixture used by item_parsing tests).
- Mock the SQLAlchemy session so we can test DB-dependent branches
  (vault gold absent, vault gold present) without a real database.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# SQLAlchemy and other backend deps are only available inside Docker.
# Skip this file gracefully when running locally without them.
# To run: docker run --rm -v $(pwd):/app -w /app enigma-engine-enigma-engine python3 -m pytest tests/ -v
pytest.importorskip("sqlalchemy", reason="SQLAlchemy not installed — run tests inside Docker")

from backend.services.stash_service import fetch_stash_local

# Real fixture shared with item_parsing tests
FIXTURE_DIR = Path(__file__).parent / "item_parsing" / "fixtures"
SC_STASH = FIXTURE_DIR / "ModernSharedStashSoftCoreV2.d2i"


# ─── Session helpers ──────────────────────────────────────────────────────────

def _empty_session() -> AsyncMock:
    """
    Session mock where every execute() returns an empty result set.
    Covers: no vault gold row, no catalog entries.
    """
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    result.scalar_one_or_none.return_value = None
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result)
    return session


def _vault_session(gold_amount: int, hardcore: bool = False) -> AsyncMock:
    """
    Session mock where the first execute() returns a GoldVault row with
    the specified amount, and subsequent calls (catalog lookups) return empty.
    """
    vault = MagicMock()
    vault.amount = gold_amount

    vault_result = MagicMock()
    vault_result.scalar_one_or_none.return_value = vault
    vault_result.scalars.return_value.all.return_value = []

    empty_result = MagicMock()
    empty_result.scalar_one_or_none.return_value = None
    empty_result.scalars.return_value.all.return_value = []

    session = AsyncMock()
    # First call → vault gold; subsequent calls → empty catalog results
    session.execute = AsyncMock(side_effect=[vault_result, empty_result, empty_result])
    return session


# ─── Happy-path tests ─────────────────────────────────────────────────────────

class TestFetchStashLocalSuccess:
    async def test_returns_correct_machine(self) -> None:
        result = await fetch_stash_local(
            session=_empty_session(),
            mode="sc",
            local_dir=FIXTURE_DIR,
            source_machine="deck",
        )
        assert result["machine"] == "deck"

    async def test_returns_softcore_flag(self) -> None:
        result = await fetch_stash_local(
            session=_empty_session(),
            mode="sc",
            local_dir=FIXTURE_DIR,
        )
        assert result["hardcore"] is False

    async def test_gold_is_non_negative(self) -> None:
        result = await fetch_stash_local(
            session=_empty_session(),
            mode="sc",
            local_dir=FIXTURE_DIR,
        )
        assert result["gold"] >= 0

    async def test_vault_gold_is_zero_when_no_db_row(self) -> None:
        result = await fetch_stash_local(
            session=_empty_session(),
            mode="sc",
            local_dir=FIXTURE_DIR,
        )
        assert result["vault_gold"] == 0

    async def test_vault_gold_reflects_db_value(self) -> None:
        result = await fetch_stash_local(
            session=_vault_session(gold_amount=5_000_000),
            mode="sc",
            local_dir=FIXTURE_DIR,
        )
        assert result["vault_gold"] == 5_000_000

    async def test_tabs_list_is_non_empty(self) -> None:
        result = await fetch_stash_local(
            session=_empty_session(),
            mode="sc",
            local_dir=FIXTURE_DIR,
        )
        assert len(result["tabs"]) > 0

    async def test_tabs_limited_to_visible_count(self) -> None:
        """fetch_stash_local should only return VISIBLE_TAB_COUNT (5) tabs."""
        from backend.services.stash_service import VISIBLE_TAB_COUNT
        result = await fetch_stash_local(
            session=_empty_session(),
            mode="sc",
            local_dir=FIXTURE_DIR,
        )
        assert len(result["tabs"]) == VISIBLE_TAB_COUNT

    async def test_each_tab_has_required_fields(self) -> None:
        result = await fetch_stash_local(
            session=_empty_session(),
            mode="sc",
            local_dir=FIXTURE_DIR,
        )
        for tab in result["tabs"]:
            assert "index" in tab
            assert "item_count" in tab
            assert "items" in tab
            assert tab["item_count"] == len(tab["items"])

    async def test_tab_indices_are_sequential(self) -> None:
        result = await fetch_stash_local(
            session=_empty_session(),
            mode="sc",
            local_dir=FIXTURE_DIR,
        )
        indices = [t["index"] for t in result["tabs"]]
        assert indices == list(range(len(indices)))

    async def test_items_have_required_fields(self) -> None:
        result = await fetch_stash_local(
            session=_empty_session(),
            mode="sc",
            local_dir=FIXTURE_DIR,
        )
        required = {
            "page_item_index", "name", "base_item", "quality",
            "quality_name", "unique_id", "set_id", "is_ear",
            "is_simple", "item_level", "is_ethereal", "properties",
        }
        for tab in result["tabs"]:
            for item in tab["items"]:
                missing = required - item.keys()
                assert not missing, f"Item missing fields: {missing}"

    async def test_source_machine_defaults_to_unknown(self) -> None:
        result = await fetch_stash_local(
            session=_empty_session(),
            mode="sc",
            local_dir=FIXTURE_DIR,
            # no source_machine kwarg
        )
        assert result["machine"] == "unknown"

    async def test_total_items_is_positive(self) -> None:
        """The fixture stash has at least one item."""
        result = await fetch_stash_local(
            session=_empty_session(),
            mode="sc",
            local_dir=FIXTURE_DIR,
        )
        total = sum(t["item_count"] for t in result["tabs"])
        assert total > 0


# ─── Error handling ───────────────────────────────────────────────────────────

class TestFetchStashLocalErrors:
    async def test_raises_file_not_found_for_missing_dir(self, tmp_path: Path) -> None:
        """A directory with no .d2i file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="not found in snapshot"):
            await fetch_stash_local(
                session=_empty_session(),
                mode="sc",
                local_dir=tmp_path,  # empty temp dir
            )

    async def test_raises_file_not_found_for_nonexistent_dir(self) -> None:
        """A completely absent directory raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            await fetch_stash_local(
                session=_empty_session(),
                mode="sc",
                local_dir=Path("/does/not/exist"),
            )

    async def test_sc_mode_looks_for_sc_filename(self, tmp_path: Path) -> None:
        """Mode 'sc' looks for the softcore file, not the hardcore one."""
        # Put only the HC file in the dir
        import shutil
        hc_src = FIXTURE_DIR / "ModernSharedStashSoftCoreV2.d2i"
        # Rename it as HC to ensure SC lookup fails
        (tmp_path / "ModernSharedStashHardCoreV2.d2i").write_bytes(hc_src.read_bytes())

        with pytest.raises(FileNotFoundError, match="SoftCore"):
            await fetch_stash_local(
                session=_empty_session(),
                mode="sc",
                local_dir=tmp_path,
            )

    async def test_hc_mode_looks_for_hc_filename(self, tmp_path: Path) -> None:
        """Mode 'hc' looks for the hardcore file, not the softcore one."""
        sc_src = FIXTURE_DIR / "ModernSharedStashSoftCoreV2.d2i"
        (tmp_path / "ModernSharedStashSoftCoreV2.d2i").write_bytes(sc_src.read_bytes())

        with pytest.raises(FileNotFoundError, match="HardCore"):
            await fetch_stash_local(
                session=_empty_session(),
                mode="hc",
                local_dir=tmp_path,
            )


# ─── Parity with fetch_stash return shape ────────────────────────────────────

class TestReturnShapeParity:
    """
    fetch_stash_local must return the same dict shape as fetch_stash so the
    router can treat them interchangeably.
    """

    async def test_top_level_keys(self) -> None:
        result = await fetch_stash_local(
            session=_empty_session(),
            mode="sc",
            local_dir=FIXTURE_DIR,
        )
        assert set(result.keys()) == {"machine", "hardcore", "gold", "vault_gold", "tabs"}

    async def test_quality_name_is_string(self) -> None:
        result = await fetch_stash_local(
            session=_empty_session(),
            mode="sc",
            local_dir=FIXTURE_DIR,
        )
        for tab in result["tabs"]:
            for item in tab["items"]:
                assert isinstance(item["quality_name"], str)
                assert item["quality_name"] != ""

    async def test_properties_is_list(self) -> None:
        result = await fetch_stash_local(
            session=_empty_session(),
            mode="sc",
            local_dir=FIXTURE_DIR,
        )
        for tab in result["tabs"]:
            for item in tab["items"]:
                assert isinstance(item["properties"], list)
