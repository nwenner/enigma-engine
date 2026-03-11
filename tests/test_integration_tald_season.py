from __future__ import annotations

"""
Integration test: full season flow with the real Tald character file.

Character: Tald (Warlock, level 88, SC, all 15 acts cleared across Normal/NM/Hell)

Phase 1 — Milestone detection
  Call check_season_milestones() with Tald.d2s and verify all 17 non-gold
  achievements are created with the correct scope (character vs account).

Phase 2 — Gold vault milestone
  Seed a 2.5M GoldVault balance, call check_gold_milestones(), verify the
  18th achievement is created.

Phase 3 — Sequential reward claims
  Claim all 18 rewards back-to-back against a real stash file in tmp_path.
  After every single claim, re-parse the stash and assert tab 5 has grown
  by exactly one item. This exercises the backup → insert → round-trip →
  write chain that claim_reward() follows.

Infrastructure
  - SQLite in-memory DB (same driver as production; create_all handles schema)
  - Real Tald.d2s fixture (real binary parse, no mocks)
  - Real stash fixture with tab 5 cleared to a blank starting state
  - Only backend.config.get_settings is patched (to redirect file paths to
    tmp_path so the test is self-contained)

To run (inside Docker):
  docker run --rm -v $(pwd):/app -w /app enigma-engine-enigma-engine \\
      python3 -m pytest tests/test_integration_tald_season.py -v
"""

import shutil
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("sqlalchemy", reason="SQLAlchemy not installed — run inside Docker")
pytest.importorskip("aiosqlite", reason="aiosqlite not installed — run inside Docker")

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from backend.models import (
    Base, Season, SeasonMilestone, SeasonAchievement,
    BackupSnapshot, GoldVault,
)


# ─── Fixture paths ────────────────────────────────────────────────────────────

TALD_D2S = Path(__file__).parent / "fixtures" / "Tald.d2s"
STASH_FIXTURE = Path(__file__).parent / "item_parsing" / "fixtures" / "ModernSharedStashSoftCoreV2.d2i"

# Sentinel value used for account-scoped achievements
_SENTINEL = "(Season)"


# ─── Milestone spec ───────────────────────────────────────────────────────────
# (name, milestone_type, scope, level_target, numeric_target, reward_label)

MILESTONE_SPECS: list[tuple] = [
    ("Level 50",             "level",                  "character", 50,  None,        "Jah Rune"),
    ("Level 80",             "level",                  "account",   80,  None,        "Treachery (Merc)"),
    ("Gold Vault 2.5M",      "gold_vault",             "account",   None, 2_500_000,  "Bulwark (Merc)"),
    ("Andariel (Normal)",    "cleared_act1_normal",    "account",   None, None,        "Insight (Merc)"),
    ("Duriel (Normal)",      "cleared_act2_normal",    "character", None, None,        "Spirit Sword"),
    ("Mephisto (Normal)",    "cleared_act3_normal",    "account",   None, None,        "Spirit Shield"),
    ("Diablo (Normal)",      "cleared_act4_normal",    "character", None, None,        "Enigma"),
    ("Baal (Normal)",        "cleared_act5_normal",    "account",   None, None,        "Harlequin Crest"),
    ("Andariel (Nightmare)", "cleared_act1_nightmare", "character", None, None,        "Arachnid Mesh"),
    ("Duriel (Nightmare)",   "cleared_act2_nightmare", "account",   None, None,        "The Stone of Jordan"),
    ("Mephisto (Nightmare)", "cleared_act3_nightmare", "character", None, None,        "Horazon's Legacy"),
    ("Diablo (Nightmare)",   "cleared_act4_nightmare", "account",   None, None,        "Diablo's Horn"),
    ("Baal (Nightmare)",     "cleared_act5_nightmare", "character", None, None,        "Mephisto's Brain"),
    ("Andariel (Hell)",      "cleared_act1_hell",      "account",   None, None,        "Key of Destruction"),
    ("Duriel (Hell)",        "cleared_act2_hell",      "character", None, None,        "Key of Hate"),
    ("Mephisto (Hell)",      "cleared_act3_hell",      "account",   None, None,        "Baal's Eye"),
    ("Diablo (Hell)",        "cleared_act4_hell",      "character", None, None,        "Key of Terror"),
    ("Baal (Hell)",          "cleared_act5_hell",      "account",   None, None,        "Gheed's Fortune"),
]

# Character-scoped milestones (scope="character") — Tald triggers all of these
_CHAR_SCOPED_NAMES = {
    name for name, _, scope, *_ in MILESTONE_SPECS if scope == "character"
}
# Expected: Level 50, Duriel Normal, Diablo Normal, Andariel NM, Mephisto NM,
#           Baal NM, Duriel Hell, Diablo Hell  →  8 total
_EXPECTED_CHAR_ACHIEVEMENTS = 8

