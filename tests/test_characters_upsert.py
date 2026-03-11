from __future__ import annotations

"""
Unit tests for backend.routers.characters.upsert_characters.

Needs SQLAlchemy — run inside Docker:
  docker run --rm -v $(pwd):/app -w /app enigma-engine-enigma-engine python3 -m pytest tests/ -v
"""

from unittest.mock import AsyncMock, MagicMock, call

import pytest

pytest.importorskip("sqlalchemy", reason="SQLAlchemy not installed — run tests inside Docker")

from backend.routers.characters import upsert_characters


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _make_char_dict(
    filename: str = "hero.d2s",
    name: str = "Hero",
    class_id: int = 3,
    class_name: str = "Paladin",
    level: int = 30,
    hardcore: bool = False,
    ever_died: bool = False,
    expansion: bool = True,
    modified_at: float = 1_000_000.0,
    difficulty_active: int = 0,
) -> dict:
    return {
        "filename": filename,
        "name": name,
        "class_id": class_id,
        "class_name": class_name,
        "level": level,
        "hardcore": hardcore,
        "ever_died": ever_died,
        "expansion": expansion,
        "modified_at": modified_at,
        "difficulty_active": difficulty_active,
        "cleared_normal": difficulty_active >= 1,
        "cleared_nightmare": difficulty_active >= 2,
    }


def _session_returning(scalar_value) -> AsyncMock:
    """
    Returns a session mock whose execute().scalar_one_or_none() returns scalar_value.
    Suitable for a single call.
    """
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar_value
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result)
    session.add = MagicMock()  # session.add is synchronous in SQLAlchemy
    return session


def _session_with_side_effects(values: list) -> AsyncMock:
    """
    Returns a session mock where each successive execute() call returns a result
    whose .scalar_one_or_none() yields the next value from `values`.
    """
    results = []
    for v in values:
        r = MagicMock()
        r.scalar_one_or_none.return_value = v
        results.append(r)

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=results)
    session.add = MagicMock()  # session.add is synchronous in SQLAlchemy
    return session


# ─── New character insertion ──────────────────────────────────────────────────

class TestUpsertNewCharacter:
    async def test_adds_new_character_when_not_found(self) -> None:
        session = _session_returning(None)
        await upsert_characters(session, [_make_char_dict()])
        session.add.assert_called_once()

    async def test_commit_called_at_end(self) -> None:
        session = _session_returning(None)
        await upsert_characters(session, [_make_char_dict()])
        session.commit.assert_called_once()

    async def test_new_character_has_correct_name(self) -> None:
        session = _session_returning(None)
        await upsert_characters(session, [_make_char_dict(name="Frost")])
        added = session.add.call_args[0][0]
        assert added.name == "Frost"

    async def test_new_character_has_correct_level(self) -> None:
        session = _session_returning(None)
        await upsert_characters(session, [_make_char_dict(level=55)])
        added = session.add.call_args[0][0]
        assert added.level == 55

    async def test_new_character_has_correct_difficulty_active(self) -> None:
        session = _session_returning(None)
        await upsert_characters(session, [_make_char_dict(difficulty_active=2)])
        added = session.add.call_args[0][0]
        assert added.difficulty_active == 2

    async def test_difficulty_active_defaults_to_zero_when_missing(self) -> None:
        """A char dict without 'difficulty_active' key → stored as 0."""
        char = _make_char_dict()
        char.pop("difficulty_active")
        session = _session_returning(None)
        await upsert_characters(session, [char])
        added = session.add.call_args[0][0]
        assert added.difficulty_active == 0

    async def test_new_character_filename_set(self) -> None:
        session = _session_returning(None)
        await upsert_characters(session, [_make_char_dict(filename="amazon.d2s")])
        added = session.add.call_args[0][0]
        assert added.filename == "amazon.d2s"

    async def test_new_character_hardcore_flag(self) -> None:
        session = _session_returning(None)
        await upsert_characters(session, [_make_char_dict(hardcore=True)])
        added = session.add.call_args[0][0]
        assert added.hardcore is True

    async def test_new_character_expansion_flag(self) -> None:
        session = _session_returning(None)
        await upsert_characters(session, [_make_char_dict(expansion=False)])
        added = session.add.call_args[0][0]
        assert added.expansion is False


# ─── Existing character updates ───────────────────────────────────────────────

