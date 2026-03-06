"""
Rare and crafted item name lookup tables.

D2R uses a single rare_names array for both name words — rare_name1 and
rare_name2 both index into RARE_NAMES (202 entries, indices 0-201).

Source: dschu012/d2s src/data/versions/99_constant_data.ts (D2R version 99).

Replaces the separate Classic D2 LOD RARE_PREFIXES (46 entries) and
RARE_SUFFIXES (155 entries) tables.
"""
from __future__ import annotations

# Single combined table: both rare_name1 and rare_name2 index here.
# Index 0 is unused (null in source). Empty/blank entries are absent.
RARE_NAMES: dict[int, str] = {
    1: "Bite", 2: "Scratch", 3: "Scalpel", 4: "Fang", 5: "Gutter",
    6: "Thirst", 7: "Razor", 8: "Scythe", 9: "Edge", 10: "Saw",
    11: "Splitter", 12: "Cleaver", 13: "Sever", 14: "Sunder", 15: "Rend",
    16: "Mangler", 17: "Slayer", 18: "Reaver", 19: "Spawn", 20: "Gnash",
    21: "Star", 22: "Blow", 23: "Smasher", 24: "Bane",
    # 25: {} empty
    26: "Breaker", 27: "Grinder", 28: "Crack", 29: "Mallet", 30: "Knell",
    31: "Lance", 32: "Spike", 33: "Impaler", 34: "Skewer", 35: "Prod",
    36: "Scourge", 37: "Wand", 38: "Wrack", 39: "Barb", 40: "Needle",
    41: "Dart", 42: "Bolt", 43: "Quarrel", 44: "Fletch", 45: "Flight",
    46: "Nock", 47: "Horn", 48: "Stinger", 49: "Quill", 50: "Goad",
    51: "Branch", 52: "Spire", 53: "Song", 54: "Call", 55: "Cry",
    56: "Spell", 57: "Chant", 58: "Weaver", 59: "Gnarl", 60: "Visage",
    61: "Crest", 62: "Circlet", 63: "Veil", 64: "Hood", 65: "Mask",
    66: "Brow", 67: "Casque", 68: "Visor", 69: "Cowl", 70: "Hide",
    71: "Pelt", 72: "Carapace", 73: "Coat", 74: "Wrap", 75: "Suit",
    76: "Cloak", 77: "Shroud", 78: "Jack", 79: "Mantle", 80: "Guard",
    81: "Badge", 82: "Rock", 83: "Aegis", 84: "Ward", 85: "Tower",
    86: "Shield", 87: "Wing", 88: "Mark", 89: "Emblem", 90: "Hand",
    91: "Fist", 92: "Claw", 93: "Clutches", 94: "Grip", 95: "Grasp",
    96: "Hold", 97: "Touch", 98: "Finger", 99: "Knuckle", 100: "Shank",
    101: "Spur", 102: "Tread", 103: "Stalker", 104: "Greaves", 105: "Blazer",
    106: "Nails", 107: "Trample", 108: "Brogues", 109: "Track", 110: "Slippers",
    111: "Clasp", 112: "Buckle", 113: "Harness", 114: "Lock", 115: "Fringe",
    116: "Winding", 117: "Chain",
    # 118: {} empty
    119: "Lash", 120: "Cord", 121: "Knot", 122: "Circle", 123: "Loop",
    124: "Eye", 125: "Turn", 126: "Spiral", 127: "Coil", 128: "Gyre",
    129: "Band", 130: "Whorl", 131: "Talisman", 132: "Heart", 133: "Noose",
    134: "Necklace", 135: "Collar", 136: "Beads", 137: "Torc", 138: "Gorget",
    # 139: {} empty
    140: "Wood", 141: "Brand", 142: "Bludgeon", 143: "Cudgel", 144: "Loom",
    145: "Harp", 146: "Master", 147: "Bar", 148: "Hew", 149: "Crook",
    150: "Mar", 151: "Shell", 152: "Stake", 153: "Picket", 154: "Pale",
    155: "Flange", 156: "Beast", 157: "Eagle", 158: "Raven", 159: "Viper",
    # 160: {} empty
    161: "Skull", 162: "Blood", 163: "Dread", 164: "Doom", 165: "Grim",
    166: "Bone", 167: "Death", 168: "Shadow", 169: "Storm", 170: "Rune",
    171: "Plague", 172: "Stone",
    173: "Cobalt",  # D2R patch addition; empty in dschu012/d2s v99 source
    174: "Spirit", 175: "Storm", 176: "Demon", 177: "Cruel", 178: "Empyrian",
    179: "Bramble", 180: "Pain", 181: "Loath", 182: "Glyph", 183: "Imp",
    184: "Stone",   # D2R patch addition; empty in dschu012/d2s v99 source
    185: "Hailstone", 186: "Gale", 187: "Dire", 188: "Soul", 189: "Brimstone",
    190: "Corpse", 191: "Carrion", 192: "Armageddon", 193: "Havoc",
    194: "Bitter", 195: "Entropy", 196: "Chaos", 197: "Order", 198: "Rule",
    199: "Warp", 200: "Rift", 201: "Corruption",
    # D2R patch additions beyond the 202-entry dschu012/d2s v99 source:
    210: "Turn",   # rare_name2 from "Wraith Turn" ring
    226: "Beads",  # rare_name2 from "Blood Beads" ring
    242: "Clasp",  # rare_name2 from "Death Clasp" amulet
    246: "Gyre",   # rare_name2 from "Wraith Gyre" ring
}

# Legacy aliases kept for any code that still imports the old names.
# Both now point to the same unified table.
RARE_PREFIXES = RARE_NAMES
RARE_SUFFIXES = RARE_NAMES

# Retained for backward compatibility (old code referenced this)
SKILLTAB_PREFIX_NAMES: dict[int, str] = {
    0: "Combat Skills", 1: "Offensive Auras", 2: "Defensive Auras",
    3: "Bow and Crossbow Skills", 4: "Passive and Magic Skills", 5: "Javelin and Spear Skills",
    6: "Curses", 7: "Poison and Bone Spells", 8: "Necromancer Summoning Spells",
    9: "Fire Skills", 10: "Lightning Skills", 11: "Cold Skills",
    12: "Warcries", 13: "Combat Skills", 14: "Masteries",
    15: "Elemental Skills", 16: "Shape Shifting Skills", 17: "Summoning Skills",
    18: "Traps", 19: "Shadow Disciplines", 20: "Martial Arts",
}