# Account-scoped non-gold milestones — Tald triggers all of these too
_EXPECTED_ACCT_ACHIEVEMENTS = 9   # Level 80 + 8 boss kills (account-scoped)

# Gold vault (triggered separately after depositing 2.5M)
_EXPECTED_TOTAL_ACHIEVEMENTS = 18


# ─── Integration test ─────────────────────────────────────────────────────────

async def test_tald_full_season_integration(tmp_path: Path) -> None:
    """
    Full integration: season setup → milestone detection → gold vault →
    sequential reward claims for all 18 milestones.
    """
    from backend.services.seasons_service import (
        check_season_milestones,
        check_gold_milestones,
        claim_reward,
    )
    from backend.services.item_parsing import parse_stash, serialize_stash
    from backend.services.item_parsing.stash_format import remove_items_from_page

    # ── 0. Verify fixture files are present ───────────────────────────────────
    assert TALD_D2S.exists(), f"Tald.d2s fixture not found at {TALD_D2S}"
    assert STASH_FIXTURE.exists(), f"Stash fixture not found at {STASH_FIXTURE}"

    # ── 1. In-memory database ─────────────────────────────────────────────────
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session = async_sessionmaker(engine, expire_on_commit=False)()

    try:
        # ── 2. Season setup ───────────────────────────────────────────────────
        season_start = datetime(2026, 3, 11, tzinfo=timezone.utc)
        season = Season(
            name="Season 1: Tald Integration Test",
            status="active",
            started_at=season_start,
            created_at=season_start,
        )
        session.add(season)
        await session.flush()  # populate season.id before creating milestones

        # Extract a small valid item (rune, 11 bytes) from the stash fixture
        # to use as reward bytes for every milestone.  The test validates the
        # claim FLOW and item count, not the specific item identity.
        fixture_stash = parse_stash(STASH_FIXTURE, hardcore=False)
        tab0_item0 = fixture_stash.pages[0].items[0]
        reward_bytes = bytes(
            fixture_stash.pages[0].raw_bytes[tab0_item0.byte_start:tab0_item0.byte_end]
        )

        ms_rows: list[SeasonMilestone] = []
        for i, (name, ms_type, scope, level_target, numeric_target, reward_label) in enumerate(MILESTONE_SPECS):
            ms = SeasonMilestone(
                season_id=season.id,
                name=name,
                milestone_type=ms_type,
                scope=scope,
                level_target=level_target,
                numeric_target=numeric_target,
                reward_item_bytes=reward_bytes,
                reward_item_name=reward_label,
                sort_order=i,
            )
            session.add(ms)
            ms_rows.append(ms)

        await session.commit()

        # ── 3. Phase 1: milestone detection with Tald ─────────────────────────
        #
        # Tald: Warlock, lvl 88, SC, all 15 acts cleared.
        # Expected: 17 achievements (every milestone except gold_vault).
        await check_season_milestones(
            session=session,
            downloaded=[{"filename": "Tald.d2s", "local_part": TALD_D2S}],
        )

        result = await session.execute(select(SeasonAchievement))
        achievements_after_checkin = result.scalars().all()

        assert len(achievements_after_checkin) == 17, (
            f"Phase 1: expected 17 achievements after check-in, "
            f"got {len(achievements_after_checkin)}"
        )

        char_achievements = [a for a in achievements_after_checkin if a.character_name == "Tald"]
        acct_achievements = [a for a in achievements_after_checkin if a.character_name == _SENTINEL]

        assert len(char_achievements) == _EXPECTED_CHAR_ACHIEVEMENTS, (
            f"Phase 1: expected {_EXPECTED_CHAR_ACHIEVEMENTS} character-scoped "
            f"achievements (character_name='Tald'), got {len(char_achievements)}"
        )
        assert len(acct_achievements) == _EXPECTED_ACCT_ACHIEVEMENTS, (
            f"Phase 1: expected {_EXPECTED_ACCT_ACHIEVEMENTS} account-scoped "
            f"achievements (character_name='(Season)'), got {len(acct_achievements)}"
        )

        # None should be claimed yet
        assert all(a.claimed_at is None for a in achievements_after_checkin), (
            "Phase 1: no achievements should be claimed at this point"
        )

        # ── 4. Phase 1b: idempotency check ───────────────────────────────────
        # Running detection again must NOT create duplicate achievements.
        await check_season_milestones(
            session=session,
            downloaded=[{"filename": "Tald.d2s", "local_part": TALD_D2S}],
        )
        result = await session.execute(select(SeasonAchievement))
        still_17 = result.scalars().all()
        assert len(still_17) == 17, (
            f"Phase 1b (idempotency): re-running detection created duplicates; "
            f"now have {len(still_17)} achievements"
        )

        # ── 5. Phase 2: gold vault milestone ─────────────────────────────────
        vault = GoldVault(hardcore=False, amount=2_500_000)
        session.add(vault)
        await session.commit()

        await check_gold_milestones(session)

        result = await session.execute(select(SeasonAchievement))
        all_achievements = result.scalars().all()

        assert len(all_achievements) == _EXPECTED_TOTAL_ACHIEVEMENTS, (
            f"Phase 2: expected {_EXPECTED_TOTAL_ACHIEVEMENTS} achievements after gold vault, "
            f"got {len(all_achievements)}"
        )

        gold_achievement = next(
            (a for a in all_achievements if a.character_name == _SENTINEL
             and a.milestone_id in {ms.id for ms in ms_rows if ms.milestone_type == "gold_vault"}),
            None,
        )
        assert gold_achievement is not None, "Phase 2: gold vault achievement not found"

        # ── 6. Phase 2b: gold vault idempotency ──────────────────────────────
        await check_gold_milestones(session)
        result = await session.execute(select(SeasonAchievement))
        still_18 = result.scalars().all()
        assert len(still_18) == 18, (
            f"Phase 2b (idempotency): re-running gold vault check created a duplicate; "
            f"now have {len(still_18)} achievements"
        )

        # ── 7. Phase 3: sequential reward claims ─────────────────────────────
        # Create a snapshot directory in tmp_path with the stash fixture but
        # tab 5 cleared to empty — this is the "portal tab" for item delivery.
        snap_dir = tmp_path / "snap"
        snap_dir.mkdir()
        stash_path = snap_dir / "ModernSharedStashSoftCoreV2.d2i"

        clean_stash = parse_stash(STASH_FIXTURE, hardcore=False)
        tab5 = clean_stash.pages[4]
        clean_stash.pages[4] = remove_items_from_page(tab5, list(range(len(tab5.items))))
        stash_path.write_bytes(serialize_stash(clean_stash))

        initial_tab5_count = len(parse_stash(stash_path, hardcore=False).pages[4].items)
        assert initial_tab5_count == 0, (
            f"Phase 3 setup: expected empty tab 5, found {initial_tab5_count} items"
        )

        # BackupSnapshot record pointing to snap_dir
        snap = BackupSnapshot(
            source_machine="pc",
            snapshot_path="snap",          # relative to cfg.data_dir
            file_count=1,
            characters=[],
            label="manual",
            created_at=datetime.now(timezone.utc),
        )
        session.add(snap)
        await session.commit()

        # Config mock: redirect data_dir and backups_dir to tmp_path
        (tmp_path / "backups" / "pc").mkdir(parents=True)
        cfg = MagicMock()
        cfg.data_dir = tmp_path
        cfg.backups_dir = tmp_path / "backups"

        ms_by_id = {ms.id: ms for ms in ms_rows}

        # Patch at both the source module and backup_manager's already-bound reference.
        # backup_manager imports get_settings at module level, so if it was imported
        # before this test runs (e.g. in a full suite run) its reference is already
        # bound to the real function and patching backend.config alone doesn't reach it.
        with patch("backend.config.get_settings", return_value=cfg), \
             patch("backend.services.backup_manager.get_settings", return_value=cfg):
            for i, ach in enumerate(all_achievements):
                milestone_name = ms_by_id.get(ach.milestone_id, MagicMock(name="?")).name

                await claim_reward(session, ach.id)

                # Re-parse stash after every claim and verify count grew by 1
                current_stash = parse_stash(stash_path, hardcore=False)
                current_tab5_count = len(current_stash.pages[4].items)
                expected_count = i + 1

                assert current_tab5_count == expected_count, (
                    f"Phase 3 claim {i + 1}/18 ('{milestone_name}'): "
                    f"expected {expected_count} item(s) in tab 5, "
                    f"got {current_tab5_count}"
                )

        # ── 8. All achievements marked claimed ────────────────────────────────
        result = await session.execute(select(SeasonAchievement))
        final_achievements = result.scalars().all()

        unclaimed = [a for a in final_achievements if a.claimed_at is None]
        assert not unclaimed, (
            f"Phase 3: {len(unclaimed)} achievement(s) still unclaimed after full run: "
            + ", ".join(
                ms_by_id.get(a.milestone_id, MagicMock(name="?")).name
                for a in unclaimed
            )
        )

        # Final sanity: 18 items in tab 5
        final_stash = parse_stash(stash_path, hardcore=False)
        assert len(final_stash.pages[4].items) == _EXPECTED_TOTAL_ACHIEVEMENTS, (
            f"Phase 3 final: expected {_EXPECTED_TOTAL_ACHIEVEMENTS} items in tab 5, "
            f"got {len(final_stash.pages[4].items)}"
        )

    finally:
        await session.close()
        await engine.dispose()
