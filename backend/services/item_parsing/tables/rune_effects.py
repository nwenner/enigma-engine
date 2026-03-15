"""
Rune socket effect lookup tables for D2R Modern stash item display.

Data sourced from data/excel_full/gems.txt and runes.txt.
"""
from __future__ import annotations


# ─── Runeword rune compositions ───────────────────────────────────────────────
# runeword_id → tuple of rune type codes in socket order.
# Formula: runeword_id = runes.txt line number (1-based, header=1) + 25
RUNEWORD_RUNES: dict[int, tuple[str, ...]] = {
    27:  ("r08", "r09", "r07"),           # Ancients' Pledge
    29:  ("r15", "r13", "r08"),           # Authority
    30:  ("r30", "r03", "r22", "r23", "r17"),  # Beast
    32:  ("r10", "r16", "r04"),           # Black
    34:  ("r12", "r22", "r22"),           # Bone
    35:  ("r08", "r27", "r29", "r05"),    # Bramble
    36:  ("r31", "r28", "r23", "r25"),    # Brand
    37:  ("r26", "r15", "r01", "r02", "r33", "r05"),  # Breath of the Dying
    39:  ("r11", "r08", "r23", "r24", "r27"),  # Call to Arms
    40:  ("r14", "r22", "r30", "r24"),    # Chains of Honor
    42:  ("r19", "r27", "r22"),           # Chaos
    43:  ("r13", "r22", "r03"),           # Crescent Moon
    46:  ("r15", "r01", "r26", "r09", "r25"),  # Death
    48:  ("r20", "r24", "r16"),           # Delirium
    51:  ("r26", "r28", "r30", "r31", "r18"),  # Destruction
    52:  ("r15", "r27", "r22", "r28", "r32"),  # Doom
    53:  ("r29", "r28", "r12"),           # Dragon
    55:  ("r16", "r31", "r21"),           # Dream
    56:  ("r13", "r22", "r10"),           # Duress
    57:  ("r03", "r07", "r11"),           # Edge
    59:  ("r31", "r06", "r30"),           # Enigma
    60:  ("r21", "r08", "r12"),           # Enlightenment
    62:  ("r11", "r30", "r24", "r12", "r29"),  # Eternity
    63:  ("r26", "r27", "r24", "r14"),    # Exile
    64:  ("r27", "r31", "r20", "r02"),    # Faith
    65:  ("r19", "r27", "r09", "r31"),    # Famine
    66:  ("r04", "r21", "r26"),           # Flickering Flame
    67:  ("r01", "r12", "r14", "r28"),    # Fortitude
    70:  ("r31", "r25", "r05"),           # Fury
    71:  ("r19", "r22", "r21"),           # Gloom
    73:  ("r05", "r03", "r28", "r23", "r08"),  # Hand of Justice
    74:  ("r29", "r32", "r11", "r28"),    # Harmony
    75:  ("r03", "r06", "r12", "r18"),    # Heart of the Oak
    77:  ("r18", "r26", "r21", "r10"),    # Ice
    80:  ("r05", "r08", "r09", "r07"),    # Infinity
    81:  ("r11", "r01", "r06", "r03", "r12"),  # Innocence
    85:  ("r11", "r13", "r31", "r28"),    # Insight
    86:  ("r30", "r23", "r30", "r24"),    # Jealousy
    88:  ("r08", "r03", "r07", "r12"),    # King's Grace
    91:  ("r11", "r08", "r10"),           # Lawbringer
    92:  ("r23", "r22", "r25", "r19"),    # Leaf
    95:  ("r31", "r23", "r31", "r29", "r31", "r30"),  # Last Wish
    97:  ("r11", "r20", "r18"),           # Lionheart
    98:  ("r03", "r08"),                  # Lore
    100: ("r15", "r17", "r19"),           # Loyalty
    101: ("r09", "r12"),                  # Melody
    106: ("r06", "r01", "r05"),           # Myth
    107: ("r13", "r18", "r04"),           # Nadir
    108: ("r17", "r16", "r12", "r05"),    # Oath
    109: ("r32", "r13", "r25", "r10", "r06"),  # Obsession
    112: ("r15", "r11", "r04"),           # Pattern
    113: ("r04", "r03"),                  # Peace
    116: ("r13", "r21", "r23", "r17"),    # Phoenix
    117: ("r15", "r18", "r10", "r05", "r19"),  # Plague
    119: ("r33", "r24", "r20", "r17", "r16", "r04"),  # Pride
    120: ("r14", "r09", "r02", "r20"),    # Principle
    122: ("r07", "r09", "r10"),           # Prudence
    123: ("r13", "r10", "r11"),           # Punishment
    124: ("r20", "r18", "r01", "r02"),    # Question
    128: ("r26", "r26", "r28", "r31"),    # Rift
    131: ("r32", "r13", "r22"),           # Sanctuary
    134: ("r32", "r29", "r16", "r28"),    # Shadow
    135: ("r08", "r25", "r02"),           # Smoke
    137: ("r23", "r03"),                  # Splendor
    141: ("r04", "r12", "r06"),           # Steel
    142: ("r09", "r23", "r06"),           # Sting
    145: ("r13", "r05"),                  # Stone
    146: ("r15", "r18", "r20", "r25"),    # Storm
    147: ("r18", "r18", "r23"),           # Strength
    151: ("r14", "r02", "r15", "r24", "r03", "r26"),  # Silence
    153: ("r04", "r17"),                  # Smoke (alt)
    155: ("r07", "r10", "r09", "r11"),    # Spirit (shield)
    156: ("r05", "r17"),                  # Starlight
    158: ("r07", "r05"),                  # Stealth
    159: ("r03", "r01"),                  # Steel (alt)
    162: ("r13", "r22", "r21", "r17"),    # Tempest
    164: ("r11", "r03"),                  # Tradition
    173: ("r13", "r10", "r20"),           # Treachery
    176: ("r19", "r16", "r06", "r02", "r01", "r15"),  # Unbending Will
    179: ("r07", "r14", "r23"),           # Venom
    182: ("r10", "r33", "r24"),           # Void
    185: ("r20", "r18", "r03"),           # Wealth
    187: ("r14", "r16"),                  # Whisper
    188: ("r29", "r01"),                  # Wind
    190: ("r21", "r06", "r02"),           # Wisdom
    193: ("r21", "r17", "r30", "r23"),    # Wrath
    196: ("r13", "r18", "r02"),           # Hustle (armor)
    197: ("r13", "r18", "r02"),           # Hustle (weapon)
    198: ("r23", "r25", "r11"),           # Mosaic
    199: ("r16", "r32", "r19"),           # Metamorphosis
    200: ("r13", "r16", "r09"),           # Ground
    201: ("r13", "r16", "r08"),           # Temper
    202: ("r13", "r16", "r10"),           # Hearth
    203: ("r13", "r16", "r07"),           # Cure
    204: ("r13", "r16", "r12"),           # Bulwark
    205: ("r24", "r08", "r16"),           # Coven
    206: ("r14", "r25"),                  # Vigilance
    207: ("r11", "r13", "r27"),           # Ritual
}


