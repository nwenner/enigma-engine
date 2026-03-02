from __future__ import annotations

import pytest
from pathlib import Path

from backend.services.item_parsing import ParsedStash, parse_stash

FIXTURE_SC = Path(__file__).parent / "fixtures" / "ModernSharedStashSoftCoreV2.d2i"


@pytest.fixture(scope="session")
def stash() -> ParsedStash:
    return parse_stash(FIXTURE_SC, hardcore=False)
