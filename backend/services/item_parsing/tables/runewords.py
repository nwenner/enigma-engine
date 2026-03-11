"""
Runeword ID → name lookup table.

IDs come from the RunewordId field in D2R's Runes.txt.
When a runeword with an unknown ID is scanned, its ID is logged at WARNING level
so the table can be extended from real game data.
"""

# Maps runeword_id (12-bit value stored in item) → runeword name
# IDs verified from D2R Runes.txt RunewordId column.
# Add new entries as you encounter unknown IDs in the logs.
RUNEWORD_NAMES: dict[int, str] = {
    59: "Enigma",
}