# ─── Rune socket effects ───────────────────────────────────────────────────────
# rune_code → {"weapon": [...], "armor": [...], "shield": [...]}
# "armor" covers helms, body armor, boots, gloves, belts (gems.txt "helm" column).
# Each effect is a (stat_id, display_str) tuple.
# stat_id: D2R ItemStatCost stat ID used to deduplicate against binary-parsed stats.
#   If the binary property list already has this stat_id, the effect is skipped to
#   avoid doubling (some runewords store socket effects in the property list).
#   None = always include regardless (stat_id unknown or not applicable).
# Values sourced directly from gems.txt (min == max for all rune effects except
# weapon damage ranges which use min-max format directly in the string).
_Effect = tuple[int | None, str]

_RUNE_EFFECTS: dict[str, dict[str, list[_Effect]]] = {
    "r01": {  # El
        "weapon": [(89, "+1 to Light Radius"), (19, "+50 to Attack Rating")],
        "armor":  [(89, "+1 to Light Radius"), (31, "+15 Defense")],
        "shield": [(89, "+1 to Light Radius"), (31, "+15 Defense")],
    },
    "r02": {  # Eld
        "weapon": [(None, "+50% to Attack Rating vs. Undead"), (None, "+75% Damage to Undead")],
        "armor":  [(None, "Slows Stamina Drain by 15%")],
        "shield": [(20, "7% Chance of Blocking")],
    },
    "r03": {  # Tir
        "weapon": [(138, "+2 Mana after each Kill")],
        "armor":  [(138, "+2 Mana after each Kill")],
        "shield": [(138, "+2 Mana after each Kill")],
    },
    "r04": {  # Nef
        "weapon": [(81, "Knockback")],
        "armor":  [(32, "+30 Defense vs. Missiles")],
        "shield": [(32, "+30 Defense vs. Missiles")],
    },
    "r05": {  # Eth
        "weapon": [(None, "-25 to Monster Defense per Hit")],
        "armor":  [(27, "Regenerate Mana 15%")],
        "shield": [(27, "Regenerate Mana 15%")],
    },
    "r06": {  # Ith
        "weapon": [(22, "+9 to Maximum Damage")],
        "armor":  [(None, "15% Damage Taken Goes to Mana")],
        "shield": [(None, "15% Damage Taken Goes to Mana")],
    },
    "r07": {  # Tal
        "weapon": [(None, "Adds 154 Poison Damage over 5 Seconds")],
        "armor":  [(45, "+30% to Poison Resistance")],
        "shield": [(45, "+35% to Poison Resistance")],
    },
    "r08": {  # Ral
        "weapon": [(None, "Adds 5-30 Fire Damage")],
        "armor":  [(39, "+30% to Fire Resistance")],
        "shield": [(39, "+35% to Fire Resistance")],
    },
    "r09": {  # Ort
        "weapon": [(None, "Adds 1-50 Lightning Damage")],
        "armor":  [(41, "+30% to Lightning Resistance")],
        "shield": [(41, "+35% to Lightning Resistance")],
    },
    "r10": {  # Thul
        "weapon": [(None, "Adds 3-14 Cold Damage")],
        "armor":  [(43, "+30% to Cold Resistance")],
        "shield": [(43, "+35% to Cold Resistance")],
    },
    "r11": {  # Amn
        "weapon": [(None, "7% Life Stolen per Hit")],
        "armor":  [(78, "Attacker Takes Damage of 14")],
        "shield": [(78, "Attacker Takes Damage of 14")],
    },
    "r12": {  # Sol
        "weapon": [(21, "+9 to Minimum Damage")],
        "armor":  [(34, "Damage Reduced by 7")],
        "shield": [(34, "Damage Reduced by 7")],
    },
    "r13": {  # Shael
        "weapon": [(93, "20% Increased Attack Speed")],
        "armor":  [(99, "20% Faster Hit Recovery")],
        "shield": [(102, "20% Faster Block Rate")],
    },
    "r14": {  # Dol
        "weapon": [(None, "Hit Causes Monster to Flee 32%")],
        "armor":  [(74, "Regenerate Life +7")],
        "shield": [(74, "Regenerate Life +7")],
    },
    "r15": {  # Hel
        "weapon": [(91, "Requirements -20%")],
        "armor":  [(91, "Requirements -15%")],
        "shield": [(91, "Requirements -15%")],
    },
    "r16": {  # Io
        "weapon": [(3, "+10 to Vitality")],
        "armor":  [(3, "+10 to Vitality")],
        "shield": [(3, "+10 to Vitality")],
    },
    "r17": {  # Lum
        "weapon": [(1, "+10 to Energy")],
        "armor":  [(1, "+10 to Energy")],
        "shield": [(1, "+10 to Energy")],
    },
    "r18": {  # Ko
        "weapon": [(2, "+10 to Dexterity")],
        "armor":  [(2, "+10 to Dexterity")],
        "shield": [(2, "+10 to Dexterity")],
    },
    "r19": {  # Fal
        "weapon": [(0, "+10 to Strength")],
        "armor":  [(0, "+10 to Strength")],
        "shield": [(0, "+10 to Strength")],
    },
    "r20": {  # Lem
        "weapon": [(79, "75% Extra Gold from Monsters")],
        "armor":  [(79, "50% Extra Gold from Monsters")],
        "shield": [(79, "50% Extra Gold from Monsters")],
    },
    "r21": {  # Pul
        "weapon": [(None, "+100% to Attack Rating vs. Demons"), (121, "+75% Damage to Demons")],
        "armor":  [(16, "30% Enhanced Defense")],
        "shield": [(16, "30% Enhanced Defense")],
    },
    "r22": {  # Um
        "weapon": [(135, "25% Chance of Open Wounds")],
        "armor":  [(None, "+15 to All Resistances")],
        "shield": [(None, "+22 to All Resistances")],
    },
    "r23": {  # Mal
        "weapon": [(None, "Prevent Monster Heal")],
        "armor":  [(35, "Magic Damage Reduced by 7")],
        "shield": [(35, "Magic Damage Reduced by 7")],
    },
    "r24": {  # Ist
        "weapon": [(80, "30% Better Chance of Getting Magic Items")],
        "armor":  [(80, "25% Better Chance of Getting Magic Items")],
        "shield": [(80, "25% Better Chance of Getting Magic Items")],
    },
    "r25": {  # Gul
        "weapon": [(119, "20% Bonus to Attack Rating")],
        "armor":  [(None, "+5% to Maximum Poison Resistance")],
        "shield": [(None, "+5% to Maximum Poison Resistance")],
    },
    "r26": {  # Vex
        "weapon": [(None, "7% Mana Stolen per Hit")],
        "armor":  [(None, "+5% to Maximum Fire Resistance")],
        "shield": [(None, "+5% to Maximum Fire Resistance")],
    },
    "r27": {  # Ohm
        "weapon": [(None, "50% Enhanced Damage")],
        "armor":  [(None, "+5% to Maximum Cold Resistance")],
        "shield": [(None, "+5% to Maximum Cold Resistance")],
    },
    "r28": {  # Lo
        "weapon": [(141, "20% Deadly Strike")],
        "armor":  [(None, "+5% to Maximum Lightning Resistance")],
        "shield": [(None, "+5% to Maximum Lightning Resistance")],
    },
    "r29": {  # Sur
        "weapon": [(150, "Slows Target by 33%")],
        "armor":  [(77, "+5% to Maximum Mana")],
        "shield": [(9, "+50 to Mana")],
    },
    "r30": {  # Ber
        "weapon": [(136, "20% Chance of Crushing Blow")],
        "armor":  [(36, "8% Damage Reduced")],
        "shield": [(36, "8% Damage Reduced")],
    },
    "r31": {  # Jah
        "weapon": [(115, "Ignores Target's Defense")],
        "armor":  [(76, "+5% to Maximum Life")],
        "shield": [(7, "+50 to Life")],
    },
    "r32": {  # Cham
        "weapon": [(None, "Freeze Target +3")],
        "armor":  [(153, "Cannot Be Frozen")],
        "shield": [(153, "Cannot Be Frozen")],
    },
    "r33": {  # Zod
        "weapon": [(152, "Indestructible")],
        "armor":  [(152, "Indestructible")],
        "shield": [(152, "Indestructible")],
    },
}