class TestUpsertExistingCharacter:
    def _existing(self, modified_at: float = 500_000.0) -> MagicMock:
        existing = MagicMock()
        existing.modified_at = modified_at
        return existing

    async def test_updates_fields_when_incoming_mtime_greater(self) -> None:
        existing = self._existing(modified_at=500_000.0)
        session = _session_returning(existing)
        await upsert_characters(session, [_make_char_dict(modified_at=999_999.0, level=80)])
        assert existing.level == 80

    async def test_updates_fields_when_incoming_mtime_equal(self) -> None:
        existing = self._existing(modified_at=500_000.0)
        session = _session_returning(existing)
        await upsert_characters(session, [_make_char_dict(modified_at=500_000.0, level=75)])
        assert existing.level == 75

    async def test_updates_difficulty_active(self) -> None:
        existing = self._existing(modified_at=500_000.0)
        session = _session_returning(existing)
        await upsert_characters(
            session, [_make_char_dict(modified_at=999_999.0, difficulty_active=2)]
        )
        assert existing.difficulty_active == 2

    async def test_only_updates_last_updated_at_when_incoming_mtime_older(self) -> None:
        """Stale incoming data → only last_updated_at touched, nothing else."""
        existing = self._existing(modified_at=999_999.0)
        existing.level = 60
        session = _session_returning(existing)
        # incoming is older (lower mtime)
        await upsert_characters(
            session, [_make_char_dict(modified_at=1.0, level=10)]
        )
        # level must NOT be overwritten
        assert existing.level == 60
        # but last_updated_at is always touched
        assert existing.last_updated_at is not None

    async def test_no_add_called_for_existing_char(self) -> None:
        existing = self._existing(500_000.0)
        session = _session_returning(existing)
        await upsert_characters(session, [_make_char_dict(modified_at=999_999.0)])
        session.add.assert_not_called()

    async def test_commit_called_once_for_existing(self) -> None:
        existing = self._existing(500_000.0)
        session = _session_returning(existing)
        await upsert_characters(session, [_make_char_dict(modified_at=999_999.0)])
        session.commit.assert_called_once()


# ─── Multiple characters ──────────────────────────────────────────────────────

class TestUpsertMultipleChars:
    async def test_two_new_chars_both_added(self) -> None:
        chars = [
            _make_char_dict(filename="a.d2s", name="Alpha"),
            _make_char_dict(filename="b.d2s", name="Beta"),
        ]
        session = _session_with_side_effects([None, None])
        await upsert_characters(session, chars)
        assert session.add.call_count == 2

    async def test_commit_called_once_for_multiple(self) -> None:
        chars = [
            _make_char_dict(filename="a.d2s"),
            _make_char_dict(filename="b.d2s"),
        ]
        session = _session_with_side_effects([None, None])
        await upsert_characters(session, chars)
        session.commit.assert_called_once()

    async def test_mixed_new_and_existing(self) -> None:
        existing = MagicMock()
        existing.modified_at = 0.0
        chars = [
            _make_char_dict(filename="new.d2s"),
            _make_char_dict(filename="old.d2s", modified_at=999.0),
        ]
        session = _session_with_side_effects([None, existing])
        await upsert_characters(session, chars)
        # Only the new one triggers add
        session.add.assert_called_once()


# ─── Missing filename key ─────────────────────────────────────────────────────

class TestUpsertSkipsMissingFilename:
    async def test_no_filename_key_skipped(self) -> None:
        char = {"name": "Ghost", "level": 10, "class_id": 0, "class_name": "Amazon"}
        session = AsyncMock()
        await upsert_characters(session, [char])
        session.add.assert_not_called()
        session.execute.assert_not_called()

    async def test_empty_filename_skipped(self) -> None:
        char = _make_char_dict(filename="")
        session = AsyncMock()
        await upsert_characters(session, [char])
        session.add.assert_not_called()

    async def test_commit_still_called_when_all_skipped(self) -> None:
        """Even if every char is skipped, commit is called (consistent behaviour)."""
        char = {"name": "Ghost", "level": 5}
        session = AsyncMock()
        await upsert_characters(session, [char])
        session.commit.assert_called_once()


# ─── difficulty_active field edge cases ──────────────────────────────────────

class TestDifficultyActiveField:
    async def test_difficulty_active_2_stored(self) -> None:
        session = _session_returning(None)
        await upsert_characters(session, [_make_char_dict(difficulty_active=2)])
        added = session.add.call_args[0][0]
        assert added.difficulty_active == 2

    async def test_difficulty_active_1_stored(self) -> None:
        session = _session_returning(None)
        await upsert_characters(session, [_make_char_dict(difficulty_active=1)])
        added = session.add.call_args[0][0]
        assert added.difficulty_active == 1

    async def test_missing_difficulty_active_defaults_zero(self) -> None:
        char = _make_char_dict()
        del char["difficulty_active"]
        session = _session_returning(None)
        await upsert_characters(session, [char])
        added = session.add.call_args[0][0]
        assert added.difficulty_active == 0

    async def test_cleared_normal_in_dict_does_not_cause_error(self) -> None:
        """to_dict() includes cleared_normal/cleared_nightmare; upsert ignores them gracefully."""
        char = _make_char_dict(difficulty_active=1)
        assert "cleared_normal" in char  # sanity check: key exists
        session = _session_returning(None)
        # Should not raise
        await upsert_characters(session, [char])
        session.add.assert_called_once()
