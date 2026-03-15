"""
Item property list reader and formatter.

Reads the binary property list (stats) from a D2R Modern stash item and
returns human-readable strings matching the in-game item tooltip.

Public API:
    read_item_stats(data, prop_bit_start, item_end_bit) -> list[RawStat]
    format_item_stats(stats) -> list[str]
    parse_standalone_stats(item_bytes) -> list[str]   # convenience wrapper
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from .item_fields import read_charm_stats

log = logging.getLogger(__name__)


@dataclass
class RawStat:
    """A single decoded item stat."""
    stat_id: int
    param: int    # save_param_bits decoded (0 if stat has no param)
    value: int    # raw_bits - save_add (the displayed in-game value)


_PROP_SENTINEL = 0x1FF


def read_item_stats(
    data: bytes | bytearray,
    prop_bit_start: int,
    item_end_bit: int,
) -> list[RawStat]:
    """
    Read all stats from a property list starting at prop_bit_start.

    Delegates to read_charm_stats (same bit-walking logic) and wraps
    the results as RawStat dataclasses.
    """
    raw = read_charm_stats(data, prop_bit_start, item_end_bit)
    return [RawStat(stat_id=sid, param=p, value=v) for sid, p, v in raw]


def read_runeword_stats(
    data: bytes | bytearray,
    prop_bit_start: int,
    item_end_bit: int,
) -> list[RawStat]:
    """
    Read runeword stats by scanning for the first 0x1FF sentinel after prop_bit_start
    and reading the property list that begins 9 bits after it.

    Runewords have pre-property fields (armor/durability/sockets) before the sentinel.
    The actual runeword bonus stats always begin 9 bits after the first sentinel found.
    Note: stats from embedded socketed runes (e.g. Tal poison resist, Eth mana regen)
    are not included here — they live in the rune items' own property lists.
    """
    from .bit_reader import BitReader

    for bit_pos in range(prop_bit_start, item_end_bit - 8):
        reader = BitReader(data, bit_pos)
        if reader.read(9) == _PROP_SENTINEL:
            runeword_start = bit_pos + 9
            if runeword_start + 9 <= item_end_bit:
                return read_item_stats(data, runeword_start, item_end_bit)
            break
    return []


# ─── Formatting tables ────────────────────────────────────────────────────────

_CLASS_NAMES: dict[int, str] = {
    0: "Amazon",
    1: "Sorceress",
    2: "Necromancer",
    3: "Paladin",
    4: "Barbarian",
    5: "Druid",
    6: "Assassin",
    7: "Warlock",
}

# stat 107 item_singleskill — global skill ID (from skills.txt *Id column) → (name, class_label)
# class_label is appended as "(ClassName Only)" in the tooltip, matching D2R's display.
# Sourced from data/excel_full/skills.txt; IDs are the *Id column values.
_GLOBAL_SKILL_NAMES: dict[int, tuple[str, str]] = {
    # Amazon (6–35)
    6:  ("Magic Arrow",      "Amazon"),    7:  ("Fire Arrow",         "Amazon"),
    8:  ("Inner Sight",      "Amazon"),    9:  ("Critical Strike",    "Amazon"),
    10: ("Jab",              "Amazon"),    11: ("Cold Arrow",         "Amazon"),
    12: ("Multiple Shot",    "Amazon"),    13: ("Dodge",              "Amazon"),
    14: ("Power Strike",     "Amazon"),    15: ("Poison Javelin",     "Amazon"),
    16: ("Exploding Arrow",  "Amazon"),    17: ("Slow Missiles",      "Amazon"),
    18: ("Avoid",            "Amazon"),    19: ("Impale",             "Amazon"),
    20: ("Lightning Bolt",   "Amazon"),    21: ("Ice Arrow",          "Amazon"),
    22: ("Guided Arrow",     "Amazon"),    23: ("Penetrate",          "Amazon"),
    24: ("Charged Strike",   "Amazon"),    25: ("Plague Javelin",     "Amazon"),
    26: ("Strafe",           "Amazon"),    27: ("Immolation Arrow",   "Amazon"),
    28: ("Dopplezon",        "Amazon"),    29: ("Evade",              "Amazon"),
    30: ("Fend",             "Amazon"),    31: ("Freezing Arrow",     "Amazon"),
    32: ("Valkyrie",         "Amazon"),    33: ("Pierce",             "Amazon"),
    34: ("Lightning Strike", "Amazon"),    35: ("Lightning Fury",     "Amazon"),
    # Sorceress (36–65)
    36: ("Fire Bolt",        "Sorceress"), 37: ("Warmth",             "Sorceress"),
    38: ("Charged Bolt",     "Sorceress"), 39: ("Ice Bolt",           "Sorceress"),
    40: ("Frozen Armor",     "Sorceress"), 41: ("Inferno",            "Sorceress"),
    42: ("Static Field",     "Sorceress"), 43: ("Telekinesis",        "Sorceress"),
    44: ("Frost Nova",       "Sorceress"), 45: ("Ice Blast",          "Sorceress"),
    46: ("Blaze",            "Sorceress"), 47: ("Fire Ball",          "Sorceress"),
    48: ("Nova",             "Sorceress"), 49: ("Lightning",          "Sorceress"),
    50: ("Shiver Armor",     "Sorceress"), 51: ("Fire Wall",          "Sorceress"),
    52: ("Enchant",          "Sorceress"), 53: ("Chain Lightning",    "Sorceress"),
    54: ("Teleport",         "Sorceress"), 55: ("Glacial Spike",      "Sorceress"),
    56: ("Meteor",           "Sorceress"), 57: ("Thunder Storm",      "Sorceress"),
    58: ("Energy Shield",    "Sorceress"), 59: ("Blizzard",           "Sorceress"),
    60: ("Chilling Armor",   "Sorceress"), 61: ("Fire Mastery",       "Sorceress"),
    62: ("Hydra",            "Sorceress"), 63: ("Lightning Mastery",  "Sorceress"),
    64: ("Frozen Orb",       "Sorceress"), 65: ("Cold Mastery",       "Sorceress"),
    # Necromancer (66–95)
    66: ("Amplify Damage",   "Necromancer"), 67: ("Teeth",            "Necromancer"),
    68: ("Bone Armor",       "Necromancer"), 69: ("Skeleton Mastery", "Necromancer"),
    70: ("Raise Skeleton",   "Necromancer"), 71: ("Dim Vision",       "Necromancer"),
    72: ("Weaken",           "Necromancer"), 73: ("Poison Dagger",    "Necromancer"),
    74: ("Corpse Explosion", "Necromancer"), 75: ("Clay Golem",       "Necromancer"),
    76: ("Iron Maiden",      "Necromancer"), 77: ("Terror",           "Necromancer"),
    78: ("Bone Wall",        "Necromancer"), 79: ("Golem Mastery",    "Necromancer"),
    80: ("Raise Skeletal Mage","Necromancer"),81: ("Confuse",          "Necromancer"),
    82: ("Life Tap",         "Necromancer"), 83: ("Poison Explosion", "Necromancer"),
    84: ("Bone Spear",       "Necromancer"), 85: ("BloodGolem",       "Necromancer"),
    86: ("Attract",          "Necromancer"), 87: ("Decrepify",        "Necromancer"),
    88: ("Bone Prison",      "Necromancer"), 89: ("Summon Resist",    "Necromancer"),
    90: ("IronGolem",        "Necromancer"), 91: ("Lower Resist",     "Necromancer"),
    92: ("Poison Nova",      "Necromancer"), 93: ("Bone Spirit",      "Necromancer"),
    94: ("FireGolem",        "Necromancer"), 95: ("Revive",           "Necromancer"),
    # Paladin (96–125)
    96:  ("Sacrifice",          "Paladin"), 97:  ("Smite",           "Paladin"),
    98:  ("Might",              "Paladin"), 99:  ("Prayer",          "Paladin"),
    100: ("Resist Fire",        "Paladin"), 101: ("Holy Bolt",       "Paladin"),
    102: ("Holy Fire",          "Paladin"), 103: ("Thorns",          "Paladin"),
    104: ("Defiance",           "Paladin"), 105: ("Resist Cold",     "Paladin"),
    106: ("Zeal",               "Paladin"), 107: ("Charge",          "Paladin"),
    108: ("Blessed Aim",        "Paladin"), 109: ("Cleansing",       "Paladin"),
    110: ("Resist Lightning",   "Paladin"), 111: ("Vengeance",       "Paladin"),
    112: ("Blessed Hammer",     "Paladin"), 113: ("Concentration",   "Paladin"),
    114: ("Holy Freeze",        "Paladin"), 115: ("Vigor",           "Paladin"),
    116: ("Conversion",         "Paladin"), 117: ("Holy Shield",     "Paladin"),
    118: ("Holy Shock",         "Paladin"), 119: ("Sanctuary",       "Paladin"),
    120: ("Meditation",         "Paladin"), 121: ("Fist of the Heavens","Paladin"),
    122: ("Fanaticism",         "Paladin"), 123: ("Conviction",      "Paladin"),
    124: ("Redemption",         "Paladin"), 125: ("Salvation",       "Paladin"),
    # Barbarian (126–155)
    126: ("Bash",               "Barbarian"), 127: ("Blade Mastery",   "Barbarian"),
    128: ("Axe Mastery",        "Barbarian"), 129: ("Mace Mastery",    "Barbarian"),
    130: ("Howl",               "Barbarian"), 131: ("Find Potion",     "Barbarian"),
    132: ("Leap",               "Barbarian"), 133: ("Double Swing",    "Barbarian"),
    134: ("Pole Arm Mastery",   "Barbarian"), 135: ("Throwing Mastery","Barbarian"),
    136: ("Spear Mastery",      "Barbarian"), 137: ("Taunt",           "Barbarian"),
    138: ("Shout",              "Barbarian"), 139: ("Stun",            "Barbarian"),
    140: ("Double Throw",       "Barbarian"), 141: ("Increased Stamina","Barbarian"),
    142: ("Find Item",          "Barbarian"), 143: ("Leap Attack",     "Barbarian"),
    144: ("Concentrate",        "Barbarian"), 145: ("Iron Skin",       "Barbarian"),
    146: ("Battle Cry",         "Barbarian"), 147: ("Frenzy",          "Barbarian"),
    148: ("Increased Speed",    "Barbarian"), 149: ("Battle Orders",   "Barbarian"),
    150: ("Grim Ward",          "Barbarian"), 151: ("Whirlwind",       "Barbarian"),
    152: ("Berserk",            "Barbarian"), 153: ("Natural Resistance","Barbarian"),
    154: ("War Cry",            "Barbarian"), 155: ("Battle Command",  "Barbarian"),
    # Druid (221–250)
    221: ("Raven",              "Druid"), 222: ("Plague Poppy",      "Druid"),
    223: ("Werewolf",           "Druid"), 224: ("Shape Shifting",    "Druid"),
    225: ("Firestorm",          "Druid"), 226: ("Oak Sage",          "Druid"),
    227: ("Summon Spirit Wolf", "Druid"), 228: ("Werebear",          "Druid"),
    229: ("Molten Boulder",     "Druid"), 230: ("Arctic Blast",      "Druid"),
    231: ("Cycle of Life",      "Druid"), 232: ("Feral Rage",        "Druid"),
    233: ("Maul",               "Druid"), 234: ("Eruption",          "Druid"),
    235: ("Cyclone Armor",      "Druid"), 236: ("Heart of Wolverine","Druid"),
    237: ("Summon Fenris",      "Druid"), 238: ("Rabies",            "Druid"),
    239: ("Fire Claws",         "Druid"), 240: ("Twister",           "Druid"),
    241: ("Vines",              "Druid"), 242: ("Hunger",            "Druid"),
    243: ("Shock Wave",         "Druid"), 244: ("Volcano",           "Druid"),
    245: ("Tornado",            "Druid"), 246: ("Spirit of Barbs",   "Druid"),
    247: ("Summon Grizzly",     "Druid"), 248: ("Fury",              "Druid"),
    249: ("Armageddon",         "Druid"), 250: ("Hurricane",         "Druid"),
    # Assassin (251–280)
    251: ("Fire Trauma",        "Assassin"), 252: ("Claw Mastery",       "Assassin"),
    253: ("Psychic Hammer",     "Assassin"), 254: ("Tiger Strike",        "Assassin"),
    255: ("Dragon Talon",       "Assassin"), 256: ("Shock Field",         "Assassin"),
    257: ("Blade Sentinel",     "Assassin"), 258: ("Quickness",           "Assassin"),
    259: ("Fists of Fire",      "Assassin"), 260: ("Dragon Claw",         "Assassin"),
    261: ("Charged Bolt Sentry","Assassin"), 262: ("Wake of Fire Sentry", "Assassin"),
    263: ("Weapon Block",       "Assassin"), 264: ("Cloak of Shadows",    "Assassin"),
    265: ("Cobra Strike",       "Assassin"), 266: ("Blade Fury",          "Assassin"),
    267: ("Fade",               "Assassin"), 268: ("Shadow Warrior",      "Assassin"),
    269: ("Claws of Thunder",   "Assassin"), 270: ("Dragon Tail",         "Assassin"),
    271: ("Lightning Sentry",   "Assassin"), 272: ("Inferno Sentry",      "Assassin"),
    273: ("Mind Blast",         "Assassin"), 274: ("Blades of Ice",       "Assassin"),
    275: ("Dragon Flight",      "Assassin"), 276: ("Death Sentry",        "Assassin"),
    277: ("Blade Shield",       "Assassin"), 278: ("Venom",               "Assassin"),
    279: ("Shadow Master",      "Assassin"), 280: ("Royal Strike",        "Assassin"),
    # Warlock (373–402)
    373: ("Summon Goatman",  "Warlock"), 374: ("Demonic Mastery",  "Warlock"),
    375: ("Death Mark",      "Warlock"), 376: ("Summon Tainted",   "Warlock"),
    377: ("Summon Defiler",  "Warlock"), 378: ("Blood Oath",       "Warlock"),
    379: ("Engorge",         "Warlock"), 380: ("Blood Boil",       "Warlock"),
    381: ("Consume",         "Warlock"), 382: ("Bind Demon",       "Warlock"),
    383: ("Levitate",        "Warlock"), 384: ("Eldritch Blast",   "Warlock"),
    385: ("Hex Bane",        "Warlock"), 386: ("Hex Siphon",       "Warlock"),
    387: ("Psychic Ward",    "Warlock"), 388: ("Echoing Strike",   "Warlock"),
    389: ("Hex Purge",       "Warlock"), 390: ("Blade Warp",       "Warlock"),
    391: ("Cleave",          "Warlock"), 392: ("Mirrored Blades",  "Warlock"),
    393: ("Sigil Lethargy",  "Warlock"), 394: ("Ring of Fire",     "Warlock"),
    395: ("Miasma Bolt",     "Warlock"), 396: ("Sigil Rancor",     "Warlock"),
    397: ("Enhanced Entropy","Warlock"), 398: ("Flame Wave",       "Warlock"),
    399: ("Miasma Chains",   "Warlock"), 400: ("Sigil Death",      "Warlock"),
    401: ("Apocalypse",      "Warlock"), 402: ("Abyss",            "Warlock"),
}

# stat 188 item_addskill_tab — param low byte = tab_id
_SKILL_TAB_NAMES: dict[int, str] = {
    0:  "Bow & Crossbow",
    1:  "Passive & Magic",
    2:  "Javelin & Spear",
    3:  "Fire Spells",
    4:  "Lightning Spells",
    5:  "Cold Spells",
    6:  "Summoning Spells",
    7:  "Poison & Bone",
    8:  "Curses",
    9:  "Offensive Auras",
    10: "Defensive Auras",
    11: "Combat Skills",
    12: "Warcries",
    13: "Combat Masteries",
    14: "Combat Skills",
    15: "Summoning Skills",
    16: "Shape Shifting",
    17: "Elemental",
    18: "Traps",
    19: "Shadow Disciplines",
    20: "Martial Arts",
}

# stat_id pairs: first stat_id → (second stat_id, format string).
# When both are present, consume both and emit one line.
# {min} = first stat's value, {max} = second stat's value.
_PAIRED_STATS: dict[int, tuple[int, str]] = {
    17: (18, "{min}% Enhanced Damage"),          # maxdamage_pct + mindamage_pct (same value)
    21: (22, "Adds {min}-{max} Damage"),          # mindamage + maxdamage
    23: (24, "Adds {min}-{max} Damage"),          # secondary_mindamage + secondary_maxdamage
    48: (49, "Adds {min}-{max} Fire Damage"),
    50: (51, "Adds {min}-{max} Lightning Damage"),
    52: (53, "Adds {min}-{max} Magic Damage"),
    54: (55, "Adds {min}-{max} Cold Damage"),
    57: (58, "Adds {min}-{max} Poison Damage"),
}

# Stats that are consumed as trailing members of a pair — never display standalone.
_PAIRED_SECONDS: frozenset[int] = frozenset({18, 22, 24, 49, 51, 53, 55, 56, 58, 59})

# Simple stat_id → display template; {v} = value.
# Only include stats common on dropped items (not internal engine stats).
_SIMPLE_TEMPLATES: dict[int, str] = {
    0:   "+{v} to Strength",
    1:   "+{v} to Energy",
    2:   "+{v} to Dexterity",
    3:   "+{v} to Vitality",
    7:   "+{v} to Life",
    9:   "+{v} to Mana",
    11:  "+{v} to Stamina",
    16:  "{v}% Enhanced Defense",
    19:  "+{v} to Attack Rating",
    20:  "{v}% Chance of Blocking",
    25:  "{v}% Damage",
    26:  "+{v} Mana Recovery",
    27:  "+{v}% Mana Recovery",
    28:  "+{v}% Stamina Recovery",
    31:  "+{v} Defense",
    32:  "+{v} Defense vs. Missiles",
    33:  "+{v} Defense vs. Melee",
    34:  "Damage Reduced by {v}",
    35:  "Magic Damage Reduced by {v}",
    36:  "{v}% Damage Reduced",
    37:  "{v}% Magic Resist",
    39:  "+{v}% to Fire Resistance",
    41:  "+{v}% to Lightning Resistance",
    43:  "+{v}% to Cold Resistance",
    45:  "+{v}% to Poison Resistance",
    67:  "{v}% Faster Run/Walk",
    74:  "Replenish Life +{v}",
    75:  "+{v}% Enhanced Durability",
    76:  "+{v}% to Maximum Life",
    77:  "+{v}% to Maximum Mana",
    78:  "Attacker Takes Damage of {v}",
    79:  "{v}% Extra Gold from Monsters",
    80:  "{v}% Better Chance of Getting Magic Items",
    81:  "Knockback",
    85:  "+{v}% to Experience Gained",
    86:  "+{v} Life after each Kill",
    87:  "{v}% Lower Buy/Repair Costs",
    89:  "+{v} to Light Radius",
    91:  "Requirements {v}%",
    93:  "{v}% Increased Attack Speed",
    96:  "{v}% Faster Run/Walk",
    99:  "{v}% Faster Hit Recovery",
    102: "{v}% Faster Block Rate",
    105: "{v}% Faster Cast Rate",
    109: "Curse Resistance +{v}%",
    110: "Poison Length Reduced by {v}%",
    111: "+{v}% Damage to Undead",
    115: "Ignores Target's Defense",
    118: "Half Freeze Duration",
    119: "{v}% Bonus to Attack Rating",
    121: "{v}% Damage to Demons",
    122: "{v}% Damage to Undead",
    127: "+{v} to All Skills",
    128: "Attacker Takes Lightning Damage of {v}",
    132: "+{v} Bone Armor",
    135: "{v}% Chance of Open Wounds",
    136: "{v}% Chance of Crushing Blow",
    138: "+{v} Mana after each Kill",
    139: "+{v} Life after each Demon Kill",
    141: "{v}% Deadly Strike",
    150: "Slows Target by {v}%",
    152: "Indestructible",
    153: "Cannot Be Frozen",
    156: "{v}% Piercing Attack",
    194: "Socketed ({v})",
    208: "+{v}% to Lightning Resistance",    # mod stat (Reign of the Warlock)
    255: "{v}% Find Item",
    385: "{v}% Extra Gold from Monsters",    # mod stat (Reign of the Warlock)
}


def format_item_stats(stats: list[RawStat]) -> list[str]:
    """
    Convert a list of RawStat into human-readable property strings.

    Handles paired damage stats (fire min+max → one line), class/tab skills,
    and simple template-based formatting for ~60 common stat IDs.
    """
    lines: list[str] = []
    consumed: set[int] = set()       # indices already handled

    # Index first occurrence of each stat_id for pairing lookups.
    first_idx: dict[int, int] = {}
    for i, s in enumerate(stats):
        if s.stat_id not in first_idx:
            first_idx[s.stat_id] = i

    for i, s in enumerate(stats):
        if i in consumed:
            continue

        stat_id = s.stat_id
        v = s.value
        p = s.param

        # Skip zero-value stats — if a stat appears in the list, it should be non-zero.
        # Zero values indicate bit-alignment noise or padding.
        _BINARY_STATS = {81, 108, 115, 118, 125, 152, 153}  # stats where value=1 means "true"
        if v == 0 and stat_id not in _BINARY_STATS:
            continue

        # ── Paired damage stats ─────────────────────────────────────────────
        if stat_id in _PAIRED_STATS:
            partner_id, template = _PAIRED_STATS[stat_id]
            if partner_id in first_idx:
                j = first_idx[partner_id]
                consumed.add(j)
                max_v = stats[j].value
                lines.append(template.format(min=v, max=max_v))
            # If partner is missing, silently skip — avoid "[stat X] = Y" noise
            continue

        # Skip stats that trail a consumed pair.
        if stat_id in _PAIRED_SECONDS:
            continue

        # ── Skills ──────────────────────────────────────────────────────────
        if stat_id == 83:   # item_addclassskills
            class_name = _CLASS_NAMES.get(p, f"Class {p}")
            lines.append(f"+{v} to {class_name} Skills")
            continue

        if stat_id == 107:  # item_singleskill
            # param is the global skill ID from skills.txt (*Id column).
            entry = _GLOBAL_SKILL_NAMES.get(p)
            if entry:
                skill_name, class_name = entry
                lines.append(f"+{v} to {skill_name} ({class_name} Only)")
            else:
                lines.append(f"+{v} to [Skill {p}]")
            continue

        if stat_id == 126:  # item_elemskill — elemental class skills
            class_id = p & 0x7
            class_name = _CLASS_NAMES.get(class_id, f"Class {class_id}")
            lines.append(f"+{v} to Elemental Skills ({class_name})")
            continue

        if stat_id == 188:  # item_addskill_tab
            tab_id = p & 0xFF
            tab_name = _SKILL_TAB_NAMES.get(tab_id, f"Skill Tab {tab_id}")
            lines.append(f"+{v} to {tab_name}")
            continue

        # ── On-skill procs (195-201, 204) ───────────────────────────────────
        if stat_id == 204:  # item_charged_skill
            # param (16 bits): low 6 bits = skill_id, bits 6-10 = level
            skill_id = p & 0x3F
            level = (p >> 6) & 0x1F
            # value encodes max_charges * 2^8 + current_charges (approximately)
            charges = v >> 8
            lines.append(f"Level {level} [Skill {skill_id}] ({charges} Charges)")
            continue

        _PROC_EVENTS: dict[int, str] = {
            195: "Striking",
            196: "Kill",
            197: "Death",
            198: "Striking",
            199: "Level-Up",
            201: "Being Struck",
        }
        if stat_id in _PROC_EVENTS:
            skill_id = p & 0x3F
            level = (p >> 6) & 0x1F
            event = _PROC_EVENTS[stat_id]
            lines.append(f"{v}% Chance to Cast Level {level} [Skill {skill_id}] on {event}")
            continue

        # ── Simple template lookup ───────────────────────────────────────────
        template = _SIMPLE_TEMPLATES.get(stat_id)
        if template is not None:
            # For templates starting with "+", avoid "+-N" when value is negative
            formatted = template.format(v=v, p=p)
            if formatted.startswith("+-") or formatted.startswith("+ "):
                formatted = formatted[1:]  # drop leading "+" for negative values
            lines.append(formatted)
            continue

        # Unknown stat — skip silently but log so we can add templates
        log.warning("format_item_stats: unhandled stat_id=%d param=%d value=%d (no display template)", stat_id, p, v)

    return lines


def parse_standalone_stats(item_bytes: bytes | bytearray) -> list[str]:
    """
    Parse and format stats from a standalone item byte buffer.

    Used for VaultItem rows where raw_item_bytes is the item in isolation
    (byte_start=0). Returns [] for simple items, ears, or on any parse error.
    """
    from .item_flags import read_item_flags
    from .item_fields import read_item_fields

    if len(item_bytes) < 7:
        return []
    try:
        flags = read_item_flags(item_bytes, byte_start=0)
        if flags.is_simple or flags.is_ear or flags.is_runeword:
            return []
        fields = read_item_fields(item_bytes, flags, byte_start=0)
        # quality 5 = set items: skip (multiple property lists produce partial/wrong results)
        if fields.prop_bit_start == 0 or fields.quality == 5:
            return []
        stats = read_item_stats(item_bytes, fields.prop_bit_start, len(item_bytes) * 8)
        return format_item_stats(stats)
    except Exception as exc:  # noqa: BLE001
        log.debug("parse_standalone_stats: failed to parse stats: %s", exc)
        return []