# ─── Item type classification ──────────────────────────────────────────────────
# Derived from data/excel_full/itemtypes.txt equivalence chains.
# Items not in either set are classified as "armor" (helms, body armor, boots,
# gloves, belts, charms, jewelry — all use the gems.txt "helm" socket effects).

_WEAPON_TYPES: frozenset[str] = frozenset({
    "2ax", "2hs", "6bs", "6cb", "6cs", "6hb", "6hx", "6l7", "6lb", "6ls",
    "6lw", "6lx", "6mx", "6rx", "6s7", "6sb", "6ss", "6sw", "6ws", "72a",
    "72h", "7ar", "7ax", "7b7", "7b8", "7ba", "7bk", "7bl", "7br", "7bs",
    "7bt", "7bw", "7cl", "7cm", "7cr", "7cs", "7dg", "7di", "7fb", "7fc",
    "7fl", "7ga", "7gd", "7gi", "7gl", "7gm", "7gs", "7gw", "7h7", "7ha",
    "7ja", "7kr", "7la", "7ls", "7lw", "7m7", "7ma", "7mp", "7mt", "7o7",
    "7p7", "7pa", "7pi", "7qr", "7qs", "7s7", "7s8", "7sb", "7sc", "7sm",
    "7sp", "7sr", "7ss", "7st", "7ta", "7tk", "7tr", "7ts", "7tw", "7vo",
    "7wa", "7wb", "7wc", "7wd", "7wh", "7wn", "7ws", "7xf", "7yw", "8bs",
    "8cb", "8cs", "8hb", "8hx", "8l8", "8lb", "8ls", "8lw", "8lx", "8mx",
    "8rx", "8s8", "8sb", "8ss", "8sw", "8ws", "92a", "92h", "9ar", "9ax",
    "9b7", "9b8", "9b9", "9ba", "9bk", "9bl", "9br", "9bs", "9bt", "9bw",
    "9cl", "9cm", "9cr", "9cs", "9dg", "9di", "9fb", "9fc", "9fl", "9ga",
    "9gd", "9gi", "9gl", "9gm", "9gs", "9gw", "9h9", "9ha", "9ja", "9kr",
    "9la", "9ls", "9lw", "9m9", "9ma", "9mp", "9mt", "9p9", "9pa", "9pi",
    "9qr", "9qs", "9s8", "9s9", "9sb", "9sc", "9sm", "9sp", "9sr", "9ss",
    "9st", "9ta", "9tk", "9tr", "9ts", "9tw", "9vo", "9wa", "9wb", "9wc",
    "9wd", "9wh", "9wn", "9ws", "9xf", "9yw", "am1", "am2", "am3", "am4",
    "am5", "am6", "am7", "am8", "am9", "ama", "amb", "amc", "amd", "ame",
    "amf", "axe", "axf", "bal", "bar", "bax", "bkf", "bld", "brn", "bsd",
    "bst", "bsw", "btl", "btx", "bwn", "cbw", "ces", "clb", "clm", "clw",
    "crs", "cst", "dgr", "dir", "fla", "flb", "flc", "gax", "gis", "gix",
    "glv", "gma", "gsc", "gsd", "gwn", "hal", "hax", "hbw", "hxb", "jav",
    "kri", "ktr", "lax", "lbb", "lbw", "lsd", "lst", "lwb", "lxb", "mac",
    "mau", "mpi", "mst", "mxb", "ob1", "ob2", "ob3", "ob4", "ob5", "ob6",
    "ob7", "ob8", "ob9", "oba", "obb", "obc", "obd", "obe", "obf", "pax",
    "pik", "pil", "qf2", "rxb", "sbb", "sbr", "sbw", "scm", "scp", "scy",
    "skr", "spc", "spr", "spt", "ssd", "ssp", "sst", "swb", "tax", "tkf",
    "tri", "tsp", "vou", "wax", "whm", "wnd", "wrb", "wsc", "wsd", "wsp",
    "wst", "ywn",
})

