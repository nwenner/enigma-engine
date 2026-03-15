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

# stat 107 item_singleskill — (class_id, local_skill_id) → skill name
# Sourced from data/excel_full/skills.txt, charclass column, in row order (0-indexed per class).
_CLASS_SKILL_NAMES: dict[int, dict[int, str]] = {
    0: {  # Amazon
        0: "Magic Arrow", 1: "Fire Arrow", 2: "Inner Sight", 3: "Critical Strike",
        4: "Jab", 5: "Cold Arrow", 6: "Multiple Shot", 7: "Dodge",
        8: "Power Strike", 9: "Poison Javelin", 10: "Exploding Arrow", 11: "Slow Missiles",
        12: "Avoid", 13: "Impale", 14: "Lightning Bolt", 15: "Ice Arrow",
        16: "Guided Arrow", 17: "Penetrate", 18: "Charged Strike", 19: "Plague Javelin",
        20: "Strafe", 21: "Immolation Arrow", 22: "Dopplezon", 23: "Evade",
        24: "Fend", 25: "Freezing Arrow", 26: "Valkyrie", 27: "Pierce",
        28: "Lightning Strike", 29: "Lightning Fury",
    },
    1: {  # Sorceress
        0: "Fire Bolt", 1: "Warmth", 2: "Charged Bolt", 3: "Ice Bolt",
        4: "Frozen Armor", 5: "Inferno", 6: "Static Field", 7: "Telekinesis",
        8: "Frost Nova", 9: "Ice Blast", 10: "Blaze", 11: "Fire Ball",
        12: "Nova", 13: "Lightning", 14: "Shiver Armor", 15: "Fire Wall",
        16: "Enchant", 17: "Chain Lightning", 18: "Teleport", 19: "Glacial Spike",
        20: "Meteor", 21: "Thunder Storm", 22: "Energy Shield", 23: "Blizzard",
        24: "Chilling Armor", 25: "Fire Mastery", 26: "Hydra", 27: "Lightning Mastery",
        28: "Frozen Orb", 29: "Cold Mastery",
    },
    2: {  # Necromancer
        0: "Amplify Damage", 1: "Teeth", 2: "Bone Armor", 3: "Skeleton Mastery",
        4: "Raise Skeleton", 5: "Dim Vision", 6: "Weaken", 7: "Poison Dagger",
        8: "Corpse Explosion", 9: "Clay Golem", 10: "Iron Maiden", 11: "Terror",
        12: "Bone Wall", 13: "Golem Mastery", 14: "Raise Skeletal Mage", 15: "Confuse",
        16: "Life Tap", 17: "Poison Explosion", 18: "Bone Spear", 19: "BloodGolem",
        20: "Attract", 21: "Decrepify", 22: "Bone Prison", 23: "Summon Resist",
        24: "IronGolem", 25: "Lower Resist", 26: "Poison Nova", 27: "Bone Spirit",
        28: "FireGolem", 29: "Revive",
    },
    3: {  # Paladin
        0: "Sacrifice", 1: "Smite", 2: "Might", 3: "Prayer",
        4: "Resist Fire", 5: "Holy Bolt", 6: "Holy Fire", 7: "Thorns",
        8: "Defiance", 9: "Resist Cold", 10: "Zeal", 11: "Charge",
        12: "Blessed Aim", 13: "Cleansing", 14: "Resist Lightning", 15: "Vengeance",
        16: "Blessed Hammer", 17: "Concentration", 18: "Holy Freeze", 19: "Vigor",
        20: "Conversion", 21: "Holy Shield", 22: "Holy Shock", 23: "Sanctuary",
        24: "Meditation", 25: "Fist of the Heavens", 26: "Fanaticism", 27: "Conviction",
        28: "Redemption", 29: "Salvation",
    },
    4: {  # Barbarian
        0: "Bash", 1: "Blade Mastery", 2: "Axe Mastery", 3: "Mace Mastery",
        4: "Howl", 5: "Find Potion", 6: "Leap", 7: "Double Swing",
        8: "Pole Arm Mastery", 9: "Throwing Mastery", 10: "Spear Mastery", 11: "Taunt",
        12: "Shout", 13: "Stun", 14: "Double Throw", 15: "Increased Stamina",
        16: "Find Item", 17: "Leap Attack", 18: "Concentrate", 19: "Iron Skin",
        20: "Battle Cry", 21: "Frenzy", 22: "Increased Speed", 23: "Battle Orders",
        24: "Grim Ward", 25: "Whirlwind", 26: "Berserk", 27: "Natural Resistance",
        28: "War Cry", 29: "Battle Command",
    },
    5: {  # Druid
        0: "Raven", 1: "Plague Poppy", 2: "Werewolf", 3: "Shape Shifting",
        4: "Firestorm", 5: "Oak Sage", 6: "Summon Spirit Wolf", 7: "Werebear",
        8: "Molten Boulder", 9: "Arctic Blast", 10: "Cycle of Life", 11: "Feral Rage",
        12: "Maul", 13: "Eruption", 14: "Cyclone Armor", 15: "Heart of Wolverine",
        16: "Summon Fenris", 17: "Rabies", 18: "Fire Claws", 19: "Twister",
        20: "Vines", 21: "Hunger", 22: "Shock Wave", 23: "Volcano",
        24: "Tornado", 25: "Spirit of Barbs", 26: "Summon Grizzly", 27: "Fury",
        28: "Armageddon", 29: "Hurricane",
    },
    6: {  # Assassin
        0: "Fire Trauma", 1: "Claw Mastery", 2: "Psychic Hammer", 3: "Tiger Strike",
        4: "Dragon Talon", 5: "Shock Field", 6: "Blade Sentinel", 7: "Quickness",
        8: "Fists of Fire", 9: "Dragon Claw", 10: "Charged Bolt Sentry", 11: "Wake of Fire Sentry",
        12: "Weapon Block", 13: "Cloak of Shadows", 14: "Cobra Strike", 15: "Blade Fury",
        16: "Fade", 17: "Shadow Warrior", 18: "Claws of Thunder", 19: "Dragon Tail",
        20: "Lightning Sentry", 21: "Inferno Sentry", 22: "Mind Blast", 23: "Blades of Ice",
        24: "Dragon Flight", 25: "Death Sentry", 26: "Blade Shield", 27: "Venom",
        28: "Shadow Master", 29: "Royal Strike",
    },
    7: {  # Warlock (charclass="war" in skills.txt)
        0: "Summon Goatman", 1: "Demonic Mastery", 2: "Death Mark", 3: "Summon Tainted",
        4: "Summon Defiler", 5: "Blood Oath", 6: "Engorge", 7: "Blood Boil",
        8: "Consume", 9: "Bind Demon", 10: "Levitate", 11: "Eldritch Blast",
        12: "Hex Bane", 13: "Hex Siphon", 14: "Psychic Ward", 15: "Echoing Strike",
        16: "Hex Purge", 17: "Blade Warp", 18: "Cleave", 19: "Mirrored Blades",
        20: "Sigil Lethargy", 21: "Ring of Fire", 22: "Miasma Bolt", 23: "Sigil Rancor",
        24: "Enhanced Entropy", 25: "Flame Wave", 26: "Miasma Chains", 27: "Sigil Death",
        28: "Apocalypse", 29: "Abyss",
    },
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
            # param (9 bits): bits 0-5 = local skill_id, bits 6-8 = class_id
            skill_id = p & 0x3F
            class_id = (p >> 6) & 0x7
            class_name = _CLASS_NAMES.get(class_id, f"Class {class_id}")
            skill_name = _CLASS_SKILL_NAMES.get(class_id, {}).get(skill_id)
            if skill_name:
                lines.append(f"+{v} to {skill_name}")
            else:
                lines.append(f"+{v} to [Skill {skill_id}] ({class_name})")
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
