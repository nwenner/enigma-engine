"""
Item type code → (width, height) in stash grid cells.

Sourced from D2R game data (invwidth/invheight columns in Armor.txt / Weapons.txt / Misc.txt).
Unknown types fall back to (1, 1) — renders safely without overlapping neighbours.
"""
from __future__ import annotations

ITEM_DIMENSIONS: dict[str, tuple[int, int]] = {

    # ── Runes (1×1) ────────────────────────────────────────────────────────────
    "r01": (1, 1), "r02": (1, 1), "r03": (1, 1), "r04": (1, 1), "r05": (1, 1),
    "r06": (1, 1), "r07": (1, 1), "r08": (1, 1), "r09": (1, 1), "r10": (1, 1),
    "r11": (1, 1), "r12": (1, 1), "r13": (1, 1), "r14": (1, 1), "r15": (1, 1),
    "r16": (1, 1), "r17": (1, 1), "r18": (1, 1), "r19": (1, 1), "r20": (1, 1),
    "r21": (1, 1), "r22": (1, 1), "r23": (1, 1), "r24": (1, 1), "r25": (1, 1),
    "r26": (1, 1), "r27": (1, 1), "r28": (1, 1), "r29": (1, 1), "r30": (1, 1),
    "r31": (1, 1), "r32": (1, 1), "r33": (1, 1),

    # ── Charms ─────────────────────────────────────────────────────────────────
    "cm1": (1, 1),   # Small Charm
    "cm2": (1, 2),   # Large Charm
    "cm3": (1, 3),   # Grand Charm
    "cs2": (1, 3),   # Crafted Sunder Charm (same size as Grand Charm)

    # ── Jewelry & Misc (1×1) ───────────────────────────────────────────────────
    "rin": (1, 1), "amu": (1, 1), "jew": (1, 1), "cjw": (1, 1),

    # ── Gems: Chipped / Flawed / Normal / Flawless / Perfect (1×1) ────────────
    "gcv": (1, 1), "gfv": (1, 1), "gsv": (1, 1), "gzv": (1, 1), "gpv": (1, 1),
    "gcy": (1, 1), "gfy": (1, 1), "gsy": (1, 1), "gly": (1, 1), "gpy": (1, 1),
    "gcb": (1, 1), "gfb": (1, 1), "gsb": (1, 1), "glb": (1, 1), "gpb": (1, 1),
    "gcg": (1, 1), "gfg": (1, 1), "gsg": (1, 1), "gig": (1, 1), "gpg": (1, 1),
    "glg": (1, 1),  # Flawless Emerald (duplicate entry)
    "gcr": (1, 1), "gfr": (1, 1), "gsr": (1, 1), "glr": (1, 1), "gpr": (1, 1),
    "gcw": (1, 1), "gfw": (1, 1), "gsw": (1, 1), "glw": (1, 1), "gpw": (1, 1),
    "skc": (1, 1), "skf": (1, 1), "sku": (1, 1), "skl": (1, 1), "skz": (1, 1),

    # ── Quest / Keys / Tokens (1×1) ────────────────────────────────────────────
    "key": (1, 1),
    "box": (2, 2),   # Horadric Cube
    "bks": (1, 1),   # Scroll of Inifuss
    "pk1": (1, 1), "pk2": (1, 1), "pk3": (1, 1),
    "bey": (1, 1), "mbr": (1, 1), "dhn": (1, 1),
    "ua1": (1, 1), "ua2": (1, 1), "ua3": (1, 1), "ua4": (1, 1), "ua5": (1, 1),
    "tr1": (1, 1),   # Token of Absolution
    "qf2": (1, 3),   # Khalim's Will (flail-type quest weapon)

    # ── Belts (2×1) ────────────────────────────────────────────────────────────
    # Normal
    "blt": (2, 1), "vbl": (2, 1), "mbl": (2, 1), "tbl": (2, 1), "hbl": (2, 1),
    "lbl": (2, 1),
    # Exceptional
    "zlb": (2, 1), "zvb": (2, 1), "zmb": (2, 1), "ztb": (2, 1), "zhb": (2, 1),
    # Elite
    "ulc": (2, 1), "uvc": (2, 1), "umc": (2, 1), "utc": (2, 1), "uhc": (2, 1),

    # ── Helmets — Normal / Exceptional / Elite (2×2) ───────────────────────────
    "cap": (2, 2), "skp": (2, 2), "hlm": (2, 2), "fhl": (2, 2), "ghm": (2, 2),
    "crn": (2, 2), "msk": (2, 2),
    "xap": (2, 2), "xkp": (2, 2), "xlm": (2, 2), "xhl": (2, 2), "xhm": (2, 2),
    "xrn": (2, 2), "xsk": (2, 2),
    "uap": (2, 2), "ukp": (2, 2), "ulm": (2, 2), "uhl": (2, 2), "uhm": (2, 2),
    "urn": (2, 2), "usk": (2, 2),
    "bhm": (2, 2), "xh9": (2, 2), "uh9": (2, 2),  # Bone Helm / Grim Helm / Bone Visage

    # ── Barbarian Helms (2×2) ──────────────────────────────────────────────────
    "ba1": (2, 2), "ba2": (2, 2), "ba3": (2, 2), "ba4": (2, 2), "ba5": (2, 2),
    "ba6": (2, 2), "ba7": (2, 2), "ba8": (2, 2), "ba9": (2, 2), "baa": (2, 2),
    "bab": (2, 2), "bac": (2, 2), "bad": (2, 2), "bae": (2, 2), "baf": (2, 2),

    # ── Druid Pelts (2×2) ──────────────────────────────────────────────────────
    "dr1": (2, 2), "dr2": (2, 2), "dr3": (2, 2), "dr4": (2, 2), "dr5": (2, 2),
    "dr6": (2, 2), "dr7": (2, 2), "dr8": (2, 2), "dr9": (2, 2), "dra": (2, 2),
    "drb": (2, 2), "drc": (2, 2), "drd": (2, 2), "dre": (2, 2), "drf": (2, 2),

    # ── Necromancer Heads (2×2) ────────────────────────────────────────────────
    "ne1": (2, 2), "ne2": (2, 2), "ne3": (2, 2), "ne4": (2, 2), "ne5": (2, 2),
    "ne6": (2, 2), "ne7": (2, 2), "ne8": (2, 2), "ne9": (2, 2), "nea": (2, 2),
    "neb": (2, 2), "ned": (2, 2), "nee": (2, 2), "nef": (2, 2), "neg": (2, 2),

    # ── Circlets (2×2) ─────────────────────────────────────────────────────────
    "ci0": (2, 2), "ci1": (2, 2), "ci2": (2, 2), "ci3": (2, 2),

    # ── Body Armor — Normal / Exceptional / Elite (2×3) ────────────────────────
    "qui": (2, 3), "lea": (2, 3), "hla": (2, 3), "stu": (2, 3), "rng": (2, 3),
    "scl": (2, 3), "chn": (2, 3), "brs": (2, 3), "spl": (2, 3), "plt": (2, 3),
    "fld": (2, 3), "gth": (2, 3), "ful": (2, 3), "arm": (2, 3), "ltp": (2, 3),
    "xui": (2, 3), "xea": (2, 3), "xla": (2, 3), "xtu": (2, 3), "xng": (2, 3),
    "xcl": (2, 3), "xhn": (2, 3), "xrs": (2, 3), "xpl": (2, 3), "xlt": (2, 3),
    "xld": (2, 3), "xth": (2, 3), "xul": (2, 3), "xar": (2, 3),
    "uui": (2, 3), "uea": (2, 3), "ula": (2, 3), "utu": (2, 3), "ung": (2, 3),
    "ucl": (2, 3), "uhn": (2, 3), "urs": (2, 3), "upl": (2, 3), "ult": (2, 3),
    "uld": (2, 3), "uth": (2, 3), "uul": (2, 3), "uar": (2, 3),
    "aar": (2, 3), "utp": (2, 3), "xtp": (2, 3),  # duplicate entries

    # ── Gloves — Normal / Exceptional / Elite (2×2) ────────────────────────────
    "lgl": (2, 2), "vgl": (2, 2), "mgl": (2, 2), "tgl": (2, 2), "hgl": (2, 2),
    "xvg": (2, 2), "xmg": (2, 2), "xtg": (2, 2), "xhg": (2, 2),
    "uvg": (2, 2), "umg": (2, 2), "utg": (2, 2), "uhg": (2, 2),

    # ── Boots — Normal / Exceptional / Elite (2×2) ─────────────────────────────
    "lbt": (2, 2), "vbt": (2, 2), "mbt": (2, 2), "tbt": (2, 2), "hbt": (2, 2),
    "xlb": (2, 2), "xvb": (2, 2), "xmb": (2, 2), "xtb": (2, 2), "xhb": (2, 2),
    "ulb": (2, 2), "uvb": (2, 2), "umb": (2, 2), "utb": (2, 2), "uhb": (2, 2),

    # ── Shields (2×2 most; 2×3 for Tower/Gothic/Aegis/Ward tiers) ──────────────
    "buc": (2, 2), "sml": (2, 2), "lrg": (2, 2), "kit": (2, 2),
    "tow": (2, 3),  # Tower Shield
    "gts": (2, 3),  # Gothic Shield
    "xuc": (2, 2), "xml": (2, 2), "xlg": (2, 2), "xks": (2, 2),
    "xow": (2, 3),  # Pavise (Tower tier)
    "xts": (2, 3),  # Ancient Shield (Gothic tier)
    "xrg": (2, 2),  # Scutum (duplicate)
    "uuc": (2, 2), "uml": (2, 2), "ulg": (2, 2), "uks": (2, 2),
    "uow": (2, 3),  # Aegis
    "uts": (2, 3),  # Ward
    "spk": (2, 2), "bsh": (2, 2),  # Spiked Shield, Bone Shield
    "xpk": (2, 2), "xsh": (2, 2),  # Barbed Shield, Grim Shield
    "xit": (2, 2), "uit": (2, 2), "upk": (2, 2), "ush": (2, 2), "urg": (2, 2),

    # ── Paladin Shields (normal 2×2; exceptional/elite 2×3) ────────────────────
    "pa1": (2, 2), "pa2": (2, 2), "pa3": (2, 2), "pa4": (2, 2), "pa5": (2, 2),
    "pa6": (2, 3), "pa7": (2, 3), "pa8": (2, 3), "pa9": (2, 3), "paa": (2, 3),
    "pab": (2, 3), "pac": (2, 3), "pad": (2, 3), "pae": (2, 3), "paf": (2, 3),

    # ── Wands (1×2) ────────────────────────────────────────────────────────────
    "wnd": (1, 2), "ywn": (1, 2), "bwn": (1, 2), "gwn": (1, 2),
    "9wn": (1, 2), "9bw": (1, 2), "9yw": (1, 2),
    "7wn": (1, 2), "7bw": (1, 2), "7yw": (1, 2),
    "7gw": (1, 2),  # Unearthed Wand
    "9gw": (1, 2),  # Grave Wand

    # ── Orbs (1×2) ─────────────────────────────────────────────────────────────
    "ob1": (1, 2), "ob2": (1, 2), "ob3": (1, 2), "ob4": (1, 2), "ob5": (1, 2),
    "ob6": (1, 2), "ob7": (1, 2), "ob8": (1, 2), "ob9": (1, 2), "oba": (1, 2),
    "obb": (1, 2), "obc": (1, 2), "obd": (1, 2), "obe": (1, 2), "obf": (1, 2),

    # ── Scepters (1×3) ─────────────────────────────────────────────────────────
    "scp": (1, 3), "wsp": (1, 3), "gsc": (1, 3),
    "9sc": (1, 3), "9qs": (1, 3),
    "9ws": (1, 3),  # Divine Scepter (listed under swords in item_types but is a scepter)
    "7sc": (1, 3), "7qs": (1, 3),
    "7ws": (1, 3),  # Caduceus (listed under swords in item_types but is a scepter)

    # ── Daggers / Dirks (1×2) ──────────────────────────────────────────────────
    "dgr": (1, 2), "dir": (1, 2), "kri": (1, 2),
    "9dg": (1, 2), "9di": (1, 2), "9bl": (1, 2),
    "7dg": (1, 2), "7di": (1, 2), "7bl": (1, 2),
    "9kr": (1, 2),  # Cinquedeas
    "7kr": (1, 2),  # Fanged Knife

    # ── Throwing Weapons (1×2) ─────────────────────────────────────────────────
    "tax": (1, 2), "tkf": (1, 2), "bal": (1, 2), "bkf": (1, 2),
    "9ta": (1, 2), "9tk": (1, 2), "9bk": (1, 2), "9b8": (1, 2),  # Hurlbat
    "7ta": (1, 2), "7tk": (1, 2), "7bk": (1, 2), "7b8": (1, 2),  # Winged Axe

    # ── Javelins (1×3) ─────────────────────────────────────────────────────────
    "jav": (1, 3), "pil": (1, 3), "ssp": (1, 3), "tsp": (1, 3),
    "9ja": (1, 3), "9pi": (1, 3), "9ts": (1, 3),
    "7ja": (1, 3), "7pi": (1, 3), "7ts": (1, 3),
    "9s9": (1, 3),  # Simbilan (Amazon javelin, exceptional)

    # ── Katars (1×3) ───────────────────────────────────────────────────────────
    "ktr": (1, 3), "wrb": (1, 3), "clw": (1, 3), "btl": (1, 3), "ces": (1, 3),
    "skr": (1, 3), "axf": (1, 3),
    "9ar": (1, 3), "9qr": (1, 3), "9lw": (1, 3), "9xf": (1, 3),
    "9tw": (1, 3), "9wb": (1, 3),  # Greater Talons, Wrist Spike
    "7ar": (1, 3), "7qr": (1, 3), "7lw": (1, 3), "7xf": (1, 3),
    "7wb": (1, 3), "7tw": (1, 3),
    "7cs": (1, 3),  # Battle Cestus (listed under swords in item_types but is a katar)

    # ── Military Pick (1×3) ────────────────────────────────────────────────────
    "mpi": (1, 3),
    "9mp": (1, 3),  # Crowbill (exceptional)
    "7mp": (1, 3),  # War Spike (elite)

    # ── Swords — Short (1×3) ───────────────────────────────────────────────────
    "ssd": (1, 3),  # Short Sword
    "lsd": (1, 3),  # Long Sword
    "scm": (1, 3),  # Scimitar
    "sbr": (1, 3),  # Saber
    "flc": (1, 3),  # Falchion
    "wsd": (1, 3),  # War Sword
    # Exceptional short 1H
    "9ss": (1, 3),  # Gladius
    "9ls": (1, 3),  # Rune Sword
    "9sm": (1, 3),  # Cutlass
    "9sb": (1, 3),  # Shamshir
    "9cm": (1, 3),  # Dacian Falx
    "9fc": (1, 3),  # Tulwar
    # Elite short 1H
    "7ss": (1, 3),  # Falcata
    "7ls": (1, 3),  # Cryptic Sword
    "7fc": (1, 3),  # Hydra Edge
    "7sm": (1, 3),  # Ataghan
    "7sb": (1, 3),  # Elegant Blade
    "7cm": (1, 3),  # Highland Blade

    # ── Swords — Long 1H (1×4) ─────────────────────────────────────────────────
    "bsd": (1, 4),  # Broad Sword
    "crs": (1, 4),  # Crystal Sword
    "bsw": (1, 4),  # Bastard Sword
    # Exceptional
    "9bs": (1, 4),  # Battle Sword
    "9cr": (1, 4),  # Dimensional Blade (exceptional Crystal Sword)
    # Elite
    "7bs": (1, 4),  # Conquest Sword
    "7cr": (1, 4),  # Phase Blade
    "7b7": (1, 4),  # Champion Sword

    # ── Swords — 2H (2×4) ──────────────────────────────────────────────────────
    "clm": (2, 4),  # Claymore
    "gis": (2, 4),  # Giant Sword
    "gsd": (2, 4),  # Great Sword
    "2hs": (2, 4),  # Two-Handed Sword
    "flb": (2, 4),  # Flamberge
    # Exceptional
    "9b9": (2, 4),  # Gothic Sword
    "9wd": (2, 4),  # Ancient Sword
    "9gs": (2, 4),  # Tusk Sword
    "9fb": (2, 4),  # Zweihander
    "9gd": (2, 4),  # Executioner Sword
    "92h": (2, 4),  # Espandon
    # Elite
    "7wd": (2, 4),  # Mythical Sword
    "7fb": (2, 4),  # Colossal Sword
    "7gs": (2, 4),  # Balrog Blade
    "72h": (2, 4),  # Legend Sword
    "7gd": (2, 4),  # Colossus Blade

    # ── Axes — 1H short (1×3) ──────────────────────────────────────────────────
    "hax": (1, 3), "axe": (1, 3),
    "9ax": (1, 3),  # Cleaver
    "9ha": (1, 3),  # Hatchet
    "7ax": (1, 3),  # Small Crescent
    "7ha": (1, 3),  # Tomahawk

    # ── Axes — 2H medium (2×3) ─────────────────────────────────────────────────
    "lax": (2, 3),  # Large Axe
    "2ax": (2, 3),  # Double Axe
    "bax": (2, 3),  # Broad Axe
    "9la": (2, 3),  # Military Axe
    "9ba": (2, 3),  # Bearded Axe
    "9bt": (2, 3),  # Tabar
    "92a": (2, 3),  # Twin Axe
    "7la": (2, 3),  # Feral Axe
    "7ba": (2, 3),  # Silver-edged Axe

    # ── Axes — 2H large (2×4) ──────────────────────────────────────────────────
    "gax": (2, 4), "gix": (2, 4),  # Great Axe, Giant Axe
    "btx": (2, 4), "wax": (2, 4),  # Battle Axe, War Axe
    "mau": (2, 4), "gma": (2, 4),  # Maul, Great Maul
    "9ga": (2, 4), "9gi": (2, 4),  # Gothic Axe, Ancient Axe
    "9wa": (2, 4),                  # Naga
    "7ga": (2, 4), "7gi": (2, 4),  # Champion Axe, Glorious Axe
    "7wa": (2, 4), "7bt": (2, 4),  # Berserker Axe, Decapitator
    "72a": (2, 4),                  # Ettin Axe

    # ── Maces / Clubs — 1H (1×3) ───────────────────────────────────────────────
    "clb": (1, 3), "spc": (1, 3), "mst": (1, 3), "fla": (1, 3), "mac": (1, 3),
    "9cl": (1, 3), "9sp": (1, 3), "9ma": (1, 3), "9fl": (1, 3),
    "9mt": (1, 3), "9m9": (1, 3),  # Jagged Star, War Club
    "7cl": (1, 3), "7sp": (1, 3), "7ma": (1, 3), "7fl": (1, 3), "7mt": (1, 3),

    # ── Maces — 2H (2×3 War Hammer tier; 2×4 Great Maul tier) ─────────────────
    "whm": (2, 3),  # War Hammer
    "9wh": (2, 3),  # Battle Hammer
    "7wh": (2, 4),  # Legendary Mallet
    "9gm": (2, 4),  # Martel de Fer
    "7gm": (2, 4),  # Thunder Maul
    "7m7": (2, 4),  # Ogre Maul

    # ── Polearms (2×4) ─────────────────────────────────────────────────────────
    "bar": (2, 4), "pax": (2, 4), "hal": (2, 4), "scy": (2, 4), "wsc": (2, 4),
    "vou": (2, 4), "glv": (2, 4), "bld": (2, 4),
    "9b7": (2, 4), "9s8": (2, 4), "9wc": (2, 4), "9h9": (2, 4), "9pa": (2, 4),
    "9gl": (2, 4), "9vo": (2, 4), "9br": (2, 4),
    "7s8": (2, 4), "7wc": (2, 4), "7h7": (2, 4), "7pa": (2, 4), "7gl": (2, 4),
    "7o7": (2, 4), "7vo": (2, 4), "7br": (2, 4),

    # ── Spears (2×4) ───────────────────────────────────────────────────────────
    "spr": (2, 4), "spt": (2, 4), "tri": (2, 4), "brn": (2, 4), "pik": (2, 4),
    "9sr": (2, 4), "9tr": (2, 4), "9p9": (2, 4), "9st": (2, 4),
    "7sr": (2, 4), "7tr": (2, 4), "7p7": (2, 4), "7st": (2, 4),
    "7s7": (2, 4),  # Balrog Spear

    # ── Staves — Short (1×3) ───────────────────────────────────────────────────
    "sst": (1, 3),  # Short Staff
    "8ss": (1, 3),  # Jo Staff (exceptional)
    "6ss": (1, 3),  # Walking Stick (elite)

    # ── Staves — Long (2×4) ────────────────────────────────────────────────────
    "lst": (2, 4), "cst": (2, 4), "bst": (2, 4), "wst": (2, 4),
    "8ls": (2, 4), "8cs": (2, 4), "8bs": (2, 4), "8ws": (2, 4),
    "6ls": (2, 4), "6cs": (2, 4), "6bs": (2, 4), "6ws": (2, 4),

    # ── Bows — Short (2×3) ─────────────────────────────────────────────────────
    "sbw": (2, 3), "hbw": (2, 3), "cbw": (2, 3), "sbb": (2, 3), "swb": (2, 3),
    "8sb": (2, 3), "8cb": (2, 3), "8hb": (2, 3), "8sw": (2, 3), "8s8": (2, 3),
    "6sb": (2, 3), "6cb": (2, 3), "6hb": (2, 3), "6sw": (2, 3), "6s7": (2, 3),

    # ── Bows — Long (2×4) ──────────────────────────────────────────────────────
    "lbw": (2, 4), "lbb": (2, 4), "lwb": (2, 4),
    "8lb": (2, 4), "8lw": (2, 4), "8l8": (2, 4),
    "6lb": (2, 4), "6lw": (2, 4), "6l7": (2, 4),

    # ── Crossbows — Light (2×3) ────────────────────────────────────────────────
    "lxb": (2, 3), "mxb": (2, 3), "rxb": (2, 3),
    "8lx": (2, 3), "8mx": (2, 3), "8rx": (2, 3),
    "6lx": (2, 3), "6mx": (2, 3), "6rx": (2, 3),

    # ── Crossbows — Heavy (2×4) ────────────────────────────────────────────────
    "hxb": (2, 4),
    "8hx": (2, 4),
    "6hx": (2, 4),

    # ── Amazon Weapons ──────────────────────────────────────────────────────────
    "am1": (2, 3), "am2": (2, 3),              # Stag Bow, Reflex Bow
    "am3": (2, 4), "am4": (2, 4),              # Maiden Spear, Maiden Pike
    "am5": (1, 3),                              # Maiden Javelin
    "am6": (2, 3), "am7": (2, 3),              # Ashwood Bow, Ceremonial Bow
    "am8": (2, 4), "am9": (2, 4),              # Ceremonial Spear, Ceremonial Pike
    "ama": (1, 3),                              # Ceremonial Javelin
    "amb": (2, 4), "amc": (2, 4),              # Matriarchal Bow, Grand Matron Bow
    "amd": (2, 4), "ame": (2, 4),              # Matriarchal Spear, Matriarchal Pike
    "amf": (1, 3),                              # Matriarchal Javelin

    # ── Reign of the Warlock patch ──────────────────────────────────────────────
    "wac": (1, 1),  # Occult Tome — dimensions unknown; using 1×1 fallback
}

DEFAULT_DIMENSIONS = (1, 1)


def get_item_dimensions(item_type: str) -> tuple[int, int]:
    """Return (width, height) in stash grid cells for an item type code."""
    return ITEM_DIMENSIONS.get(item_type.strip(), DEFAULT_DIMENSIONS)