_SHIELD_TYPES: frozenset[str] = frozenset({
    "bsh", "buc", "gts", "kit", "lrg", "ne1", "ne2", "ne3", "ne4", "ne5",
    "ne6", "ne7", "ne8", "ne9", "nea", "neb", "ned", "nee", "nef", "neg",
    "pa1", "pa2", "pa3", "pa4", "pa5", "pa6", "pa7", "pa8", "pa9", "paa",
    "pab", "pac", "pad", "pae", "paf", "sml", "spk", "tow", "uit", "uml",
    "uow", "upk", "urg", "ush", "uts", "uuc", "wac", "xit", "xml", "xow",
    "xpk", "xrg", "xsh", "xts", "xuc",
})


def get_slot_type(item_type: str) -> str:
    """Return "weapon", "shield", or "armor" for a 4-char item type code."""
    t = item_type.strip()
    if t in _WEAPON_TYPES:
        return "weapon"
    if t in _SHIELD_TYPES:
        return "shield"
    return "armor"


def get_rune_socket_effects(
    runeword_id: int,
    item_type: str,
    existing_stat_ids: frozenset[int] | set[int] = frozenset(),
) -> list[str]:
    """
    Return formatted socket effect strings contributed by embedded runes.

    Uses the runeword's known rune composition (from runes.txt) and the item's
    type code to determine the correct slot (weapon/armor/shield) for each rune's
    socket effect.

    Effects whose stat_id is already in existing_stat_ids are skipped to avoid
    doubling stats that are already in the binary property list. Effects with
    stat_id=None are always included.

    Returns [] for unknown runeword IDs.
    """
    runes = RUNEWORD_RUNES.get(runeword_id)
    if not runes:
        return []
    slot = get_slot_type(item_type)
    effects: list[str] = []
    for rune in runes:
        for stat_id, line in _RUNE_EFFECTS.get(rune, {}).get(slot, []):
            if stat_id is None or stat_id not in existing_stat_ids:
                effects.append(line)
    return effects
