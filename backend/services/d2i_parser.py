from __future__ import annotations

"""
D2I stash file parser for Diablo 2 Resurrected.

Handles both the legacy format (SharedStashSoftCoreV2.d2i) and the Modern format
(ModernSharedStashSoftCoreV2.d2i, version==2).

Legacy layout (version != 2):
  [12-byte header: magic(4) + version(4) + num_pages(4)]
  [N pages, each: flags(4) + name_len(2) + name(N) + JM(2) + item_count(4) + item_bytes...]
  Each top-level item starts at its JM (0x4A 0x4D) byte marker.

Modern layout (version == 2):
  [64-byte header: magic(4) + version(4) + unknown(4) + gold(4) + page0_size(4) + zeros(44)]
  [N pages, page 0 follows the header directly, pages 1+ are each preceded by a 64-byte separator:]
    JM(2) + item_count(2, uint16 LE) + item_bytes...
  Separator format: magic(4)+version(4)+unk1(4)+gold=0(4)+size_field(4)+zeros(44)
    size_field = slot size of the FOLLOWING page = 4+raw_len+64 (for non-last pages).
    Last separator has field at offset 20 = 1 (terminal marker); its size_field is not a slot size.
  Items have NO JM prefix. Each item starts with first_byte=0x10 (identified flag at bit 4).
  Quality (4 bits) is at a variable bit offset in the range [108, 121] from item start.
  The exact offset depends on the item type encoding used by D2R, which differs from legacy ASCII.
  unique_id/set_id (12 bits) follow quality after 2 flag bits (multiple_pictures, class_specific).
"""

import logging
import struct
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)


# ─── Bit I/O (LSB-first) ──────────────────────────────────────────────────────

class BitReader:
    """Reads LSB-first bits from a bytearray."""

    def __init__(self, data: bytes | bytearray, bit_offset: int = 0):
        self.data = data
        self.bit_offset = bit_offset

    def read(self, n: int) -> int:
        result = 0
        for i in range(n):
            byte_idx = self.bit_offset // 8
            bit_idx = self.bit_offset % 8
            if byte_idx < len(self.data):
                result |= ((self.data[byte_idx] >> bit_idx) & 1) << i
            self.bit_offset += 1
        return result

    def peek(self, n: int) -> int:
        saved = self.bit_offset
        val = self.read(n)
        self.bit_offset = saved
        return val

    def seek(self, bit_offset: int) -> None:
        self.bit_offset = bit_offset

    def tell(self) -> int:
        return self.bit_offset


# ─── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class D2IItem:
    byte_start: int        # byte offset within page's raw_bytes
    byte_end: int          # exclusive end (includes socketed sub-items for legacy)
    item_type: str         # 4-char code e.g. "uow " (empty string for Modern format)
    quality: int           # 4-bit: 5=set, 7=unique
    unique_id: int | None  # 12 bits when quality==7
    set_id: int | None     # 12 bits when quality==5
    item_level: int        # 7 bits (0 for Modern format)
    is_ethereal: bool
    socket_count: int      # filled sockets (0 for Modern format)
    is_simple: bool
    is_ear: bool
    properties: list[str] = field(default_factory=list)  # formatted stat strings
    p1_unique_id: int | None = None  # Phase 1 unique_id, preserved even when Phase 2 wins quality
    p1_set_id: int | None = None     # Phase 1 set_id, preserved even when Phase 2 wins quality
    magic_prefix: str | None = None  # display name of magic prefix (q=3, e.g. "Viridian")
    magic_suffix: str | None = None  # display name of magic suffix (q=3, e.g. "of Life")
    rare_name: str | None = None     # combined two-word rare/crafted name (q=4/6)


@dataclass
class D2IPage:
    flags: int
    name: str
    raw_bytes: bytearray   # item data bytes only (after JM + item_count header)
    item_count: int
    items: list[D2IItem] = field(default_factory=list)
    is_modern: bool = False
    preceding_separator: bytes = field(default=b"")  # 64-byte separator before this page's JM (empty for page 0)


@dataclass
class D2IStash:
    magic: int
    version: int
    num_pages: int
    pages: list[D2IPage] = field(default_factory=list)
    is_modern: bool = False
    raw_header: bytes = field(default=b"")  # preserved 64-byte header for Modern format
    gold: int = 0  # stash gold (bytes 12-15 of Modern header)


# ─── Legacy parser constants ───────────────────────────────────────────────────

ITEM_MARKER = b"JM"

# Bit offsets within a single item's bitstream (from the start of its JM marker)
_BIT_IDENTIFIED    = 20
_BIT_SOCKETED_ITEM = 21
_BIT_EAR           = 28
_BIT_NEWBIE        = 29
_BIT_SIMPLE        = 35
_BIT_ETHEREAL      = 36
_BIT_PERSONALIZED  = 38
_BIT_RUNEWORD      = 42
_BIT_ITEM_TYPE     = 96       # 4 chars × 8 bits = 32 bits, ASCII
_BIT_SOCKET_COUNT  = 128      # 3 bits
_BIT_NID           = 131
_BIT_ILVL          = 163
_BIT_QUALITY       = 170
_BIT_QUALITY_DATA  = 174      # 12 bits


# ─── Item stat table (from ItemStatCost.txt) ──────────────────────────────────
# Maps stat_id → (save_bits, save_add, save_param_bits)
# actual_value = stored_value - save_add
# save_param_bits: extra bits before the value for parameterized stats (e.g. skill ID)
_STAT_TABLE: dict[int, tuple[int, int, int]] = {
    0:   (8,  32, 0),   # strength
    1:   (7,  32, 0),   # energy
    2:   (7,  32, 0),   # dexterity
    3:   (7,  32, 0),   # vitality
    7:   (9,  32, 0),   # maxhp
    9:   (8,  32, 0),   # maxmana
    11:  (8,  32, 0),   # maxstamina
    16:  (9,   0, 0),   # item_armor_percent (enhanced defense %)
    17:  (9,   0, 0),   # item_maxdamage_percent (enhanced damage %)
    18:  (9,   0, 0),   # item_mindamage_percent
    19:  (10,  0, 0),   # tohit (attack rating)
    20:  (6,   0, 0),   # toblock
    21:  (6,   0, 0),   # mindamage (min 1h dmg bonus)
    22:  (7,   0, 0),   # maxdamage (max 1h dmg bonus)
    23:  (6,   0, 0),   # secondary_mindamage (min 2h)
    24:  (7,   0, 0),   # secondary_maxdamage (max 2h)
    25:  (8,   0, 0),   # damagepercent
    26:  (8,   0, 0),   # manarecovery
    27:  (8,   0, 0),   # manarecoverybonus
    28:  (8,   0, 0),   # staminarecoverybonus
    31:  (11, 10, 0),   # armorclass (defense)
    32:  (9,   0, 0),   # armorclass_vs_missile
    33:  (8,   0, 0),   # armorclass_vs_hth
    34:  (6,   0, 0),   # normal_damage_reduction
    35:  (6,   0, 0),   # magic_damage_reduction
    36:  (9, 200, 0),   # damageresist (physical resist %)
    37:  (9, 200, 0),   # magicresist
    38:  (5,   0, 0),   # maxmagicresist
    39:  (9, 200, 0),   # fireresist
    40:  (5,   0, 0),   # maxfireresist
    41:  (9, 200, 0),   # lightresist
    42:  (5,   0, 0),   # maxlightresist
    43:  (9, 200, 0),   # coldresist
    44:  (5,   0, 0),   # maxcoldresist
    45:  (9, 200, 0),   # poisonresist
    46:  (5,   0, 0),   # maxpoisonresist
    48:  (8,   0, 0),   # firemindam
    49:  (9,   0, 0),   # firemaxdam
    50:  (6,   0, 0),   # lightmindam
    51:  (10,  0, 0),   # lightmaxdam
    52:  (8,   0, 0),   # magicmindam
    53:  (9,   0, 0),   # magicmaxdam
    54:  (8,   0, 0),   # coldmindam
    55:  (9,   0, 0),   # coldmaxdam
    56:  (8,   0, 0),   # coldlength (frames; /25 = seconds)
    57:  (10,  0, 0),   # poisonmindam
    58:  (10,  0, 0),   # poisonmaxdam
    59:  (9,   0, 0),   # poisonlength (frames; /25 = seconds)
    60:  (7,   0, 0),   # lifedrainmindam
    62:  (7,   0, 0),   # manadrainmindam
    67:  (7,  30, 0),   # velocitypercent (unused display)
    68:  (7,  30, 0),   # attackrate (unused display)
    72:  (9,   0, 0),   # durability
    73:  (8,   0, 0),   # maxdurability
    74:  (6,  30, 0),   # hpregen (replenish life)
    75:  (7,  20, 0),   # item_maxdurability_percent
    76:  (6,  10, 0),   # item_maxhp_percent
    77:  (6,  10, 0),   # item_maxmana_percent
    78:  (7,   0, 0),   # item_attackertakesdamage (thorns)
    79:  (9, 100, 0),   # item_goldbonus
    80:  (8, 100, 0),   # item_magicbonus
    81:  (7,   0, 0),   # item_knockback
    83:  (3,   0, 3),   # item_addclassskills (param=class index)
    85:  (9,  50, 0),   # item_addexperience
    86:  (7,   0, 0),   # item_healafterkill
    89:  (4,   4, 0),   # item_lightradius
    91:  (8, 100, 0),   # item_req_percent (requirements %)
    93:  (7,  20, 0),   # item_fasterattackrate (IAS)
    96:  (7,  20, 0),   # item_fastermovevelocity (FRW)
    97:  (6,   0, 9),   # item_nonclassskill (param=skill id)
    99:  (7,  20, 0),   # item_fastergethitrate (FHR)
    102: (7,  20, 0),   # item_fasterblockrate (FBR)
    105: (7,  20, 0),   # item_fastercastrate (FCR)
    107: (3,   0, 9),   # item_singleskill (param=skill id)
    108: (1,   0, 0),   # item_restinpeace (slain monsters rest)
    110: (8,  20, 0),   # item_poisonlengthresist
    111: (9,  20, 0),   # item_normaldamage
    112: (7,  -1, 0),   # item_howl
    113: (7,   0, 0),   # item_stupidity
    114: (6,   0, 0),   # item_damagetomana
    115: (1,   0, 0),   # item_ignoretargetac
    116: (7,   0, 0),   # item_fractionaltargetac
    117: (7,   0, 0),   # item_preventheal
    118: (1,   0, 0),   # item_halffreezeduration
    119: (9,  20, 0),   # item_tohit_percent (AR %)
    120: (7, 128, 0),   # item_damagetargetac (-def)
    121: (9,  20, 0),   # item_demondamage_percent
    122: (9,  20, 0),   # item_undeaddamage_percent
    123: (10,128, 0),   # item_demon_tohit
    124: (10,128, 0),   # item_undead_tohit
    127: (3,   0, 0),   # item_allskills
    128: (5,   0, 0),   # item_attackertakeslightdamage
    134: (5,   0, 0),   # item_freeze
    135: (7,   0, 0),   # item_openwounds
    136: (7,   0, 0),   # item_crushingblow
    137: (7,   0, 0),   # item_kickdamage
    138: (7,   0, 0),   # item_manaafterkill
    139: (7,   0, 0),   # item_healafterdemonkill
    141: (7,   0, 0),   # item_deadlystrike
    142: (7,   0, 0),   # item_absorbfire_percent
    143: (7,   0, 0),   # item_absorbfire
    144: (7,   0, 0),   # item_absorblight_percent
    145: (7,   0, 0),   # item_absorblight
    146: (7,   0, 0),   # item_absorbmagic_percent
    147: (7,   0, 0),   # item_absorbmagic
    148: (7,   0, 0),   # item_absorbcold_percent
    149: (7,   0, 0),   # item_absorbcold
    150: (7,   0, 0),   # item_slow
    151: (5,   0, 9),   # item_aura (param=aura skill id)
    152: (1,   0, 0),   # item_indestructible
    153: (1,   0, 0),   # item_cannotbefrozen
    154: (7,  20, 0),   # item_staminadrainpct
    155: (7,   0, 10),  # item_reanimate
    156: (7,   0, 0),   # item_pierce
    157: (7,   0, 0),   # item_magicarrow
    158: (7,   0, 0),   # item_explosivearrow
    159: (6,   0, 0),   # item_throw_mindamage
    160: (7,   0, 0),   # item_throw_maxdamage
    179: (9,   0, 10),  # attack_vs_montype
    180: (9,   0, 10),  # damage_vs_montype
    185: (8,   0, 0),   # bonus_mindamage
    186: (8,   0, 0),   # bonus_maxdamage
    187: (10,  0, 0),   # item_pierce_cold_immunity (cold sunder)
    188: (3,   0, 16),  # item_addskill_tab (param=tab id)
    189: (10,  0, 0),   # item_pierce_fire_immunity
    190: (10,  0, 0),   # item_pierce_light_immunity
    191: (10,  0, 0),   # item_pierce_poison_immunity
    192: (10,  0, 0),   # item_pierce_damage_immunity
    193: (10,  0, 0),   # item_pierce_magic_immunity
    194: (4,   0, 0),   # item_numsockets
    195: (7,   0, 16),  # item_skillonattack
    196: (7,   0, 16),  # item_skillonkill
    197: (7,   0, 16),  # item_skillondeath
    198: (7,   0, 16),  # item_skillonhit
    199: (7,   0, 16),  # item_skillonlevelup
    200: (7,   0, 0),   # item_charge_noconsume
    201: (7,   0, 16),  # item_skillongethit
    204: (16,  0, 16),  # item_charged_skill (level<<8|charges, param=skill_id<<8|max_charges? complex)
    205: (7,   0, 0),   # item_noconsume
    213: (8,   0, 0),   # passive_mastery_gethit_rate / passive_mastery_attack_speed
    214: (6,   0, 0),   # item_armor_perlevel
    215: (6,   0, 0),   # item_armorpercent_perlevel
    216: (6,   0, 0),   # item_hp_perlevel
    217: (6,   0, 0),   # item_mana_perlevel
    218: (6,   0, 0),   # item_maxdamage_perlevel
    219: (6,   0, 0),   # item_maxdamage_percent_perlevel
    220: (6,   0, 0),   # item_strength_perlevel
    221: (6,   0, 0),   # item_dexterity_perlevel
    222: (6,   0, 0),   # item_energy_perlevel
    223: (6,   0, 0),   # item_vitality_perlevel
    224: (6,   0, 0),   # item_tohit_perlevel
    225: (6,   0, 0),   # item_tohitpercent_perlevel
    226: (6,   0, 0),   # item_cold_damagemax_perlevel
    227: (6,   0, 0),   # item_fire_damagemax_perlevel
    228: (6,   0, 0),   # item_ltng_damagemax_perlevel
    229: (6,   0, 0),   # item_pois_damagemax_perlevel
    230: (6,   0, 0),   # item_resist_cold_perlevel
    231: (6,   0, 0),   # item_resist_fire_perlevel
    232: (6,   0, 0),   # item_resist_ltng_perlevel
    233: (6,   0, 0),   # item_resist_pois_perlevel
    238: (5,   0, 0),   # item_thorns_perlevel
    239: (6,   0, 0),   # item_find_gold_perlevel
    240: (6,   0, 0),   # item_find_magic_perlevel
    241: (6,   0, 0),   # item_regenstamina_perlevel
    242: (6,   0, 0),   # item_stamina_perlevel
    243: (6,   0, 0),   # item_damage_demon_perlevel
    244: (6,   0, 0),   # item_damage_undead_perlevel
    250: (6,   0, 0),   # item_deadlystrike_perlevel
    252: (6,   0, 0),   # item_replenish_durability
    253: (6,   0, 0),   # item_replenish_quantity
    254: (8,   0, 0),   # item_extra_stack
    305: (8,  50, 0),   # item_pierce_cold
    306: (8,  50, 0),   # item_pierce_fire
    307: (8,  50, 0),   # item_pierce_ltng
    308: (8,  50, 0),   # item_pierce_pois
    324: (6,   0, 0),   # item_extra_charges
    329: (9,  50, 0),   # passive_fire_mastery
    330: (9,  50, 0),   # passive_ltng_mastery
    331: (9,  50, 0),   # passive_cold_mastery
    332: (9,  50, 0),   # passive_pois_mastery
    333: (8,   0, 0),   # passive_fire_pierce
    334: (8,   0, 0),   # passive_ltng_pierce
    335: (8,   0, 0),   # passive_cold_pierce
    336: (8,   0, 0),   # passive_pois_pierce
    357: (9,  50, 0),   # passive_mag_mastery
    358: (8,   0, 0),   # passive_mag_pierce
    365: (6,   0, 0),   # item_magic_damagemax_perlevel
    366: (8,   0, 0),   # passive_dmg_pierce
    # ── Additional stats (must be known so parser doesn't stop on them) ───────
    71:  (8, 100, 0),   # value (vendor)
    82:  (9,  20, 0),   # item_timeduration
    87:  (7,   0, 0),   # item_reducedprices
    88:  (1,   0, 0),   # item_doubleherbduration
    90:  (24,  0, 0),   # item_lightcolor (CRITICAL: 24 bits — unknown breaks parsing)
    92:  (7,   0, 0),   # item_levelreq
    94:  (7,  64, 0),   # item_levelreqpct (reduces level req %)
    98:  (1,   0, 8),   # state
    109: (9,   0, 0),   # curse_resistance
    125: (1,   0, 0),   # item_throwable
    126: (3,   0, 3),   # item_elemskill (+X to elemental skills, param=element)
    140: (7,   0, 0),   # item_extrablood
    181: (3,   0, 0),   # fade
    206: (8,   0, 0),   # passive_mastery_noconsume
    207: (8,   0, 0),   # passive_mastery_replenish_oncrit
    234: (6,   0, 0),   # item_absorb_cold_perlevel
    235: (6,   0, 0),   # item_absorb_fire_perlevel
    236: (6,   0, 0),   # item_absorb_ltng_perlevel
    237: (6,   0, 0),   # item_absorb_pois_perlevel
    245: (6,   0, 0),   # item_tohit_demon_perlevel
    246: (6,   0, 0),   # item_tohit_undead_perlevel
    247: (6,   0, 0),   # item_crushingblow_perlevel
    248: (6,   0, 0),   # item_openwounds_perlevel
    249: (6,   0, 0),   # item_kick_damage_perlevel
    268: (22,  0, 0),   # item_armor_bytime
    269: (22,  0, 0),   # item_armorpercent_bytime
    270: (22,  0, 0),   # item_hp_bytime
    271: (22,  0, 0),   # item_mana_bytime
    272: (22,  0, 0),   # item_maxdamage_bytime
    273: (22,  0, 0),   # item_maxdamage_percent_bytime
    274: (22,  0, 0),   # item_strength_bytime
    275: (22,  0, 0),   # item_dexterity_bytime
    276: (22,  0, 0),   # item_energy_bytime
    277: (22,  0, 0),   # item_vitality_bytime
    278: (22,  0, 0),   # item_tohit_bytime
    279: (22,  0, 0),   # item_tohitpercent_bytime
    280: (22,  0, 0),   # item_cold_damagemax_bytime
    281: (22,  0, 0),   # item_fire_damagemax_bytime
    282: (22,  0, 0),   # item_ltng_damagemax_bytime
    283: (22,  0, 0),   # item_pois_damagemax_bytime
    284: (22,  0, 0),   # item_resist_cold_bytime
    285: (22,  0, 0),   # item_resist_fire_bytime
    286: (22,  0, 0),   # item_resist_ltng_bytime
    287: (22,  0, 0),   # item_resist_pois_bytime
    288: (22,  0, 0),   # item_absorb_cold_bytime
    289: (22,  0, 0),   # item_absorb_fire_bytime
    290: (22,  0, 0),   # item_absorb_ltng_bytime
    291: (22,  0, 0),   # item_absorb_pois_bytime
    292: (22,  0, 0),   # item_find_gold_bytime
    293: (22,  0, 0),   # item_find_magic_bytime
    294: (22,  0, 0),   # item_regenstamina_bytime
    295: (22,  0, 0),   # item_stamina_bytime
    296: (22,  0, 0),   # item_damage_demon_bytime
    297: (22,  0, 0),   # item_damage_undead_bytime
    298: (22,  0, 0),   # item_tohit_demon_bytime
    299: (22,  0, 0),   # item_tohit_undead_bytime
    300: (22,  0, 0),   # item_crushingblow_bytime
    301: (22,  0, 0),   # item_openwounds_bytime
    302: (22,  0, 0),   # item_kick_damage_bytime
    303: (22,  0, 0),   # item_deadlystrike_bytime
    338: (7,   0, 0),   # passive_dodge
    339: (7,   0, 0),   # passive_avoid
    340: (7,   0, 0),   # passive_evade
    341: (8,   0, 0),   # passive_warmth
    342: (8,   0, 0),   # passive_mastery_melee_th
    343: (8,   0, 0),   # passive_mastery_melee_dmg
    344: (8,   0, 0),   # passive_mastery_melee_crit
    337: (8,   0, 0),   # passive_critical_strike
    345: (8,   0, 0),   # passive_mastery_throw_th
    346: (8,   0, 0),   # passive_mastery_throw_dmg
    347: (8,   0, 0),   # passive_mastery_throw_crit
    348: (8,   0, 0),   # passive_weaponblock
    349: (8,   0, 0),   # passive_summon_resist
    356: (2,   0, 0),   # questitemdifficulty
    # ── Classic D2 stats that D2R now saves (empty Save Bits in classic txt) ─────
    # These stats existed in D2 but were never saved to item files; D2R changed
    # that without updating ItemStatCost.txt.  Widths inferred from paired stats
    # or Send Bits where available.
    47:  (8,  0, 0),  # damageaura (between poisonresist/firemindam family; est 8 bits)
    61:  (7,  0, 0),  # lifedrainmaxdam (pairs with 60, same 7 bits)
    63:  (7,  0, 0),  # manadrainmaxdam (pairs with 62, same 7 bits)
    65:  (7,  0, 0),  # stamdrainmaxdam (pairs with 64, same family as 60-63)
    66:  (8,  0, 0),  # stunlength (D2R stun mechanic; estimated 8 bits)
    70:  (9,  0, 0),  # quantity / stack size (stackable items; estimated 9 bits)
    104: (1,  0, 0),  # skill_bypass_demons (boolean; Send Bits=1)
    133: (7,  0, 0),  # bonearmormax (pairs with 132)
    167: (7,  0, 0),  # skill_conviction (same family as skill_chillingarmor 168; est 7 bits)
    168: (7,  0, 0),  # skill_chillingarmor (skill level; estimated 7 bits)
    172: (2,  0, 0),  # alignment (Send Bits=2)
    208: (9,  0, 0),  # missile_thorns_percent (D2R; estimated 9 bits)
    211: (8,  0, 0),  # ua_defeated counter (Send Bits=8)
    255: (7,  0, 0),  # item_find_item (Find Item % chance; est 7 bits ≤100%)
    # ── D2R Season / Ladder stats (slash/crush/thrust damage types) ──────────
    256: (10, 0, 0),  # item_slash_damage
    257: (9,  0, 0),  # item_slash_damage_percent
    258: (10, 0, 0),  # item_crush_damage (inferred from block pattern)
    259: (10, 0, 0),  # item_thrust_damage
    261: (9,  0, 0),  # item_crush_or_thrust_damage_percent
    262: (8,  0, 0),  # item_absorb_slash
    263: (8,  0, 0),  # item_absorb_crush
    264: (8,  0, 0),  # item_absorb_thrust
    304: (22, 0, 0),  # item_find_gems_bytime (extends bytime group 268-303)
    316: (8,  0, 0),  # burningmin (like firemindam 48; est 8 bits)
    317: (9,  0, 0),  # burningmax (like firemaxdam 49; est 9 bits)
    318: (7,  0, 0),  # progressive_damage (same family as progressive_fire 321)
    319: (7,  0, 0),  # progressive_steal
    320: (7,  0, 0),  # progressive_other
    322: (7,  0, 0),  # progressive_cold
    323: (7,  0, 0),  # progressive_lightning
    325: (7,  0, 0),  # progressive_tohit
    326: (5,  0, 0),  # poison_count (Send Bits=5)
    327: (8,  0, 0),  # damage_framerate (est 8 bits)
    361: (9,  0, 0),  # psychicward (shield buffer like bonearmor; est 9 bits)
    362: (9,  0, 0),  # psychicwardmax
    # ── D2R-specific stats (absent from classic ItemStatCost.txt) ─────────────
    # D2R added saving for these stats or introduced them entirely.  Bit widths
    # are determined empirically from actual D2R stash files; they may not match
    # any field in the classic txt rip.  Wrong widths cause property display
    # errors but do NOT break quality/name detection as long as the sentinel is
    # subsequently found.  Add new IDs here as they appear in docker log warnings.
    64:  (12, 0, 0),  # unknown D2R stat; empirical 12 bits
    132: (6,  0, 0),  # bonearmor (D2R saves this); empirical 6 bits
    260: (14, 0, 0),  # unknown D2R stat; empirical 14 bits
    321: (7,  0, 0),  # progressive_fire / unknown; empirical 7 bits
    355: (1,  0, 0),  # shortparam1 / unknown; empirical 1 bit
    396: (0,  0, 0),  # unknown D2R stat; empirical 0 bits (flag)
    424: (0,  0, 0),  # unknown D2R stat; empirical 0 bits (flag)
    # ── Pure D2R additions (no classic D2 entry; 8-bit width is a best guess) ─
    # Wrong widths cause display desyncs but the two-tier Phase 1 scan still
    # detects quality+uid/sid correctly as long as the blocklist doesn't trigger.
    # Full range 368-510 covered (excluding 396/424 which have 0-bit entries above).
    368: (8,  0, 0),
    369: (8,  0, 0),
    370: (8,  0, 0),
    371: (8,  0, 0),
    372: (8,  0, 0),
    373: (8,  0, 0),
    374: (8,  0, 0),
    375: (8,  0, 0),
    376: (8,  0, 0),
    377: (8,  0, 0),
    378: (8,  0, 0),
    379: (8,  0, 0),
    380: (8,  0, 0),
    381: (8,  0, 0),
    382: (8,  0, 0),
    383: (8,  0, 0),
    384: (8,  0, 0),
    385: (8,  0, 0),
    386: (8,  0, 0),
    387: (8,  0, 0),
    388: (8,  0, 0),
    389: (8,  0, 0),
    390: (8,  0, 0),
    391: (8,  0, 0),
    392: (8,  0, 0),
    393: (8,  0, 0),
    394: (8,  0, 0),
    395: (8,  0, 0),
    397: (8,  0, 0),
    398: (8,  0, 0),
    399: (8,  0, 0),
    400: (8,  0, 0),
    401: (8,  0, 0),
    402: (8,  0, 0),
    403: (8,  0, 0),
    404: (8,  0, 0),
    405: (8,  0, 0),
    406: (8,  0, 0),
    407: (8,  0, 0),
    408: (8,  0, 0),
    409: (8,  0, 0),
    410: (8,  0, 0),
    411: (8,  0, 0),
    412: (8,  0, 0),
    413: (8,  0, 0),
    414: (8,  0, 0),
    415: (8,  0, 0),
    416: (8,  0, 0),
    417: (8,  0, 0),
    418: (8,  0, 0),
    419: (8,  0, 0),
    420: (8,  0, 0),
    421: (8,  0, 0),
    422: (8,  0, 0),
    423: (8,  0, 0),
    425: (8,  0, 0),
    426: (8,  0, 0),
    427: (8,  0, 0),
    428: (8,  0, 0),
    429: (8,  0, 0),
    430: (8,  0, 0),
    431: (8,  0, 0),
    432: (8,  0, 0),
    433: (8,  0, 0),
    434: (8,  0, 0),
    435: (8,  0, 0),
    436: (8,  0, 0),
    437: (8,  0, 0),
    438: (8,  0, 0),
    439: (8,  0, 0),
    440: (8,  0, 0),
    441: (8,  0, 0),
    442: (8,  0, 0),
    443: (8,  0, 0),
    444: (8,  0, 0),
    445: (8,  0, 0),
    446: (8,  0, 0),
    447: (8,  0, 0),
    448: (8,  0, 0),
    449: (8,  0, 0),
    450: (8,  0, 0),
    451: (8,  0, 0),
    452: (8,  0, 0),
    453: (8,  0, 0),
    454: (8,  0, 0),
    455: (8,  0, 0),
    456: (8,  0, 0),
    457: (8,  0, 0),
    458: (8,  0, 0),
    459: (8,  0, 0),
    460: (8,  0, 0),
    461: (8,  0, 0),
    462: (8,  0, 0),
    463: (8,  0, 0),
    464: (8,  0, 0),
    465: (8,  0, 0),
    466: (8,  0, 0),
    467: (8,  0, 0),
    468: (8,  0, 0),
    469: (8,  0, 0),
    470: (8,  0, 0),
    471: (8,  0, 0),
    472: (8,  0, 0),
    473: (8,  0, 0),
    474: (8,  0, 0),
    475: (8,  0, 0),
    476: (8,  0, 0),
    477: (8,  0, 0),
    478: (8,  0, 0),
    479: (8,  0, 0),
    480: (8,  0, 0),
    481: (8,  0, 0),
    482: (8,  0, 0),
    483: (8,  0, 0),
    484: (8,  0, 0),
    485: (8,  0, 0),
    486: (8,  0, 0),
    487: (8,  0, 0),
    488: (8,  0, 0),
    489: (8,  0, 0),
    490: (8,  0, 0),
    491: (8,  0, 0),
    492: (8,  0, 0),
    493: (8,  0, 0),
    494: (8,  0, 0),
    495: (8,  0, 0),
    496: (8,  0, 0),
    497: (8,  0, 0),
    498: (8,  0, 0),
    499: (8,  0, 0),
    500: (8,  0, 0),
    501: (8,  0, 0),
    502: (8,  0, 0),
    503: (8,  0, 0),
    504: (8,  0, 0),
    505: (8,  0, 0),
    506: (8,  0, 0),
    507: (8,  0, 0),
    508: (8,  0, 0),
    509: (8,  0, 0),
    510: (8,  0, 0),
    # ── Observed below D2R range (base game unsaved or unknown; 8-bit stubs) ─────
    69:  (8,  0, 0),
    101: (8,  0, 0),
    161: (8,  0, 0),
    169: (8,  0, 0),
    173: (8,  0, 0),   # target0
    174: (8,  0, 0),   # target1
    175: (8,  0, 0),
    176: (8,  0, 0),   # conversion_level
    177: (8,  0, 0),   # conversion_maxhp
    178: (8,  0, 0),   # unit_dooverlay
    182: (8,  0, 0),   # armor_override_percent
    183: (8,  0, 0),   # lasthitreactframe
    184: (8,  0, 0),   # create_season
    212: (8,  0, 0),
    265: (8,  0, 0),   # item_absorb_slash_percent
    266: (8,  0, 0),   # item_absorb_crush_percent
    267: (8,  0, 0),   # item_absorb_thrust_percent
    309: (8,  0, 0),   # item_damage_vs_monster
    310: (8,  0, 0),   # item_damage_percent_vs_monster
    311: (8,  0, 0),   # item_tohit_vs_monster
    312: (8,  0, 0),   # item_tohit_percent_vs_monster
    313: (8,  0, 0),   # item_ac_vs_monster
    314: (8,  0, 0),   # item_ac_percent_vs_monster
    315: (8,  0, 0),
    328: (8,  0, 0),   # pierce_idx
    359: (8,  0, 0),   # skill_cooldown
    360: (8,  0, 0),   # skill_missile_damage_scale
    363: (8,  0, 0),
    364: (8,  0, 0),   # customization_index
    367: (8,  0, 0),   # heraldtier
}

# Stat IDs that are character/entity state values — they can never legitimately
# appear in an item property list.  If we see one it means the quality-field
# offset detection landed on a false-positive position, so we reject it.
# 4=statpts, 5=newskills, 6=hitpoints, 8=mana, 10=stamina, 12=level,
# 13=experience, 14=gold, 15=goldbank, 29=lastexp, 30=nextexp,
# 353=source_unit_type, 354=source_unit_id
_PROPERTY_BLOCKLIST: frozenset[int] = frozenset({4, 5, 6, 8, 10, 12, 13, 14, 15, 29, 30, 353, 354})

# D2 character class names by index (for item_addclassskills param)
_CLASS_NAMES = {0: "Amazon", 1: "Sorceress", 2: "Necromancer", 3: "Paladin",
                4: "Barbarian", 5: "Druid", 6: "Assassin"}

# Skill names by ID (from skills.txt)
_SKILL_NAMES: dict[int, str] = {
    0: 'Attack',
    1: 'Kick',
    2: 'Throw',
    3: 'Unsummon',
    4: 'Left Hand Throw',
    5: 'Left Hand Swing',
    6: 'Magic Arrow',
    7: 'Fire Arrow',
    8: 'Inner Sight',
    9: 'Critical Strike',
    10: 'Jab',
    11: 'Cold Arrow',
    12: 'Multiple Shot',
    13: 'Dodge',
    14: 'Power Strike',
    15: 'Poison Javelin',
    16: 'Exploding Arrow',
    17: 'Slow Missiles',
    18: 'Avoid',
    19: 'Impale',
    20: 'Lightning Bolt',
    21: 'Ice Arrow',
    22: 'Guided Arrow',
    23: 'Penetrate',
    24: 'Charged Strike',
    25: 'Plague Javelin',
    26: 'Strafe',
    27: 'Immolation Arrow',
    28: 'Dopplezon',
    29: 'Evade',
    30: 'Fend',
    31: 'Freezing Arrow',
    32: 'Valkyrie',
    33: 'Pierce',
    34: 'Lightning Strike',
    35: 'Lightning Fury',
    36: 'Fire Bolt',
    37: 'Warmth',
    38: 'Charged Bolt',
    39: 'Ice Bolt',
    40: 'Frozen Armor',
    41: 'Inferno',
    42: 'Static Field',
    43: 'Telekinesis',
    44: 'Frost Nova',
    45: 'Ice Blast',
    46: 'Blaze',
    47: 'Fire Ball',
    48: 'Nova',
    49: 'Lightning',
    50: 'Shiver Armor',
    51: 'Fire Wall',
    52: 'Enchant',
    53: 'Chain Lightning',
    54: 'Teleport',
    55: 'Glacial Spike',
    56: 'Meteor',
    57: 'Thunder Storm',
    58: 'Energy Shield',
    59: 'Blizzard',
    60: 'Chilling Armor',
    61: 'Fire Mastery',
    62: 'Hydra',
    63: 'Lightning Mastery',
    64: 'Frozen Orb',
    65: 'Cold Mastery',
    66: 'Amplify Damage',
    67: 'Teeth',
    68: 'Bone Armor',
    69: 'Skeleton Mastery',
    70: 'Raise Skeleton',
    71: 'Dim Vision',
    72: 'Weaken',
    73: 'Poison Dagger',
    74: 'Corpse Explosion',
    75: 'Clay Golem',
    76: 'Iron Maiden',
    77: 'Terror',
    78: 'Bone Wall',
    79: 'Golem Mastery',
    80: 'Raise Skeletal Mage',
    81: 'Confuse',
    82: 'Life Tap',
    83: 'Poison Explosion',
    84: 'Bone Spear',
    85: 'BloodGolem',
    86: 'Attract',
    87: 'Decrepify',
    88: 'Bone Prison',
    89: 'Summon Resist',
    90: 'IronGolem',
    91: 'Lower Resist',
    92: 'Poison Nova',
    93: 'Bone Spirit',
    94: 'FireGolem',
    95: 'Revive',
    96: 'Sacrifice',
    97: 'Smite',
    98: 'Might',
    99: 'Prayer',
    100: 'Resist Fire',
    101: 'Holy Bolt',
    102: 'Holy Fire',
    103: 'Thorns',
    104: 'Defiance',
    105: 'Resist Cold',
    106: 'Zeal',
    107: 'Charge',
    108: 'Blessed Aim',
    109: 'Cleansing',
    110: 'Resist Lightning',
    111: 'Vengeance',
    112: 'Blessed Hammer',
    113: 'Concentration',
    114: 'Holy Freeze',
    115: 'Vigor',
    116: 'Conversion',
    117: 'Holy Shield',
    118: 'Holy Shock',
    119: 'Sanctuary',
    120: 'Meditation',
    121: 'Fist of the Heavens',
    122: 'Fanaticism',
    123: 'Conviction',
    124: 'Redemption',
    125: 'Salvation',
    126: 'Bash',
    127: 'Blade Mastery',
    128: 'Axe Mastery',
    129: 'Mace Mastery',
    130: 'Howl',
    131: 'Find Potion',
    132: 'Leap',
    133: 'Double Swing',
    134: 'Pole Arm Mastery',
    135: 'Throwing Mastery',
    136: 'Spear Mastery',
    137: 'Taunt',
    138: 'Shout',
    139: 'Stun',
    140: 'Double Throw',
    141: 'Increased Stamina',
    142: 'Find Item',
    143: 'Leap Attack',
    144: 'Concentrate',
    145: 'Iron Skin',
    146: 'Battle Cry',
    147: 'Frenzy',
    148: 'Increased Speed',
    149: 'Battle Orders',
    150: 'Grim Ward',
    151: 'Whirlwind',
    152: 'Berserk',
    153: 'Natural Resistance',
    154: 'War Cry',
    155: 'Battle Command',
    156: 'Fire Hit',
    157: 'UnHolyBolt',
    158: 'SkeletonRaise',
    159: 'MaggotEgg',
    160: 'ShamanFire',
    161: 'MagottUp',
    162: 'MagottDown',
    163: 'MagottLay',
    164: 'AndrialSpray',
    165: 'Jump',
    166: 'Swarm Move',
    167: 'Nest',
    168: 'Quick Strike',
    169: 'VampireFireball',
    170: 'VampireFirewall',
    171: 'VampireMeteor',
    172: 'GargoyleTrap',
    173: 'SpiderLay',
    174: 'VampireHeal',
    175: 'VampireRaise',
    176: 'Submerge',
    177: 'FetishAura',
    178: 'FetishInferno',
    179: 'ZakarumHeal',
    180: 'Emerge',
    181: 'Resurrect',
    182: 'Bestow',
    183: 'MissileSkill1',
    184: 'MonTeleport',
    185: 'PrimeLightning',
    186: 'PrimeBolt',
    187: 'PrimeBlaze',
    188: 'PrimeFirewall',
    189: 'PrimeSpike',
    190: 'PrimeIceNova',
    191: 'PrimePoisonball',
    192: 'PrimePoisonNova',
    193: 'DiabLight',
    194: 'DiabCold',
    195: 'DiabFire',
    196: 'FingerMageSpider',
    197: 'DiabWall',
    198: 'DiabRun',
    199: 'DiabPrison',
    200: 'PoisonBallTrap',
    201: 'AndyPoisonBolt',
    202: 'HireableMissile',
    203: 'DesertTurret',
    204: 'ArcaneTower',
    205: 'MonBlizzard',
    206: 'Mosquito',
    207: 'CursedBallTrapRight',
    208: 'CursedBallTrapLeft',
    209: 'MonFrozenArmor',
    210: 'MonBoneArmor',
    211: 'MonBoneSpirit',
    212: 'MonCurseCast',
    213: 'HellMeteor',
    214: 'RegurgitatorEat',
    215: 'MonFrenzy',
    216: 'QueenDeath',
    217: 'Scroll of Identify',
    218: 'Book of Identify',
    219: 'Scroll of Townportal',
    220: 'Book of Townportal',
    221: 'Raven',
    222: 'Plague Poppy',
    223: 'Wearwolf',
    224: 'Shape Shifting',
    225: 'Firestorm',
    226: 'Oak Sage',
    227: 'Summon Spirit Wolf',
    228: 'Wearbear',
    229: 'Molten Boulder',
    230: 'Arctic Blast',
    231: 'Cycle of Life',
    232: 'Feral Rage',
    233: 'Maul',
    234: 'Eruption',
    235: 'Cyclone Armor',
    236: 'Heart of Wolverine',
    237: 'Summon Fenris',
    238: 'Rabies',
    239: 'Fire Claws',
    240: 'Twister',
    241: 'Vines',
    242: 'Hunger',
    243: 'Shock Wave',
    244: 'Volcano',
    245: 'Tornado',
    246: 'Spirit of Barbs',
    247: 'Summon Grizzly',
    248: 'Fury',
    249: 'Armageddon',
    250: 'Hurricane',
    251: 'Fire Trauma',
    252: 'Claw Mastery',
    253: 'Psychic Hammer',
    254: 'Tiger Strike',
    255: 'Dragon Talon',
    256: 'Shock Field',
    257: 'Blade Sentinel',
    258: 'Quickness',
    259: 'Fists of Fire',
    260: 'Dragon Claw',
    261: 'Charged Bolt Sentry',
    262: 'Wake of Fire Sentry',
    263: 'Weapon Block',
    264: 'Cloak of Shadows',
    265: 'Cobra Strike',
    266: 'Blade Fury',
    267: 'Fade',
    268: 'Shadow Warrior',
    269: 'Claws of Thunder',
    270: 'Dragon Tail',
    271: 'Lightning Sentry',
    272: 'Inferno Sentry',
    273: 'Mind Blast',
    274: 'Blades of Ice',
    275: 'Dragon Flight',
    276: 'Death Sentry',
    277: 'Blade Shield',
    278: 'Venom',
    279: 'Shadow Master',
    280: 'Royal Strike',
    281: 'Wake Of Destruction Sentry',
    282: 'Imp Inferno',
    283: 'Imp Fireball',
    284: 'Baal Taunt',
    285: 'Baal Corpse Explode',
    286: 'Baal Monster Spawn',
    287: 'Catapult Charged Ball',
    288: 'Catapult Spike Ball',
    289: 'Suck Blood',
    290: 'Cry Help',
    291: 'Healing Vortex',
    292: 'Teleport 2',
    293: 'Self-resurrect',
    294: 'Vine Attack',
    295: 'Overseer Whip',
    296: 'Barbs Aura',
    297: 'Wolverine Aura',
    298: 'Oak Sage Aura',
    299: 'Imp Fire Missile',
    300: 'Impregnate',
    301: 'Siege Beast Stomp',
    302: 'MinionSpawner',
    303: 'CatapultBlizzard',
    304: 'CatapultPlague',
    305: 'CatapultMeteor',
    306: 'BoltSentry',
    307: 'CorpseCycler',
    308: 'DeathMaul',
    309: 'Defense Curse',
    310: 'Blood Mana',
    311: 'mon inferno sentry',
    312: 'mon death sentry',
    313: 'sentry lightning',
    314: 'fenris rage',
    315: 'Baal Tentacle',
    316: 'Baal Nova',
    317: 'Baal Inferno',
    318: 'Baal Cold Missiles',
    319: 'MegademonInferno',
    320: 'EvilHutSpawner',
    321: 'CountessFirewall',
    322: 'ImpBolt',
    323: 'Horror Arctic Blast',
    324: 'death sentry ltng',
    325: 'VineCycler',
    326: 'BearSmite',
    327: 'Resurrect2',
    328: 'BloodLordFrenzy',
    329: 'Baal Teleport',
    330: 'Imp Teleport',
    331: 'Baal Clone Teleport',
    332: 'ZakarumLightning',
    333: 'VampireMissile',
    334: 'MephistoMissile',
    335: 'DoomKnightMissile',
    336: 'RogueMissile',
    337: 'HydraMissile',
    338: 'NecromageMissile',
    339: 'MonBow',
    340: 'MonFireArrow',
    341: 'MonColdArrow',
    342: 'MonExplodingArrow',
    343: 'MonFreezingArrow',
    344: 'MonPowerStrike',
    345: 'SuccubusBolt',
    346: 'MephFrostNova',
    347: 'MonIceSpear',
    348: 'ShamanIce',
    349: 'Diablogeddon',
    350: 'Delerium Change',
    351: 'NihlathakCorpseExplosion',
    352: 'SerpentCharge',
    353: 'Trap Nova',
    354: 'UnHolyBoltEx',
    355: 'ShamanFireEx',
    356: 'Imp Fire Missile Ex',
    357: 'Interact',
    358: 'Loot',
    359: 'TownPortal',
    360: 'EmoteWheel',
    361: 'SwapWeapons',
    362: 'Map',
    363: 'ShowItems',
    364: 'RunToggle',
    365: 'MonHolyFreeze',
    366: 'MonLeap',
    367: 'MonLeapAttack',
    368: 'MonHolyFire',
    369: 'MonHolyShock',
    370: 'CubeLoot',
    371: 'Mark of the Bear',
    372: 'Mark of the Wolf',
    373: 'Summon Goatman',
    374: 'Demonic Mastery',
    375: 'Death Mark',
    376: 'Summon Tainted',
    377: 'Summon Defiler',
    378: 'Blood Oath',
    379: 'Engorge',
    380: 'Blood Boil',
    381: 'Consume',
    382: 'Bind Demon',
    383: 'Levitate',
    384: 'Eldritch Blast',
    385: 'Hex Bane',
    386: 'Hex Siphon',
    387: 'Psychic Ward',
    388: 'Echoing Strike',
    389: 'Hex Purge',
    390: 'Blade Warp',
    391: 'Cleave',
    392: 'Mirrored Blades',
    393: 'Sigil Lethargy',
    394: 'Ring of Fire',
    395: 'Miasma Bolt',
    396: 'Sigil Rancor',
    397: 'Enhanced Entropy',
    398: 'Flame Wave',
    399: 'Miasma Chains',
    400: 'Sigil Death',
    401: 'Apocalypse',
    402: 'Abyss',
    403: 'Sigil Death Explosion',
    404: 'Hex Purge Explosion',
    405: 'Health Link',
    406: 'Cold Fissure',
    407: "Korlic's Leap Attack",
    408: 'Cold Enchant',
    409: 'Lightning Enchant',
    410: "Talic's Whirlwind",
    411: 'Townportal O Skill',
    412: 'Fire Twisters',
    413: 'Colossal Volcano',
    414: 'Colossal Thunder Storm',
    415: 'UberAncientsHeal',
    416: 'Goatman Stun',
    417: 'Goatman Frenzy',
    418: 'Goatman Berserk',
    419: 'Goatman Cleave',
    420: 'Tainted Resist Fire',
    421: 'Tainted Fire Bolt',
    422: 'Tainted Fire Ball',
    423: "Talic's Fire Pierce",
    424: "Madawc's Lightning Pierce",
    425: "Korlic's Cold Pierce",
    426: 'Charged Bolt Disk',
    427: "Korlic's Bash",
    428: 'HeraldThorns',
}

# Skill proc event names by stat_id
_PROC_EVENTS = {
    195: "Striking",
    196: "Killing a Monster",
    197: "Death",
    198: "Striking",  # on hit
    199: "Level-Up",
    201: "Being Struck",
}

# Stat IDs that form damage min+max pairs: min_id → (max_id, label, divisor)
# divisor: divide raw value by this for display (poison = /256 per frame, then *length/25)
_DMG_PAIRS: dict[int, tuple[int, str]] = {
    21:  (22,  "Damage"),
    23:  (24,  "Damage"),       # 2h bonus
    48:  (49,  "Fire Damage"),
    50:  (51,  "Lightning Damage"),
    52:  (53,  "Magic Damage"),
    54:  (55,  "Cold Damage"),
    57:  (58,  "Poison Damage"),
    159: (160, "Throw Damage"),
    185: (186, "Damage"),       # bonus min/max
}


def _format_properties(raw_props: list[tuple[int, int, int]]) -> list[str]:
    """
    Convert raw (stat_id, param, value) triples to human-readable stat lines.

    Combines min/max damage pairs and handles common display formats.
    """
    # Build lookup of stat_id → (param, value) for pair combination
    stat_map: dict[int, tuple[int, int]] = {}
    for sid, param, val in raw_props:
        stat_map.setdefault(sid, (param, val))

    lines: list[str] = []
    handled: set[int] = set()

    for sid, param, val in raw_props:
        if sid in handled:
            continue

        # ── Damage min+max pairs ──────────────────────────────────────
        if sid in _DMG_PAIRS:
            max_sid, label = _DMG_PAIRS[sid]
            if max_sid in stat_map:
                max_val = stat_map[max_sid][1]
                handled.add(sid)
                handled.add(max_sid)
                if sid == 57:   # poison: append duration
                    cold_dur = stat_map.get(59)
                    handled.add(59)
                    secs = round(cold_dur[1] / 25, 1) if cold_dur else "?"
                    # Poison damage values are stored as dmg_per_frame * 256;
                    # game shows (min+max)/2 * length / (25*256) total, but
                    # for simplicity show the range as-stored with a note.
                    lines.append(f"Adds {val}-{max_val} {label} over {secs}s")
                elif sid == 54:  # cold: append duration
                    dur = stat_map.get(56)
                    handled.add(56)
                    secs = round(dur[1] / 25, 1) if dur else "?"
                    lines.append(f"Adds {val}-{max_val} {label} ({secs}s)")
                else:
                    lines.append(f"Adds {val}-{max_val} {label}")
                continue

        handled.add(sid)

        # ── Boolean flags ─────────────────────────────────────────────
        bool_flags = {
            81:  "Knockback",
            108: "Slain Monsters Rest in Peace",
            115: "Ignore Target's Defense",
            117: "Prevent Monster Heal",
            118: "Half Freeze Duration",
            152: "Indestructible",
            153: "Cannot Be Frozen",
            157: "Magic Arrow",
            158: "Explosive Arrow",
        }
        if sid in bool_flags and val:
            lines.append(bool_flags[sid])
            continue

        # ── Attribute bonuses ─────────────────────────────────────────
        attr_map = {0: "Strength", 1: "Energy", 2: "Dexterity", 3: "Vitality"}
        if sid in attr_map:
            lines.append(f"{val:+} to {attr_map[sid]}")
            continue
        if sid == 127:
            lines.append(f"{val:+} to All Skills")
            continue
        if sid == 83:
            cls = _CLASS_NAMES.get(param, f"Class {param}")
            lines.append(f"{val:+} to {cls} Skill Levels")
            continue
        if sid in (97, 107):
            skill_name = _SKILL_NAMES.get(param, f"[Skill {param}]")
            lines.append(f"{val:+} to {skill_name}")
            continue
        if sid == 188:
            lines.append(f"{val:+} to [Skill Tab {param}]")
            continue

        # ── Life / Mana / Stamina ─────────────────────────────────────
        if sid == 7:
            lines.append(f"{val:+} to Life")
            continue
        if sid == 9:
            lines.append(f"{val:+} to Mana")
            continue
        if sid == 11:
            lines.append(f"{val:+} to Stamina")
            continue
        if sid == 74:
            lines.append(f"Replenish Life +{val}")
            continue
        if sid == 76:
            lines.append(f"{val:+}% to Maximum Life")
            continue
        if sid == 77:
            lines.append(f"{val:+}% to Maximum Mana")
            continue

        # ── Defense / Damage ──────────────────────────────────────────
        if sid == 31:
            lines.append(f"{val:+} Defense")
            continue
        if sid == 32:
            lines.append(f"{val:+} Defense vs. Missiles")
            continue
        if sid == 33:
            lines.append(f"{val:+} Defense vs. Melee")
            continue
        if sid == 16:
            lines.append(f"{val:+}% Enhanced Defense")
            continue
        if sid in (17, 18, 25):
            lines.append(f"{val:+}% Enhanced Damage")
            continue
        if sid == 19:
            lines.append(f"{val:+} to Attack Rating")
            continue
        if sid == 119:
            lines.append(f"{val:+}% to Attack Rating")
            continue
        if sid == 78:
            lines.append(f"Attacker Takes Damage of {val}")
            continue
        if sid == 128:
            lines.append(f"Attacker Takes Lightning Damage of {val}")
            continue

        # ── Resistances ───────────────────────────────────────────────
        res_map = {
            39: "Fire Resist", 41: "Lightning Resist",
            43: "Cold Resist",  45: "Poison Resist",
            37: "Magic Resist", 36: "Physical Damage Reduced",
        }
        max_res_map = {40: "Maximum Fire Resist", 42: "Maximum Lightning Resist",
                       44: "Maximum Cold Resist", 46: "Maximum Poison Resist"}
        if sid in res_map:
            lines.append(f"{val:+}% {res_map[sid]}")
            continue
        if sid in max_res_map:
            lines.append(f"{val:+}% to {max_res_map[sid]}")
            continue

        # ── Damage reducers ───────────────────────────────────────────
        if sid == 34:
            lines.append(f"Damage Reduced by {val}")
            continue
        if sid == 35:
            lines.append(f"Magic Damage Reduced by {val}")
            continue

        # ── Speed stats ───────────────────────────────────────────────
        speed_map = {
            93:  "Increased Attack Speed",
            96:  "Faster Run/Walk",
            99:  "Faster Hit Recovery",
            102: "Faster Block Rate",
            105: "Faster Cast Rate",
        }
        if sid in speed_map:
            lines.append(f"{val:+}% {speed_map[sid]}")
            continue

        # ── Gold / Magic Find ─────────────────────────────────────────
        if sid == 79:
            lines.append(f"{val:+}% Extra Gold from Monsters")
            continue
        if sid == 80:
            lines.append(f"{val:+}% Better Chance of Magic Items")
            continue

        # ── Life / Mana steal ─────────────────────────────────────────
        # (stored as raw float-like; display as fraction — not in this table)

        # ── Sockets ───────────────────────────────────────────────────
        if sid == 194:
            lines.append(f"Socketed ({val})")
            continue

        # ── Skill procs ───────────────────────────────────────────────
        if sid in _PROC_EVENTS:
            event = _PROC_EVENTS[sid]
            # param encodes skill_id (low 12 bits) + level (high 4 bits) in 16 bits
            skill_id = param & 0x1FF
            level    = (param >> 9) & 0x7F
            skill_name = _SKILL_NAMES.get(skill_id, f"[Skill {skill_id}]")
            lines.append(f"{val}% Chance to Cast Level {level} {skill_name} on {event}")
            continue
        if sid == 204:  # charged skill
            skill_id = param & 0x1FF
            max_chg  = (param >> 9) & 0x7F
            level    = (val >> 8) & 0xFF
            charges  = val & 0xFF
            skill_name = _SKILL_NAMES.get(skill_id, f"[Skill {skill_id}]")
            lines.append(f"Level {level} {skill_name} ({charges}/{max_chg} Charges)")
            continue

        # ── Aura ─────────────────────────────────────────────────────
        if sid == 151:
            skill_name = _SKILL_NAMES.get(param, f"[Skill {param}]")
            lines.append(f"Level {val} {skill_name} Aura When Equipped")
            continue

        # ── Misc hits/on-kill ─────────────────────────────────────────
        if sid == 86:
            lines.append(f"Heal {val} HP After Each Kill")
            continue
        if sid == 138:
            lines.append(f"{val:+} to Mana After Each Kill")
            continue
        if sid == 89:
            sign = "+" if val >= 0 else ""
            lines.append(f"{sign}{val} to Light Radius")
            continue
        if sid == 91:
            lines.append(f"Requirements {val}%")  # val is already negative (e.g. -25)
            continue
        if sid == 75:
            lines.append(f"{val:+}% Durability")
            continue
        if sid == 20:
            lines.append(f"{val:+}% to Block")
            continue
        if sid == 112:
            lines.append(f"Hit Blinds Target +{val}")
            continue
        if sid == 113:
            lines.append(f"Hit Causes Monster to Flee {val}%")
            continue
        if sid == 135:
            lines.append(f"{val}% Chance of Open Wounds")
            continue
        if sid == 136:
            lines.append(f"{val}% Chance of Crushing Blow")
            continue
        if sid == 141:
            lines.append(f"{val}% Deadly Strike")
            continue
        if sid == 150:
            lines.append(f"Slows Target by {val}%")
            continue
        if sid == 121:
            lines.append(f"{val:+}% Damage to Demons")
            continue
        if sid == 122:
            lines.append(f"{val:+}% Damage to Undead")
            continue
        if sid == 123:
            lines.append(f"{val:+} to Attack Rating vs. Demons")
            continue
        if sid == 124:
            lines.append(f"{val:+} to Attack Rating vs. Undead")
            continue
        if sid == 142:
            lines.append(f"Fire Absorb {val}%")
            continue
        if sid == 143:
            lines.append(f"{val:+} Fire Absorb")
            continue
        if sid == 144:
            lines.append(f"Lightning Absorb {val}%")
            continue
        if sid == 145:
            lines.append(f"{val:+} Lightning Absorb")
            continue
        if sid == 148:
            lines.append(f"Cold Absorb {val}%")
            continue
        if sid == 149:
            lines.append(f"{val:+} Cold Absorb")
            continue
        if sid == 146:
            lines.append(f"Magic Absorb {val}%")
            continue
        if sid == 147:
            lines.append(f"{val:+} Magic Absorb")
            continue
        if sid == 110:
            lines.append(f"Poison Length Reduced by {val}%")
            continue
        if sid in (187, 189, 190, 191, 192, 193):
            sunder_map = {187: "Cold", 189: "Fire", 190: "Lightning",
                          191: "Poison", 192: "Physical", 193: "Magic"}
            lines.append(f"{sunder_map[sid]} Sunder")
            continue

        # ── Per-level stats (show as "N per level") ───────────────────
        per_level = {214: "Defense", 215: "Defense%", 216: "Life", 217: "Mana",
                     218: "Max Damage", 219: "Enhanced Damage", 220: "Strength",
                     221: "Dexterity", 222: "Energy", 223: "Vitality",
                     230: "Cold Resist", 231: "Fire Resist", 232: "Lightning Resist",
                     233: "Poison Resist", 240: "Magic Find", 239: "Gold Find"}
        if sid in per_level:
            lines.append(f"{val:+} {per_level[sid]} per Character Level")
            continue

        # ── Life / Mana leech ─────────────────────────────────────────
        if sid == 60:
            lines.append(f"{val}% Life Stolen per Hit")
            continue
        if sid == 62:
            lines.append(f"{val}% Mana Stolen per Hit")
            continue

        # ── Level requirement ─────────────────────────────────────────
        if sid == 92 and val != 0:
            sign = "+" if val > 0 else ""
            lines.append(f"{sign}{val} to Level Requirement")
            continue
        if sid == 94 and val != 0:
            lines.append(f"Reduces Level Requirements by {val}%")
            continue

        # ── Elemental skills ──────────────────────────────────────────
        if sid == 126:
            elem_map = {0: "Fire", 1: "Cold", 2: "Lightning", 3: "Poison"}
            elem = elem_map.get(param, f"Element {param}")
            lines.append(f"{val:+} to {elem} Skills")
            continue

        # ── Curse resistance (D2R) ────────────────────────────────────
        if sid == 109 and val != 0:
            lines.append(f"{val:+}% Curse Resistance")
            continue

        # ── Vendor price discount ─────────────────────────────────────
        if sid == 87 and val != 0:
            lines.append(f"Prices Reduced by {val}%")
            continue

        # ── Damage to mana ────────────────────────────────────────────
        if sid == 114 and val != 0:
            lines.append(f"{val}% Damage Taken Goes to Mana")
            continue

        # ── Freeze target ─────────────────────────────────────────────
        if sid == 134 and val != 0:
            lines.append(f"Freezes Target +{val}")
            continue

        # Stats we know the bit-width of but don't display (bytime, passives, internal).
        # They must be in _STAT_TABLE to prevent parser desync; just silently skip display.

    return lines


def _is_valid_property_list(
    raw: bytes | bytearray,
    bit_start: int,
    max_bit: int,
) -> bool:
    """
    Heuristic to confirm bit_start is a real property list start.

    Reads up to 3 stats and returns True only if at least 2 consecutive
    stat_ids are in _STAT_TABLE (or the list opens with 0x1FF).

    A false-positive quality position will almost always have a garbage
    stat_id in the first or second slot that isn't in the table.
    """
    reader = BitReader(raw, bit_start)
    valid = 0
    for _ in range(3):
        if reader.tell() + 9 > max_bit:
            break
        sid = reader.read(9)
        if sid == 0x1FF:
            return valid >= 1    # sentinel is valid only after at least 1 known stat
        if sid not in _STAT_TABLE:
            return False         # unknown stat → false positive
        valid += 1
        save_bits, _, save_param = _STAT_TABLE[sid]
        needed = save_param + save_bits
        if reader.tell() + needed > max_bit:
            break
        reader.read(save_param) if save_param else None
        reader.read(save_bits)
    return valid >= 2


def _parse_property_list(
    raw: bytes | bytearray,
    bit_start: int,
    max_bit: int,
) -> list[tuple[int, int, int]]:
    """
    Read the property list starting at bit_start. Returns list of (stat_id, param, value).
    Stops on stat_id 0x1FF (end sentinel) or unknown stat_id (to avoid desync).
    """
    reader = BitReader(raw, bit_start)
    props: list[tuple[int, int, int]] = []

    for _ in range(64):  # cap iterations
        if reader.tell() + 9 > max_bit:
            break
        stat_id = reader.read(9)
        if stat_id == 0x1FF:
            break
        if stat_id in _PROPERTY_BLOCKLIST:
            break   # character stat — indicates wrong quality position; stop silently
        if stat_id not in _STAT_TABLE:
            log.warning("d2i_parser: unknown stat_id=%d, stopping property parse (add to _STAT_TABLE to fix)", stat_id)
            break   # unknown: stop safely rather than desyncing

        save_bits, save_add, save_param = _STAT_TABLE[stat_id]
        param = reader.read(save_param) if save_param else 0
        stored = reader.read(save_bits)
        value = stored - save_add
        props.append((stat_id, param, value))

    return props


# ─── Modern format constants ───────────────────────────────────────────────────

MODERN_HEADER_SIZE = 64   # bytes (also the size of each inter-page separator)
MODERN_SEP_SIZE    = 64   # separator between pages equals one header-size block

# Scan range for Modern format quality field (from item byte_start, NO JM prefix).
# D2R uses a variable-length item type encoding (not the 4-char ASCII of legacy D2),
# so the quality field offset varies per item in the range [108, 121].
# Empirically confirmed on 8 items: offsets observed are 110–115.
# Candidates are filtered by:
#   - ilvl (7 bits before quality) in [1, 99]
#   - uid <= _MOD_MAX_UNIQUE_ID for unique items
#   - sid <= _MOD_MAX_SET_ID for set items
_MOD_QUALITY_SCAN_START      = 104
_MOD_QUALITY_SCAN_END        = 130   # exclusive; used for Phase 1 (set/unique, tightly calibrated)
_MOD_QUALITY_SCAN_END_WIDE   = 145   # exclusive; used for Phase 2 (magic/rare/normal — wider to catch charms/jewels)
_MOD_MAX_UNIQUE_ID      = 512   # generous upper bound above D2R catalog max (~437)
_MOD_MAX_SET_ID         = 160   # upper bound above catalog max (~139); false positives seen at 200+

# Bit offset from item byte_start where the Huffman item type code begins.
# Confirmed empirically across cm1/cm2/cm3/rin/r03/fhl — all decode at bit 53.
_MOD_HUFFMAN_CODE_START = 53

# Reverse Huffman table: (bit_value, bit_length) → character.
# Derived from dschu012/d2s; D2R Modern stash uses Huffman-encoded 4-char item type codes.
_HUFFMAN_REVERSE: dict[tuple[int, int], str] = {
    (1, 2): ' ',
    (10, 4): 'b', (4, 4): 's',
    (15, 5): 'a', (2, 5): 'c', (11, 5): 'g', (24, 5): 'h', (23, 5): 'l',
    (22, 5): 'm', (19, 5): 'p', (7, 5): 'r', (6, 5): 't', (16, 5): 'u',
    (0, 5): 'w', (28, 5): 'x', (30, 5): '7', (14, 5): '9',
    (12, 6): '2', (8, 6): '8', (35, 6): 'd', (3, 6): 'e', (50, 6): 'f',
    (18, 6): 'k', (44, 6): 'n',
    (31, 7): '1', (91, 7): '3', (123, 7): '6', (63, 7): 'i', (127, 7): 'o',
    (59, 7): 'v', (40, 7): 'y',
    (223, 8): '0', (95, 8): '4', (104, 8): '5', (155, 8): 'q', (27, 8): 'z',
    (232, 9): 'j',
}

# Public mapping: stripped 4-char item type code → human-readable base item name.
# Used by stash_service to display the base item type for non-catalog Modern items.
# Codes are space-stripped (e.g. 'cm1' not 'cm1 '). Add new codes here as needed.
MOD_ITEM_NAMES: dict[str, str] = {
    # ── Runes ──────────────────────────────────────────────────────────────────
    "r01": "El Rune",    "r02": "Eld Rune",   "r03": "Tir Rune",   "r04": "Nef Rune",
    "r05": "Eth Rune",   "r06": "Ith Rune",   "r07": "Tal Rune",   "r08": "Ral Rune",
    "r09": "Ort Rune",   "r10": "Thul Rune",  "r11": "Amn Rune",   "r12": "Sol Rune",
    "r13": "Shael Rune", "r14": "Dol Rune",   "r15": "Hel Rune",   "r16": "Io Rune",
    "r17": "Lum Rune",   "r18": "Ko Rune",    "r19": "Fal Rune",   "r20": "Lem Rune",
    "r21": "Pul Rune",   "r22": "Um Rune",    "r23": "Mal Rune",   "r24": "Ist Rune",
    "r25": "Gul Rune",   "r26": "Vex Rune",   "r27": "Ohm Rune",   "r28": "Lo Rune",
    "r29": "Sur Rune",   "r30": "Ber Rune",   "r31": "Jah Rune",   "r32": "Cham Rune",
    "r33": "Zod Rune",
    # ── Charms ─────────────────────────────────────────────────────────────────
    "cm1": "Small Charm", "cm2": "Large Charm", "cm3": "Grand Charm",
    # ── Jewelry & miscellaneous ─────────────────────────────────────────────────
    "rin": "Ring", "amu": "Amulet", "jew": "Jewel",
    # ── Gems: Chipped / Flawed / Normal / Flawless / Perfect ───────────────────
    "gcv": "Chipped Amethyst",  "gfv": "Flawed Amethyst",  "gsv": "Amethyst",
    "gzv": "Flawless Amethyst", "gpv": "Perfect Amethyst",
    "gcy": "Chipped Topaz",     "gfy": "Flawed Topaz",     "gsy": "Topaz",
    "gly": "Flawless Topaz",    "gpy": "Perfect Topaz",
    "gcb": "Chipped Sapphire",  "gfb": "Flawed Sapphire",  "gsb": "Sapphire",
    "glb": "Flawless Sapphire", "gpb": "Perfect Sapphire",
    "gcg": "Chipped Emerald",   "gfg": "Flawed Emerald",   "gsg": "Emerald",
    "gig": "Flawless Emerald",  "gpg": "Perfect Emerald",
    "gcr": "Chipped Ruby",      "gfr": "Flawed Ruby",      "gsr": "Ruby",
    "glr": "Flawless Ruby",     "gpr": "Perfect Ruby",
    "gcw": "Chipped Diamond",   "gfw": "Flawed Diamond",   "gsw": "Diamond",
    "glw": "Flawless Diamond",  "gpw": "Perfect Diamond",
    "skc": "Chipped Skull",     "skf": "Flawed Skull",     "sku": "Skull",
    "skl": "Flawless Skull",    "skz": "Perfect Skull",
    # ── Quest / special items ───────────────────────────────────────────────────
    "key": "Key", "box": "Horadric Cube", "bks": "Scroll of Inifuss",
    "pk1": "Key of Terror", "pk2": "Key of Hate", "pk3": "Key of Destruction",
    "tr1": "Token of Absolution",
    # ── Helmets: Normal / Exceptional / Elite ──────────────────────────────────
    "cap": "Cap",        "skp": "Skull Cap",  "hlm": "Helm",
    "fhl": "Full Helm",  "ghm": "Great Helm", "crn": "Crown",  "msk": "Mask",
    "xap": "War Hat",    "xkp": "Sallet",     "xlm": "Casque",
    "xhl": "Basinet",    "xhm": "Giant Conch","xrn": "Winged Helm", "xsk": "Death Mask",
    "uap": "Shako",      "ukp": "Hydraskull", "ulm": "Armet",
    "uhl": "Giant Skull","uhm": "Spired Helm","urn": "Corona", "usk": "Demonhead",
    # ── Body Armor: Normal / Exceptional / Elite ────────────────────────────────
    "qui": "Quilted Armor",   "lea": "Leather Armor",    "hla": "Hard Leather Armor",
    "stu": "Studded Leather", "rng": "Ring Mail",         "scl": "Scale Mail",
    "chn": "Chain Mail",      "brs": "Breast Plate",      "spl": "Splint Mail",
    "plt": "Plate Mail",      "fld": "Field Plate",       "gth": "Gothic Plate",
    "ful": "Full Plate Mail", "arm": "Ancient Armor",     "ltp": "Light Plate",
    "xui": "Ghost Armor",     "xea": "Serpentskin Armor", "xla": "Demonhide Armor",
    "xtu": "Trellised Armor", "xng": "Linked Mail",       "xcl": "Tiger Mail",
    "xhn": "Mesh Armor",      "xrs": "Cuirass",           "xpl": "Russet Armor",
    "xlt": "Mage Plate",      "xld": "Boneweave",         "xth": "Balrog Skin",
    "xul": "Chaos Armor",     "xar": "Ornate Armor",
    "uui": "Dusk Shroud",     "uea": "Wyrmhide",          "ula": "Scarab Husk",
    "utu": "Wire Fleece",     "ung": "Diamond Mail",      "ucl": "Loricated Mail",
    "uhn": "Boneweave",       "urs": "Great Hauberk",     "upl": "Hellforge Plate",
    "ult": "Archon Plate",    "uld": "Kraken Shell",      "uth": "Lacquered Plate",
    "uul": "Shadow Plate",    "uar": "Sacred Armor",
    # ── Shields: Normal / Exceptional / Elite ──────────────────────────────────
    "buc": "Buckler",       "sml": "Small Shield",  "lrg": "Large Shield",
    "kit": "Kite Shield",   "tow": "Tower Shield",  "gts": "Gothic Shield",
    "xuc": "Defender",      "xml": "Round Shield",  "xlg": "Scutum",
    "xks": "Dragon Shield", "xow": "Pavise",        "xts": "Ancient Shield",
    "uuc": "Heater",        "uml": "Luna",          "ulg": "Hyperion",
    "uks": "Monarch",       "uow": "Aegis",         "uts": "Ward",
    # ── Gloves: Normal ─────────────────────────────────────────────────────────
    "lgl": "Leather Gloves", "vgl": "Heavy Gloves",     "mgl": "Chain Gloves",
    "tgl": "Light Gauntlets","hgl": "Gauntlets",
    # ── Boots: Normal ──────────────────────────────────────────────────────────
    "lbt": "Leather Boots",  "vbt": "Heavy Boots",      "mbt": "Chain Boots",
    "tbt": "Light Plate Boots","hbt": "Battle Boots",
    # ── Belts: Normal ──────────────────────────────────────────────────────────
    "blt": "Sash",  "vbl": "Light Belt", "mbl": "Belt", "tbl": "Heavy Belt", "hbl": "Plated Belt",
    # ── Weapons: Swords ─────────────────────────────────────────────
    "ssd": "Short Sword",
    "lsd": "Long Sword",
    "bsd": "Broad Sword",
    "scm": "Scimitar",
    "sbr": "Saber",
    "flc": "Falchion",
    "crs": "Crystal Sword",
    "bsw": "Bastard Sword",
    "clm": "Claymore",
    "gis": "Giant Sword",
    "gsd": "Great Sword",
    "2hs": "Two-Handed Sword",
    "9ss": "Gladius",
    "9bs": "Battle Sword",
    "9ls": "Rune Sword",
    "9cs": "Hand Scythe",
    "9b9": "Gothic Sword",
    "9ws": "Divine Scepter",
    "9wd": "Ancient Sword",
    "9sm": "Cutlass",
    "9sb": "Shamshir",
    "9cm": "Dacian Falx",
    "9gs": "Tusk Sword",
    "9dg": "Poignard",
    "9di": "Rondel",
    "9bl": "Stilleto",
    "9fc": "Tulwar",
    "9fb": "Zweihander",
    "7ss": "Falcata",
    "7bs": "Conquest Sword",
    "7ls": "Cryptic Sword",
    "7cs": "Battle Cestus",
    "7wd": "Mythical Sword",
    "7fb": "Colossal Sword",
    "7fc": "Hydra Edge",
    "7sm": "Ataghan",
    "7sb": "Elegant Blade",
    "7cm": "Highland Blade",
    "7gs": "Balrog Blade",
    "7dg": "Bone Knife",
    "7di": "Mithral Point",
    "7bl": "Legend Spike",
    "7b7": "Champion Sword",
    "72h": "Legend Sword",
    "7gd": "Colossus Blade",
    "7cr": "Phase Blade",
    "7ls": "Cryptic Sword",
    "7ws": "Caduceus",

    # ── Weapons: Axes ───────────────────────────────────────────────
    "hax": "Hand Axe",
    "axe": "Axe",
    "lax": "Large Axe",
    "2ax": "Double Axe",
    "gax": "Great Axe",
    "gix": "Giant Axe",
    "btx": "Battle Axe",
    "bax": "Broad Axe",
    "wax": "War Axe",
    "mau": "Maul",
    "gma": "Great Maul",
    "9ax": "Cleaver",
    "9ha": "Hatchet",
    "9la": "Military Axe",
    "9ba": "Bearded Axe",
    "9ga": "Gothic Axe",
    "9gi": "Ancient Axe",
    "9wa": "Naga",
    "9bt": "Tabar",
    "7ax": "Small Crescent",
    "7ha": "Tomahawk",
    "7la": "Feral Axe",
    "7ba": "Silver-edged Axe",
    "7ga": "Champion Axe",
    "7gi": "Glorious Axe",
    "7wa": "Berserker Axe",
    "7bt": "Decapitator",
    "72a": "Ettin Axe",

    # ── Weapons: Maces ──────────────────────────────────────────────
    "clb": "Club",
    "spc": "Spiked Club",
    "mst": "Morning Star",
    "fla": "Flail",
    "mac": "Mace",
    "whm": "War Hammer",
    "9cl": "Cudgel",
    "9sp": "Barbed Club",
    "9ma": "Flanged Mace",
    "9fl": "Knout",
    "9wh": "Battle Hammer",
    "9gm": "Martel de Fer",
    "9mt": "Jagged Star",
    "9m9": "War Club",
    "7cl": "Truncheon",
    "7sp": "Tyrant Club",
    "7ma": "Reinforced Mace",
    "7fl": "Scourge",
    "7wh": "Legendary Mallet",
    "7gm": "Thunder Maul",
    "7mt": "Devil Star",
    "7m7": "Ogre Maul",

    # ── Weapons: Polearms ───────────────────────────────────────────
    "bar": "Bardiche",
    "pax": "Poleaxe",
    "hal": "Halberd",
    "scy": "Scythe",
    "wsc": "War Scythe",
    "vou": "Voulge",
    "glv": "Glaive",
    "bld": "Blade",
    "9b7": "Lochaber Axe",
    "9s8": "Battle Scythe",
    "9wc": "Grim Scythe",
    "9h9": "Bec-de-Corbin",
    "9pa": "Partizan",
    "9gl": "Spiculum",
    "7s8": "Thresher",
    "7wc": "Giant Thresher",
    "7h7": "Great Poleaxe",
    "7pa": "Cryptic Axe",
    "7gl": "Ghost Glaive",
    "7o7": "Ogre Axe",
    "7vo": "Colossus Voulge",

    # ── Weapons: Spears ─────────────────────────────────────────────
    "spr": "Spear",
    "spt": "Spetum",
    "tri": "Trident",
    "brn": "Brandistock",
    "pik": "Pike",
    "9sr": "War Spear",
    "9tr": "Fuscina",
    "9p9": "Lance",
    "9st": "Yari",
    "7sr": "Hyperion Spear",
    "7tr": "Stygian Pike",
    "7p7": "War Pike",
    "7st": "Ghost Spear",

    # ── Weapons: Staves ─────────────────────────────────────────────
    "sst": "Short Staff",
    "lst": "Long Staff",
    "cst": "Gnarled Staff",
    "bst": "Battle Staff",
    "wst": "War Staff",
    "gsc": "Grand Scepter",
    "8ss": "Jo Staff",
    "8ls": "Quarterstaff",
    "8cs": "Cedar Staff",
    "8bs": "Gothic Staff",
    "8ws": "Rune Staff",
    "6ss": "Walking Stick",
    "6ls": "Stalagmite",
    "6cs": "Elder Staff",
    "6bs": "Shillelagh",
    "6ws": "Archon Staff",

    # ── Weapons: Wands ──────────────────────────────────────────────
    "wnd": "Wand",
    "ywn": "Yew Wand",
    "bwn": "Bone Wand",
    "gwn": "Grim Wand",
    "9wn": "Burnt Wand",
    "9bw": "Tomb Wand",
    "9yw": "Petrified Wand",
    "7wn": "Polished Wand",
    "7bw": "Lich Wand",
    "7yw": "Ghost Wand",

    # ── Weapons: Bows/Xbows ─────────────────────────────────────────
    "sbw": "Short Bow",
    "hbw": "Hunter's Bow",
    "lbw": "Long Bow",
    "cbw": "Composite Bow",
    "sbb": "Short Battle Bow",
    "lbb": "Long Battle Bow",
    "swb": "Short War Bow",
    "lwb": "Long War Bow",
    "lxb": "Light Crossbow",
    "mxb": "Crossbow",
    "hxb": "Heavy Crossbow",
    "rxb": "Repeating Crossbow",
    "8sb": "Edge Bow",
    "8lb": "Cedar Bow",
    "8cb": "Double Bow",
    "8hb": "Razor Bow",
    "8sw": "Rune Bow",
    "8lw": "Gothic Bow",
    "8s8": "Short Siege Bow",
    "8l8": "Long Siege Bow",
    "8lx": "Arbalest",
    "8mx": "Siege Crossbow",
    "8hx": "Ballista",
    "8rx": "Chu-Ko-Nu",
    "6sb": "Spider Bow",
    "6lb": "Shadow Bow",
    "6cb": "Great Bow",
    "6hb": "Blade Bow",
    "6sw": "Ward Bow",
    "6lw": "Hydra Bow",
    "6s7": "Diamond Bow",
    "6l7": "Crusader Bow",
    "6lx": "Pellet Bow",
    "6mx": "Gorgon Crossbow",
    "6hx": "Colossus Crossbow",
    "6rx": "Demon Crossbow",

    # ── Weapons: Throwing ───────────────────────────────────────────
    "tax": "Throwing Axe",
    "tkf": "Throwing Knife",
    "bal": "Balanced Axe",
    "bkf": "Balanced Knife",
    "9ta": "Francisca",
    "9tk": "Battle Dart",
    "9bk": "War Dart",
    "9b8": "Hurlbat",
    "7ta": "Flying Axe",
    "7tk": "Flying Knife",
    "7bk": "Winged Knife",
    "7b8": "Winged Axe",

    # ── Weapons: Katars ─────────────────────────────────────────────
    "ktr": "Katar",
    "wrb": "Wrist Blade",
    "clw": "Claws",
    "btl": "Blade Talons",
    "ces": "Cestus",
    "skr": "Scissors Katar",
    "axf": "Hatchet Hands",
    "9ar": "Quhab",
    "9qr": "Scissors Quhab",
    "9lw": "Greater Claws",
    "9cs": "Hand Scythe",
    "9xf": "Fascia",
    "7ar": "Suwayyah",
    "7qr": "Scissors Suwayyah",
    "7lw": "Feral Claws",
    "7cs": "Battle Cestus",
    "7xf": "War Fist",
    "7wb": "Wrist Sword",
    "7tw": "Runic Talons",

    # ── Weapons: Other ──────────────────────────────────────────────
    "dgr": "Dagger",
    "dir": "Dirk",
    "kri": "Kriss",
    "jav": "Javelin",
    "pil": "Pilum",
    "ssp": "Short Spear",
    "tsp": "Throwing Spear",
    "scp": "Scepter",
    "wsp": "War Scepter",
    "gsc": "Grand Scepter",
    "9dg": "Poignard",
    "9di": "Rondel",
    "9sc": "Rune Scepter",
    "9qs": "Holy Water Sprinkler",
    "9ja": "War Javelin",
    "9pi": "Great Pilum",
    "9gl": "Spiculum",
    "9ts": "Harpoon",
    "7dg": "Bone Knife",
    "7di": "Mithral Point",
    "7sc": "Mighty Scepter",
    "7qs": "Seraph Rod",
    "7ja": "Hyperion Javelin",
    "7pi": "Stygian Pilum",
    "7gl": "Ghost Glaive",
    "7ts": "Winged Harpoon",
    "flb": "Flamberge",
    "sbr": "Saber",
    "mpi": "Military Pick",
    "scy": "Scythe",
    "ob1": "Eagle Orb",
    "ob2": "Sacred Globe",
    "ob3": "Smoked Sphere",
    "ob4": "Clasped Orb",
    "ob5": "Jared's Stone",
    "ob6": "Glowing Orb",
    "ob7": "Crystalline Globe",
    "ob8": "Cloudy Sphere",
    "ob9": "Sparkling Ball",
    "oba": "Swirling Crystal",
    "obb": "Heavenly Stone",
    "obc": "Eldritch Orb",
    "obd": "Demon Heart",
    "obe": "Vortex Orb",
    "obf": "Dimensional Shard",

    # ── Amazon Weapons ──────────────────────────────────────────────
    "am1": "Stag Bow",
    "am2": "Reflex Bow",
    "am3": "Maiden Spear",
    "am4": "Maiden Pike",
    "am5": "Maiden Javelin",
    "am6": "Ashwood Bow",
    "am7": "Ceremonial Bow",
    "am8": "Ceremonial Spear",
    "am9": "Ceremonial Pike",
    "ama": "Ceremonial Javelin",
    "amb": "Matriarchal Bow",
    "amc": "Grand Matron Bow",
    "amd": "Matriarchal Spear",
    "ame": "Matriarchal Pike",
    "amf": "Matriarchal Javelin",

    # ── Barbarian Helms ─────────────────────────────────────────────
    "ba1": "Jawbone Cap",
    "ba2": "Fanged Helm",
    "ba3": "Horned Helm",
    "ba4": "Assault Helmet",
    "ba5": "Avenger Guard",
    "ba6": "Jawbone Visor",
    "ba7": "Lion Helm",
    "ba8": "Rage Mask",
    "ba9": "Savage Helmet",
    "baa": "Slayer Guard",
    "bab": "Carnage Helm",
    "bac": "Fury Visor",
    "bad": "Destroyer Helm",
    "bae": "Conqueror Crown",
    "baf": "Guardian Crown",

    # ── Druid Pelts ─────────────────────────────────────────────────
    "dr1": "Wolf Head",
    "dr2": "Hawk Helm",
    "dr3": "Antlers",
    "dr4": "Falcon Mask",
    "dr5": "Spirit Mask",
    "dr6": "Alpha Helm",
    "dr7": "Griffon Headress",
    "dr8": "Hunter's Guise",
    "dr9": "Sacred Feathers",
    "dra": "Totemic Mask",
    "drb": "Blood Spirit",
    "drc": "Sun Spirit",
    "drd": "Earth Spirit",
    "dre": "Sky Spirit",
    "drf": "Dream Spirit",

    # ── Necro Heads ─────────────────────────────────────────────────
    "ne1": "Preserved Head",
    "ne2": "Zombie Head",
    "ne3": "Unraveller Head",
    "ne4": "Gargoyle Head",
    "ne5": "Demon Head",
    "ne6": "Mummified Trophy",
    "ne7": "Fetish Trophy",
    "ne8": "Sexton Trophy",
    "ne9": "Cantor Trophy",
    "nea": "Heirophant Trophy",
    "neb": "Minion Skull",
    "ned": "Overseer Skull",
    "nee": "Succubus Skull",
    "nef": "Bloodlord Skull",
    "neg": "Hellspawn Skull",

    # ── Paladin Shields ─────────────────────────────────────────────
    "pa1": "Targe",
    "pa2": "Rondache",
    "pa3": "Heraldic Shield",
    "pa4": "Aerin Shield",
    "pa5": "Crown Shield",
    "pa6": "Akaran Targe",
    "pa7": "Akaran Rondache",
    "pa8": "Protector Shield",
    "pa9": "Gilded Shield",
    "paa": "Royal Shield",
    "pab": "Sacred Targe",
    "pac": "Sacred Rondache",
    "pad": "Ancient Shield",
    "pae": "Zakarum Shield",
    "paf": "Vortex Shield",

    # ── Circlets ────────────────────────────────────────────────────
    "ci0": "Circlet",
    "ci1": "Coronet",
    "ci2": "Tiara",
    "ci3": "Diadem",

    # ── Armor: Shields (missing) ────────────────────────────────────
    "spk": "Spiked Shield",
    "bsh": "Bone Shield",
    "xpk": "Barbed Shield",
    "xsh": "Grim Shield",
    "xit": "Dragon Shield",
    "uit": "Monarch",
    "upk": "Blade Barrier",
    "ush": "Troll Nest",
    "urg": "Hyperion",

    # ── Armor: Exc/Elite Gloves ─────────────────────────────────────
    "xvg": "Sharkskin Gloves",
    "xmg": "Heavy Bracers",
    "xtg": "Battle Gauntlets",
    "xhg": "War Gauntlets",
    "uvg": "Vampirebone Gloves",
    "umg": "Vambraces",
    "utg": "Crusader Gauntlets",
    "uhg": "Ogre Gauntlets",

    # ── Armor: Exc/Elite Boots ──────────────────────────────────────
    "xlb": "Demonhide Boots",
    "xvb": "Sharkskin Boots",
    "xmb": "Mesh Boots",
    "xtb": "Battle Boots",
    "xhb": "War Boots",
    "ulb": "Wyrmhide Boots",
    "uvb": "Scarabshell Boots",
    "umb": "Boneweave Boots",
    "utb": "Mirrored Boots",
    "uhb": "Myrmidon Greaves",

    # ── Armor: Exc/Elite Belts ──────────────────────────────────────
    "zlb": "Demonhide Sash",
    "zvb": "Sharkskin Belt",
    "zmb": "Mesh Belt",
    "ztb": "Battle Belt",
    "zhb": "War Belt",
    "ulc": "Spiderweb Sash",
    "uvc": "Vampirefang Belt",
    "umc": "Mithril Coil",
    "utc": "Troll Belt",
    "uhc": "Colossus Girdle",
    "lbl": "Sash",

    # ── Armor: Misc Missing ─────────────────────────────────────────
    "aar": "Ancient Armor",
    "bhm": "Bone Helm",
    "xh9": "Grim Helm",
    "uh9": "Bone Visage",
    "utp": "Archon Plate",

    # ── Misc items in stash ─────────────────────────────────────────
    "cjw": "Colossal Jewel",
    "glg": "Flawless Emerald",

    # ── Other missing items ────────────────────────────────────────
    "7br": "Mancatcher",
    "7gw": "Unearthed Wand",
    "7kr": "Fanged Knife",
    "7mp": "War Spike",
    "7s7": "Balrog Spear",
    "92a": "Twin Axe",
    "92h": "Espandon",
    "9br": "War Fork",
    "9cr": "Dimensional Blade",
    "9gd": "Executioner Sword",
    "9gw": "Grave Wand",
    "9kr": "Cinquedeas",
    "9mp": "Crowbill",
    "9s9": "Simbilan",
    "9tw": "Greater Talons",
    "9vo": "Bill",
    "9wb": "Wrist Spike",
    "cs2": "Crafted Sunder Charm",
    "qf2": "Khalim's Will",
    "wsd": "War Sword",
    "xrg": "Scutum",
    "xtp": "Mage Plate",

}


# ─── Affix name lookup tables (from D2R excel data files) ────────────────────

_MAGIC_PREFIXES: dict[int, str] = {
    2: 'Sturdy',
    3: 'Strong',
    4: 'Glorious',
    5: 'Blessed',
    6: 'Saintly',
    7: 'Holy',
    8: 'Devious',
    9: 'Fortified',
    13: 'Jagged',
    14: 'Deadly',
    15: 'Vicious',
    16: 'Brutal',
    17: 'Massive',
    18: 'Savage',
    19: 'Merciless',
    20: 'Vulpine',
    25: 'Tireless',
    26: 'Rugged',
    27: 'Bronze',
    28: 'Iron',
    29: 'Steel',
    30: 'Silver',
    32: 'Gold',
    33: 'Platinum',
    34: 'Meteoric',
    35: 'Sharp',
    36: 'Fine',
    37: "Warrior's",
    38: "Soldier's",
    39: "Knight's",
    40: "Lord's",
    41: "King's",
    42: 'Howling',
    43: 'Fortuitous',
    49: 'Glimmering',
    50: 'Glowing',
    53: "Lizard's",
    55: "Snake's",
    56: "Serpent's",
    57: "Serpent's",
    58: "Drake's",
    59: "Dragon's",
    60: "Dragon's",
    61: "Wyrm's",
    64: 'Prismatic',
    65: 'Prismatic',
    66: 'Azure',
    67: 'Lapis',
    68: 'Lapis',
    69: 'Cobalt',
    70: 'Cobalt',
    72: 'Sapphire',
    75: 'Crimson',
    76: 'Burgundy',
    77: 'Burgundy',
    78: 'Garnet',
    79: 'Garnet',
    81: 'Ruby',
    84: 'Ocher',
    85: 'Tangerine',
    86: 'Tangerine',
    87: 'Coral',
    88: 'Coral',
    90: 'Amber',
    93: 'Beryl',
    94: 'Jade',
    95: 'Jade',
    96: 'Viridian',
    97: 'Viridian',
    99: 'Emerald',
    101: "Fletcher's",
    102: "Archer's",
    103: "Archer's",
    104: "Monk's",
    105: "Priest's",
    106: "Priest's",
    107: "Summoner's",
    108: "Necromancer's",
    109: "Necromancer's",
    110: "Angel's",
    111: "Arch-Angel's",
    112: "Arch-Angel's",
    113: "Slayer's",
    114: "Berserker's",
    115: "Berserker's",
    118: 'Triumphant',
    120: 'Stout',
    121: 'Stout',
    122: 'Stout',
    123: 'Burly',
    124: 'Burly',
    125: 'Burly',
    126: 'Stalwart',
    127: 'Stalwart',
    128: 'Stalwart',
    129: 'Stout',
    130: 'Stout',
    131: 'Stout',
    132: 'Burly',
    133: 'Burly',
    134: 'Stalwart',
    135: 'Stalwart',
    136: 'Stout',
    137: 'Stout',
    138: 'Burly',
    139: 'Stalwart',
    140: 'Blanched',
    141: 'Eburin',
    142: 'Bone',
    143: 'Ivory',
    144: 'Sturdy',
    145: 'Sturdy',
    146: 'Strong',
    147: 'Glorious',
    148: 'Blessed',
    149: 'Saintly',
    150: 'Holy',
    151: 'Godly',
    152: 'Devious',
    153: 'Blank',
    154: 'Null',
    155: 'Antimagic',
    156: 'Red',
    157: 'Red',
    158: 'Sanguinary',
    159: 'Sanguinary',
    160: 'Bloody',
    161: 'Red',
    162: 'Sanguinary',
    163: 'Bloody',
    164: 'Red',
    165: 'Sanguinary',
    166: 'Bloody',
    167: 'Scarlet',
    168: 'Crimson',
    169: 'Jagged',
    170: 'Jagged',
    171: 'Jagged',
    172: 'Forked',
    173: 'Forked',
    174: 'Serrated',
    175: 'Serrated',
    176: 'Jagged',
    177: 'Jagged',
    178: 'Forked',
    179: 'Forked',
    180: 'Serrated',
    181: 'Jagged',
    182: 'Forked',
    183: 'Serrated',
    184: 'Carbuncle',
    185: 'Carmine',
    186: 'Vermillion',
    187: 'Jagged',
    188: 'Deadly',
    189: 'Vicious',
    190: 'Brutal',
    191: 'Massive',
    192: 'Savage',
    193: 'Merciless',
    194: 'Ferocious',
    195: 'Cruel',
    196: 'Cinnabar',
    197: 'Rusty',
    198: 'Realgar',
    199: 'Ruby',
    200: 'Vulpine',
    201: 'Dun',
    202: 'Tireless',
    203: 'Tireless',
    204: 'Brown',
    205: 'Rugged',
    206: 'Rugged',
    207: 'Rugged',
    208: 'Rugged',
    209: 'Rugged',
    210: 'Rugged',
    211: 'Rugged',
    212: 'Rugged',
    213: 'Rugged',
    214: 'Rugged',
    215: 'Rugged',
    216: 'Vigorous',
    217: 'Chestnut',
    218: 'Maroon',
    219: 'Bronze',
    220: 'Bronze',
    221: 'Bronze',
    222: 'Iron',
    223: 'Iron',
    224: 'Iron',
    225: 'Steel',
    226: 'Steel',
    227: 'Steel',
    228: 'Bronze',
    229: 'Bronze',
    230: 'Bronze',
    231: 'Iron',
    232: 'Iron',
    233: 'Steel',
    234: 'Steel',
    235: 'Bronze',
    236: 'Bronze',
    237: 'Iron',
    238: 'Steel',
    239: 'Bronze',
    240: 'Iron',
    241: 'Steel',
    242: 'Silver',
    243: 'Gold',
    244: 'Platinum',
    245: 'Meteoric',
    246: 'Strange',
    247: 'Weird',
    248: 'Nickel',
    249: 'Tin',
    250: 'Silver',
    251: 'Argent',
    252: 'Fine',
    253: 'Fine',
    254: 'Sharp',
    255: 'Fine',
    256: 'Sharp',
    257: 'Fine',
    258: 'Sharp',
    259: 'Fine',
    260: "Warrior's",
    261: "Soldier's",
    262: "Knight's",
    263: "Lord's",
    264: "King's",
    265: "Master's",
    266: "Grandmaster's",
    267: 'Glimmering',
    268: 'Glowing',
    269: 'Bright',
    270: 'Screaming',
    271: 'Howling',
    272: 'Wailing',
    273: 'Screaming',
    274: 'Howling',
    275: 'Wailing',
    276: 'Lucky',
    277: 'Lucky',
    278: 'Lucky',
    279: 'Lucky',
    280: 'Lucky',
    281: 'Lucky',
    282: 'Felicitous',
    283: 'Fortuitous',
    284: 'Emerald',
    285: "Lizard's",
    286: "Lizard's",
    287: "Lizard's",
    288: "Snake's",
    289: "Snake's",
    290: "Snake's",
    291: "Serpent's",
    292: "Serpent's",
    293: "Serpent's",
    294: "Lizard's",
    295: "Lizard's",
    296: "Lizard's",
    297: "Snake's",
    298: "Snake's",
    299: "Serpent's",
    300: "Serpent's",
    301: "Lizard's",
    302: "Lizard's",
    303: "Snake's",
    304: "Serpent's",
    305: "Lizard's",
    306: "Snake's",
    307: "Serpent's",
    308: "Serpent's",
    309: "Drake's",
    310: "Dragon's",
    311: "Dragon's",
    312: "Wyrm's",
    313: "Great Wyrm's",
    314: "Bahamut's",
    315: 'Zircon',
    316: 'Jacinth',
    317: 'Turquoise',
    318: 'Shimmering',
    319: 'Shimmering',
    320: 'Shimmering',
    321: 'Shimmering',
    322: 'Shimmering',
    323: 'Shimmering',
    324: 'Shimmering',
    325: 'Rainbow',
    326: 'Scintillating',
    327: 'Prismatic',
    328: 'Chromatic',
    329: 'Shimmering',
    330: 'Rainbow',
    331: 'Scintillating',
    332: 'Prismatic',
    333: 'Chromatic',
    334: 'Shimmering',
    335: 'Rainbow',
    336: 'Scintillating',
    337: 'Shimmering',
    338: 'Scintillating',
    339: 'Azure',
    340: 'Lapis',
    341: 'Cobalt',
    342: 'Sapphire',
    343: 'Azure',
    344: 'Lapis',
    345: 'Cobalt',
    346: 'Sapphire',
    347: 'Azure',
    348: 'Lapis',
    349: 'Cobalt',
    350: 'Sapphire',
    351: 'Azure',
    352: 'Lapis',
    353: 'Lapis',
    354: 'Cobalt',
    355: 'Cobalt',
    356: 'Sapphire',
    357: 'Lapis Lazuli',
    358: 'Sapphire',
    359: 'Crimson',
    360: 'Russet',
    361: 'Garnet',
    362: 'Ruby',
    363: 'Crimson',
    364: 'Russet',
    365: 'Garnet',
    366: 'Ruby',
    367: 'Crimson',
    368: 'Russet',
    369: 'Garnet',
    370: 'Ruby',
    371: 'Russet',
    372: 'Russet',
    373: 'Garnet',
    374: 'Garnet',
    375: 'Ruby',
    376: 'Garnet',
    377: 'Ruby',
    378: 'Tangerine',
    379: 'Ocher',
    380: 'Coral',
    381: 'Amber',
    382: 'Tangerine',
    383: 'Ocher',
    384: 'Coral',
    385: 'Amber',
    386: 'Tangerine',
    387: 'Ocher',
    388: 'Coral',
    389: 'Amber',
    390: 'Tangerine',
    391: 'Ocher',
    392: 'Ocher',
    393: 'Coral',
    394: 'Coral',
    395: 'Amber',
    396: 'Camphor',
    397: 'Ambergris',
    398: 'Beryl',
    399: 'Viridian',
    400: 'Jade',
    401: 'Emerald',
    402: 'Beryl',
    403: 'Viridian',
    404: 'Jade',
    405: 'Emerald',
    406: 'Beryl',
    407: 'Viridian',
    408: 'Jade',
    409: 'Emerald',
    410: 'Beryl',
    411: 'Viridian',
    412: 'Viridian',
    413: 'Jade',
    414: 'Jade',
    415: 'Emerald',
    416: 'Beryl',
    417: 'Jade',
    418: 'Triumphant',
    419: 'Victorious',
    420: 'Aureolin',
    421: "Mechanist's",
    422: "Artificer's",
    423: "Jeweler's",
    424: 'Assamic',
    425: 'Arcadian',
    426: 'Unearthly',
    427: 'Astral',
    428: 'Elysian',
    429: 'Celestial',
    430: 'Diamond',
    431: "Fletcher's",
    432: "Acrobat's",
    433: "Harpoonist's",
    434: "Fletcher's",
    435: "Bowyer's",
    436: "Archer's",
    437: "Acrobat's",
    438: "Gymnast's",
    439: "Athlete's",
    440: "Harpoonist's",
    441: "Spearmaiden's",
    442: "Lancer's",
    443: 'Burning',
    444: 'Sparking',
    445: 'Chilling',
    446: 'Burning',
    447: 'Blazing',
    448: 'Volcanic',
    449: 'Sparking',
    450: 'Charged',
    451: 'Powered',
    452: 'Chilling',
    453: 'Freezing',
    454: 'Glacial',
    455: 'Hexing',
    456: 'Fungal',
    457: "Graverobber's",
    458: 'Hexing',
    459: 'Blighting',
    460: 'Accursed',
    461: 'Fungal',
    462: 'Noxious',
    463: 'Venomous',
    464: "Graverobber's",
    465: 'Vodoun',
    466: "Golemlord's",
    467: 'Lion Branded',
    468: "Captain's",
    469: "Preserver's",
    470: 'Lion Branded',
    471: 'Hawk Branded',
    472: 'Rose Branded',
    473: "Captain's",
    474: "Commander's",
    475: "Marshal's",
    476: "Preserver's",
    477: "Warder's",
    478: "Guardian's",
    479: "Expert's",
    480: 'Fanatic',
    481: 'Sounding',
    482: "Expert's",
    483: "Veteran's",
    484: "Master's",
    485: 'Fanatic',
    486: 'Raging',
    487: 'Furious',
    488: 'Sounding',
    489: 'Resonant',
    490: 'Echoing',
    491: "Trainer's",
    492: 'Spiritual',
    493: "Nature's",
    494: "Trainer's",
    495: "Caretaker's",
    496: "Keeper's",
    497: 'Spiritual',
    498: 'Feral',
    499: 'Communal',
    500: "Nature's",
    501: "Terra's",
    502: "Gaea's",
    503: 'Entrapping',
    504: "Mentalist's",
    505: "Shogukusha's",
    506: 'Entrapping',
    507: "Trickster's",
    508: 'Cunning',
    509: "Mentalist's",
    510: 'Psychic',
    511: 'Shadow',
    512: "Shogukusha's",
    513: "Sensei's",
    514: "Kenshi's",
    515: 'Miocene',
    516: 'Miocene',
    517: 'Oligocene',
    518: 'Oligocene',
    519: 'Eocene',
    520: 'Eocene',
    521: 'Paleocene',
    522: 'Paleocene',
    523: "Knave's",
    524: "Jack's",
    525: "Jester's",
    526: "Joker's",
    527: 'Trump',
    528: 'Loud',
    529: 'Calling',
    530: 'Yelling',
    531: 'Shouting',
    532: 'Gritty',
    533: 'Paradox',
    534: 'Paradox',
    535: 'Robineye',
    536: 'Sparroweye',
    537: 'Falconeye',
    538: 'Hawkeye',
    539: 'Eagleeye',
    540: 'Visionary',
    541: 'Mnemonic',
    542: 'Snowflake',
    543: 'Shivering',
    544: 'Boreal',
    545: 'Hibernal',
    546: 'Ember',
    547: 'Smoldering',
    548: 'Smoking',
    549: 'Flaming',
    550: 'Scorching',
    551: 'Static',
    552: 'Glowing',
    553: 'Buzzing',
    554: 'Arcing',
    555: 'Shocking',
    556: 'Septic',
    557: 'Envenomed',
    558: 'Corosive',
    559: 'Toxic',
    560: 'Pestilent',
    561: "Maiden's",
    562: "Valkyrie's",
    563: "Maiden's",
    564: "Valkyrie's",
    565: "Monk's",
    566: "Priest's",
    567: "Monk's",
    568: "Priest's",
    569: "Monk's",
    570: "Priest's",
    571: "Summoner's",
    572: "Necromancer's",
    573: "Summoner's",
    574: "Necromancer's",
    575: "Angel's",
    576: "Arch-Angel's",
    577: "Angel's",
    578: "Arch-Angel's",
    579: "Slayer's",
    580: "Berserker's",
    581: "Slayer's",
    582: "Berserker's",
    583: "Slayer's",
    584: "Berserker's",
    585: "Shaman's",
    586: "Hierophant's",
    587: "Shaman's",
    588: "Hierophant's",
    589: "Magekiller's",
    590: "Witch-hunter's",
    591: "Magekiller's",
    592: "Witch-hunter's",
    593: 'Compact',
    594: 'Thin',
    595: 'Dense',
    596: 'Consecrated',
    597: 'Pure',
    598: 'Sacred',
    599: 'Hallowed',
    600: 'Divine',
    601: 'Pearl',
    602: 'Crimson',
    603: 'Red',
    604: 'Sanguinary',
    605: 'Bloody',
    606: 'Red',
    607: 'Sanguinary',
    608: 'Red',
    609: 'Jagged',
    610: 'Forked',
    611: 'Serrated',
    612: 'Jagged',
    613: 'Forked',
    614: 'Jagged',
    615: 'Snowflake',
    616: 'Shivering',
    617: 'Boreal',
    618: 'Hibernal',
    619: 'Snowflake',
    620: 'Shivering',
    621: 'Boreal',
    622: 'Hibernal',
    623: 'Snowflake',
    624: 'Shivering',
    625: 'Boreal',
    626: 'Hibernal',
    627: 'Ember',
    628: 'Smoldering',
    629: 'Smoking',
    630: 'Flaming',
    631: 'Ember',
    632: 'Smoldering',
    633: 'Smoking',
    634: 'Flaming',
    635: 'Ember',
    636: 'Smoldering',
    637: 'Smoking',
    638: 'Flaming',
    639: 'Static',
    640: 'Glowing',
    641: 'Arcing',
    642: 'Shocking',
    643: 'Static',
    644: 'Glowing',
    645: 'Arcing',
    646: 'Shocking',
    647: 'Static',
    648: 'Glowing',
    649: 'Arcing',
    650: 'Shocking',
    651: 'Septic',
    652: 'Envenomed',
    653: 'Toxic',
    654: 'Pestilent',
    655: 'Septic',
    656: 'Envenomed',
    657: 'Toxic',
    658: 'Pestilent',
    659: 'Septic',
    660: 'Envenomed',
    661: 'Toxic',
    662: 'Pestilent',
    663: 'Tireless',
    664: "Lizard's",
    665: 'Azure',
    666: 'Crimson',
    667: 'Tangerine',
    668: 'Beryl',
    669: 'Godly',
    670: 'Cruel',
    671: 'Virulent',
    672: 'Virulent',
    673: 'Virulent',
    674: 'Virulent',
    675: 'Virulent',
    676: 'Incendiary',
    677: 'Incendiary',
    678: 'Incendiary',
    679: 'Incendiary',
    680: 'Incendiary',
    681: 'Gelid',
    682: 'Gelid',
    683: 'Gelid',
    684: 'Gelid',
    685: 'Gelid',
    686: 'Magnetic',
    687: 'Magnetic',
    688: 'Magnetic',
    689: 'Magnetic',
    690: 'Magnetic',
    691: 'Mystical',
    692: 'Mystical',
    693: 'Mystical',
    694: 'Mystical',
    695: 'Mystical',
    696: 'Breaching',
    697: 'Breaching',
    698: 'Breaching',
    699: 'Breaching',
    700: 'Breaching',
    701: 'Chaotic',
    702: 'Sullied',
    703: 'Fiendish',
    704: 'Chaotic',
    705: 'Erratic',
    706: 'Torrid',
    707: 'Sullied',
    708: 'TaintedAffix',
    709: 'Forbidden',
    710: 'Fiendish',
    711: 'Dreadful',
    712: 'Malevolent',
    713: "Devil's",
    714: "Arch-Devil's",
    715: "Devil's",
    716: "Arch-Devil's",
    717: 'Virulent',
    718: 'Incendiary',
    719: 'Gelid',
    720: 'Magnetic',
    721: 'Mystical',
    722: 'Breaching',
}

_MAGIC_SUFFIXES: dict[int, str] = {
    1: 'of Health',
    2: 'of Protection',
    3: 'of Absorption',
    4: 'of Life',
    6: 'of Warding',
    7: 'of the Sentinel',
    8: 'of Guarding',
    9: 'of Negation',
    11: 'of Piercing',
    12: 'of Bashing',
    13: 'of Puncturing',
    14: 'of Thorns',
    15: 'of Spikes',
    16: 'of Readiness',
    17: 'of Alacrity',
    18: 'of Swiftness',
    19: 'of Quickness',
    20: 'of Blocking',
    21: 'of Deflecting',
    22: 'of the Apprentice',
    23: 'of the Magus',
    24: 'of Frost',
    25: 'of the Glacier',
    26: 'of Frost',
    27: 'of Warmth',
    28: 'of Flame',
    29: 'of Fire',
    30: 'of Burning',
    31: 'of Flame',
    32: 'of Shock',
    33: 'of Lightning',
    34: 'of Thunder',
    35: 'of Shock',
    36: 'of Craftsmanship',
    37: 'of Quality',
    38: 'of Maiming',
    39: 'of Slaying',
    40: 'of Gore',
    41: 'of Carnage',
    42: 'of Slaughter',
    43: 'of Maiming',
    44: 'of Worth',
    45: 'of Measure',
    46: 'of Excellence',
    47: 'of Performance',
    48: 'of Measure',
    49: 'of Blight',
    50: 'of Venom',
    51: 'of Pestilence',
    52: 'of Blight',
    53: 'of Dexterity',
    54: 'of Dexterity',
    55: 'of Skill',
    56: 'of Skill',
    57: 'of Accuracy',
    58: 'of Precision',
    59: 'of Precision',
    60: 'of Perfection',
    61: 'of Balance',
    62: 'of Stability',
    64: 'of Regeneration',
    65: 'of Regeneration',
    66: 'of Regeneration',
    67: 'of Regrowth',
    68: 'of Regrowth',
    69: 'of Vileness',
    71: 'of Greed',
    72: 'of Wealth',
    73: 'of Chance',
    74: 'of Fortune',
    75: 'of Energy',
    76: 'of Energy',
    77: 'of the Mind',
    78: 'of Brilliance',
    79: 'of Sorcery',
    80: 'of Wizardry',
    81: 'of the Bear',
    82: 'of Light',
    83: 'of Radiance',
    84: 'of the Sun',
    85: 'of Life',
    86: 'of the Jackal',
    87: 'of the Fox',
    88: 'of the Wolf',
    89: 'of the Wolf',
    90: 'of the Tiger',
    91: 'of the Mammoth',
    92: 'of the Mammoth',
    93: 'of the Colosuss',
    94: 'of the Leech',
    95: 'of the Locust',
    96: 'of the Bat',
    97: 'of the Vampire',
    98: 'of Defiance',
    99: 'of Amelioration',
    100: 'of Remedy',
    102: 'of Simplicity',
    103: 'of Ease',
    105: 'of Strength',
    106: 'of Might',
    107: 'of the Ox',
    108: 'of the Ox',
    109: 'of the Giant',
    110: 'of the Giant',
    111: 'of the Titan',
    112: 'of Pacing',
    113: 'of Haste',
    114: 'of Speed',
    116: 'of Health',
    117: 'of Protection',
    118: 'of Absorption',
    119: 'of Life',
    120: 'of Life Everlasting',
    121: 'of Protection',
    122: 'of Absorption',
    123: 'of Life',
    124: 'of Anima',
    125: 'of Warding',
    126: 'of the Sentinel',
    127: 'of Guarding',
    128: 'of Negation',
    129: 'of the Sentinel',
    130: 'of Guarding',
    131: 'of Negation',
    132: 'of Coolness',
    133: 'of Incombustibility',
    134: 'of Amianthus',
    135: 'of Fire Quenching',
    136: 'of Coolness',
    137: 'of Incombustibility',
    138: 'of Amianthus',
    139: 'of Fire Quenching',
    140: 'of Faith',
    141: 'of Resistance',
    142: 'of Insulation',
    143: 'of Grounding',
    144: 'of the Dynamo',
    145: 'of Resistance',
    146: 'of Insulation',
    147: 'of Grounding',
    148: 'of the Dynamo',
    149: 'of Stoicism',
    150: 'of Warming',
    151: 'of Thawing',
    152: 'of the Dunes',
    153: 'of the Sirocco',
    154: 'of Warming',
    155: 'of Thawing',
    156: 'of the Dunes',
    157: 'of the Sirocco',
    158: 'of Desire',
    159: 'of Piercing',
    160: 'of Bashing',
    161: 'of Puncturing',
    162: 'of Thorns',
    163: 'of Spikes',
    164: 'of Razors',
    165: 'of Swords',
    166: 'of Malice',
    167: 'of Readiness',
    168: 'of Alacrity',
    169: 'of Swiftness',
    170: 'of Quickness',
    171: 'of Alacrity',
    172: 'of Fervor',
    173: 'of Blocking',
    174: 'of Deflecting',
    175: 'of the Apprentice',
    176: 'of the Magus',
    177: 'of Frost',
    178: 'of the Icicle',
    179: 'of the Glacier',
    180: 'of Winter',
    181: 'of Frost',
    182: 'of Frigidity',
    183: 'of Warmth',
    184: 'of Flame',
    185: 'of Fire',
    186: 'of Burning',
    187: 'of Incineration',
    188: 'of Flame',
    189: 'of Passion',
    190: 'of Shock',
    191: 'of Lightning',
    192: 'of Thunder',
    193: 'of Storms',
    194: 'of Shock',
    195: 'of Ennui',
    196: 'of Craftsmanship',
    197: 'of Quality',
    198: 'of Maiming',
    199: 'of Slaying',
    200: 'of Gore',
    201: 'of Carnage',
    202: 'of Slaughter',
    203: 'of Butchery',
    204: 'of Evisceration',
    205: 'of Maiming',
    206: 'of Craftsmanship',
    207: 'of Craftsmanship',
    208: 'of Craftsmanship',
    209: 'of Quality',
    210: 'of Quality',
    211: 'of Maiming',
    212: 'of Maiming',
    213: 'of Craftsmanship',
    214: 'of Craftsmanship',
    215: 'of Quality',
    216: 'of Quality',
    217: 'of Maiming',
    218: 'of Craftsmanship',
    219: 'of Quality',
    220: 'of Maiming',
    221: 'of Ire',
    222: 'of Wrath',
    223: 'of Carnage',
    224: 'of Worth',
    225: 'of Measure',
    226: 'of Excellence',
    227: 'of Performance',
    228: 'of Transcendence',
    229: 'of Worth',
    230: 'of Measure',
    231: 'of Excellence',
    232: 'of Performance',
    233: 'of Joyfulness',
    234: 'of Bliss',
    235: 'of Blight',
    236: 'of Venom',
    237: 'of Pestilence',
    238: 'of Anthrax',
    239: 'of Blight',
    240: 'of Envy',
    241: 'of Dexterity',
    242: 'of Skill',
    243: 'of Accuracy',
    244: 'of Precision',
    245: 'of Perfection',
    246: 'of Nirvana',
    247: 'of Dexterity',
    248: 'of Skill',
    249: 'of Accuracy',
    250: 'of Precision',
    251: 'of Perfection',
    252: 'of Dexterity',
    253: 'of Skill',
    254: 'of Accuracy',
    255: 'of Precision',
    256: 'of Dexterity',
    257: 'of Dexterity',
    258: 'of Dexterity',
    259: 'of Dexterity',
    260: 'of Dexterity',
    261: 'of Dexterity',
    262: 'of Daring',
    263: 'of Balance',
    264: 'of Equilibrium',
    265: 'of Stability',
    266: 'of Balance',
    267: 'of Balance',
    268: 'of Balance',
    269: 'of Truth',
    270: 'of Regeneration',
    271: 'of Regeneration',
    272: 'of Regeneration',
    273: 'of Regrowth',
    274: 'of Regrowth',
    275: 'of Revivification',
    276: 'of Honor',
    277: 'of Vileness',
    278: 'of Greed',
    279: 'of Wealth',
    280: 'of Greed',
    281: 'of Greed',
    282: 'of Greed',
    283: 'of Greed',
    284: 'of Greed',
    285: 'of Greed',
    286: 'of Avarice',
    287: 'of Chance',
    288: 'of Fortune',
    289: 'of Fortune',
    290: 'of Luck',
    291: 'of Fortune',
    292: 'of Good Luck',
    293: 'of Prosperity',
    294: 'of Energy',
    295: 'of the Mind',
    296: 'of Brilliance',
    297: 'of Sorcery',
    298: 'of Wizardry',
    299: 'of Enlightenment',
    300: 'of Energy',
    301: 'of the Mind',
    302: 'of Brilliance',
    303: 'of Sorcery',
    304: 'of Wizardry',
    305: 'of Energy',
    306: 'of the Mind',
    307: 'of Brilliance',
    308: 'of Sorcery',
    309: 'of Knowledge',
    310: 'of the Bear',
    311: 'of Light',
    312: 'of Radiance',
    313: 'of the Sun',
    314: 'of the Jackal',
    315: 'of the Fox',
    316: 'of the Wolf',
    317: 'of the Tiger',
    318: 'of the Mammoth',
    319: 'of the Colosuss',
    320: 'of the Squid',
    321: 'of the Whale',
    322: 'of the Jackal',
    323: 'of the Fox',
    324: 'of the Wolf',
    325: 'of the Tiger',
    326: 'of the Mammoth',
    327: 'of the Colosuss',
    328: 'of the Jackal',
    329: 'of the Fox',
    330: 'of the Wolf',
    331: 'of the Tiger',
    332: 'of the Mammoth',
    333: 'of Life',
    334: 'of Life',
    335: 'of Life',
    336: 'of Substinence',
    337: 'of Substinence',
    338: 'of Substinence',
    339: 'of Vita',
    340: 'of Vita',
    341: 'of Vita',
    342: 'of Life',
    343: 'of Life',
    344: 'of Substinence',
    345: 'of Substinence',
    346: 'of Vita',
    347: 'of Vita',
    348: 'of Life',
    349: 'of Substinence',
    350: 'of Vita',
    351: 'of Spirit',
    352: 'of Hope',
    353: 'of the Leech',
    354: 'of the Locust',
    355: 'of the Lamprey',
    356: 'of the Leech',
    357: 'of the Locust',
    358: 'of the Lamprey',
    359: 'of the Leech',
    360: 'of the Bat',
    361: 'of the Wraith',
    362: 'of the Vampire',
    363: 'of the Bat',
    364: 'of the Wraith',
    365: 'of the Vampire',
    366: 'of the Bat',
    367: 'of Defiance',
    368: 'of Amelioration',
    369: 'of Remedy',
    370: 'of Simplicity',
    371: 'of Ease',
    372: 'of Freedom',
    373: 'of Strength',
    374: 'of Might',
    375: 'of the Ox',
    376: 'of the Giant',
    377: 'of the Titan',
    378: 'of Atlus',
    379: 'of Strength',
    380: 'of Might',
    381: 'of the Ox',
    382: 'of the Giant',
    383: 'of the Titan',
    384: 'of Strength',
    385: 'of Might',
    386: 'of the Ox',
    387: 'of the Giant',
    388: 'of Strength',
    389: 'of Strength',
    390: 'of Strength',
    391: 'of Strength',
    392: 'of Strength',
    393: 'of Strength',
    394: 'of Virility',
    395: 'of Pacing',
    396: 'of Haste',
    397: 'of Speed',
    398: 'of Traveling',
    399: 'of Acceleration',
    400: 'of Inertia',
    401: 'of Inertia',
    402: 'of Inertia',
    403: 'of Self-Repair',
    404: 'of Fast Repair',
    405: 'of Ages',
    406: 'of Replenishing',
    407: 'of Propogation',
    408: 'of the Kraken',
    409: 'of Memory',
    410: 'of the Elephant',
    411: 'of Power',
    412: 'of Grace',
    413: 'of Grace and Power',
    414: 'of the Yeti',
    415: 'of the Phoenix',
    416: 'of the Efreeti',
    417: 'of the Cobra',
    418: 'of the Elements',
    419: 'of Firebolts',
    420: 'of Firebolts',
    421: 'of Firebolts',
    422: 'of Charged Shield',
    423: 'of Charged Shield',
    424: 'of Charged Shield',
    425: 'of Icebolt',
    426: 'of Frozen Armor',
    427: 'of Static Field',
    428: 'of Telekinesis',
    429: 'of Frost Shield',
    430: 'of Ice Blast',
    431: 'of Blaze',
    432: 'of Fire Ball',
    433: 'of Nova',
    434: 'of Nova',
    435: 'of Nova Shield',
    436: 'of Nova Shield',
    437: 'of Nova Shield',
    438: 'of Lightning',
    439: 'of Lightning',
    440: 'of Shiver Armor',
    441: 'of Fire Wall',
    442: 'of Enchant',
    443: 'of Chain Lightning',
    444: 'of Chain Lightning',
    445: 'of Chain Lightning',
    446: 'of Teleport Shield',
    447: 'of Teleport Shield',
    448: 'of Teleport Shield',
    449: 'of Glacial Spike',
    450: 'of Meteor',
    451: 'of Thunder Storm',
    452: 'of Energy Shield',
    453: 'of Blizzard',
    454: 'of Chilling Armor',
    455: 'of Hydra Shield',
    456: 'of Frozen Orb',
    457: 'of Dawn',
    458: 'of Sunlight',
    459: 'of Magic Arrows',
    460: 'of Magic Arrows',
    461: 'of Fire Arrows',
    462: 'of Fire Arrows',
    463: 'of Inner Sight',
    464: 'of Inner Sight',
    465: 'of Jabbing',
    466: 'of Jabbing',
    467: 'of Cold Arrows',
    468: 'of Cold Arrows',
    469: 'of Multiple Shot',
    470: 'of Multiple Shot',
    471: 'of Power Strike',
    472: 'of Power Strike',
    473: 'of Poison Jab',
    474: 'of Poison Jab',
    475: 'of Exploding Arrows',
    476: 'of Exploding Arrows',
    477: 'of Slow Missiles',
    478: 'of Slow Missiles',
    479: 'of Impaling Strike',
    480: 'of Impaling Strike',
    481: 'of Lightning Javelin',
    482: 'of Lightning Javelin',
    483: 'of Ice Arrows',
    484: 'of Ice Arrows',
    485: 'of Guided Arrows',
    486: 'of Guided Arrows',
    487: 'of Charged Strike',
    488: 'of Charged Strike',
    489: 'of Plague Jab',
    490: 'of Plague Jab',
    491: 'of Immolating Arrows',
    492: 'of Immolating Arrows',
    493: 'of Fending',
    494: 'of Fending',
    495: 'of Freezing Arrows',
    496: 'of Freezing Arrows',
    497: 'of Lightning Strike',
    498: 'of Lightning Strike',
    499: 'of Lightning Fury',
    500: 'of Lightning Fury',
    501: 'of Fire Bolts',
    502: 'of Fire Bolts',
    503: 'of Charged Bolts',
    504: 'of Charged Bolts',
    505: 'of Ice Bolts',
    506: 'of Ice Bolts',
    507: 'of Frozen Armor',
    508: 'of Frozen Armor',
    509: 'of Static Field',
    510: 'of Static Field',
    511: 'of Telekinesis',
    512: 'of Telekinesis',
    513: 'of Frost Novas',
    514: 'of Frost Novas',
    515: 'of Ice Blasts',
    516: 'of Ice Blasts',
    517: 'of Blazing',
    518: 'of Blazing',
    519: 'of Fire Balls',
    520: 'of Fire Balls',
    521: 'of Novas',
    522: 'of Novas',
    523: 'of Lightning',
    524: 'of Lightning',
    525: 'of Shiver Armor',
    526: 'of Shiver Armor',
    527: 'of Fire Walls',
    528: 'of Fire Walls',
    529: 'of Enchantment',
    530: 'of Enchantment',
    531: 'of Chain Lightning',
    532: 'of Chain Lightning',
    533: 'of Teleportation',
    534: 'of Teleportation',
    535: 'of Glacial Spikes',
    536: 'of Glacial Spikes',
    537: 'of Meteors',
    538: 'of Meteors',
    539: 'of Thunder Storm',
    540: 'of Thunder Storm',
    541: 'of Energy Shield',
    542: 'of Energy Shield',
    543: 'of Blizzards',
    544: 'of Blizzards',
    545: 'of Chilling Armor',
    546: 'of Chilling Armor',
    547: 'of Hydras',
    548: 'of Hydras',
    549: 'of Frozen Orbs',
    550: 'of Frozen Orbs',
    551: 'of Amplify Damage',
    552: 'of Amplify Damage',
    553: 'of Teeth',
    554: 'of Teeth',
    555: 'of Bone Armor',
    556: 'of Bone Armor',
    557: 'of Raise Skeletons',
    558: 'of Raise Skeletons',
    559: 'of Dim Vision',
    560: 'of Dim Vision',
    561: 'of Weaken',
    562: 'of Weaken',
    563: 'of Poison Dagger',
    564: 'of Poison Dagger',
    565: 'of Corpse Explosions',
    566: 'of Corpse Explosions',
    567: 'of Clay Golem Summoning',
    568: 'of Clay Golem Summoning',
    569: 'of Iron Maiden',
    570: 'of Iron Maiden',
    571: 'of Terror',
    572: 'of Terror',
    573: 'of Bone Walls',
    574: 'of Bone Walls',
    575: 'of Raise Skeletal Mages',
    576: 'of Raise Skeletal Mages',
    577: 'of Confusion',
    578: 'of Confusion',
    579: 'of Life Tap',
    580: 'of Life Tap',
    581: 'of Poison Explosion',
    582: 'of Poison Explosion',
    583: 'of Bone Spears',
    584: 'of Bone Spears',
    585: 'of Blood Golem Summoning',
    586: 'of Blood Golem Summoning',
    587: 'of Attraction',
    588: 'of Attraction',
    589: 'of Decrepification',
    590: 'of Decrepification',
    591: 'of Bone Imprisonment',
    592: 'of Bone Imprisonment',
    593: 'of Iron Golem Creation',
    594: 'of Iron Golem Creation',
    595: 'of Lower Resistance',
    596: 'of Lower Resistance',
    597: 'of Poison Novas',
    598: 'of Poison Novas',
    599: 'of Bone Spirits',
    600: 'of Bone Spirits',
    601: 'of Fire Golem Summoning',
    602: 'of Fire Golem Summoning',
    603: 'of Revivification',
    604: 'of Revivification',
    605: 'of Sacrifice',
    606: 'of Sacrifice',
    607: 'of Holy Bolts',
    608: 'of Holy Bolts',
    609: 'of Zeal',
    610: 'of Zeal',
    611: 'of Vengeance',
    612: 'of Vengeance',
    613: 'of Blessed Hammers',
    614: 'of Blessed Hammers',
    615: 'of Conversion',
    616: 'of Conversion',
    617: 'of Fist of the Heavens',
    618: 'of Fist of the Heavens',
    619: 'of Bashing',
    620: 'of Bashing',
    621: 'of Howling',
    622: 'of Howling',
    623: 'of Potion Finding',
    624: 'of Potion Finding',
    625: 'of Taunting',
    626: 'of Taunting',
    627: 'of Shouting',
    628: 'of Shouting',
    629: 'of Stunning',
    630: 'of Stunning',
    631: 'of Item Finding',
    632: 'of Item Finding',
    633: 'of Concentration',
    634: 'of Concentration',
    635: 'of Battle Cry',
    636: 'of Battle Cry',
    637: 'of Battle Orders',
    638: 'of Battle Orders',
    639: 'of Grim Ward',
    640: 'of Grim Ward',
    641: 'of War Cry',
    642: 'of War Cry',
    643: 'of Battle Command',
    644: 'of Battle Command',
    645: 'of Firestorms',
    646: 'of Firestorms',
    647: 'of Molten Boulders',
    648: 'of Molten Boulders',
    649: 'of Eruption',
    650: 'of Eruption',
    651: 'of Cyclone Armor',
    652: 'of Cyclone Armor',
    653: 'of Twister',
    654: 'of Twister',
    655: 'of Volcano',
    656: 'of Volcano',
    657: 'of Tornado',
    658: 'of Tornado',
    659: 'of Armageddon',
    660: 'of Armageddon',
    661: 'of Hurricane',
    662: 'of Hurricane',
    663: 'of Damage Amplification',
    664: 'of the Icicle',
    665: 'of the Glacier',
    666: 'of Fire',
    667: 'of Burning',
    668: 'of Lightning',
    669: 'of Thunder',
    670: 'of Daring',
    671: 'of Daring',
    672: 'of Knowledge',
    673: 'of Knowledge',
    674: 'of Virility',
    675: 'of Virility',
    676: 'of Readiness',
    677: 'of Craftsmanship',
    678: 'of Quality',
    679: 'of Maiming',
    680: 'of Craftsmanship',
    681: 'of Quality',
    682: 'of Craftsmanship',
    683: 'of Blight',
    684: 'of Venom',
    685: 'of Pestilence',
    686: 'of Anthrax',
    687: 'of Blight',
    688: 'of Venom',
    689: 'of Pestilence',
    690: 'of Anthrax',
    691: 'of Blight',
    692: 'of Venom',
    693: 'of Pestilence',
    694: 'of Anthrax',
    695: 'of Frost',
    696: 'of the Icicle',
    697: 'of the Glacier',
    698: 'of Winter',
    699: 'of Frost',
    700: 'of the Icicle',
    701: 'of the Glacier',
    702: 'of Winter',
    703: 'of Frost',
    704: 'of the Icicle',
    705: 'of the Glacier',
    706: 'of Winter',
    707: 'of Flame',
    708: 'of Fire',
    709: 'of Burning',
    710: 'of Incineration',
    711: 'of Flame',
    712: 'of Fire',
    713: 'of Burning',
    714: 'of Incineration',
    715: 'of Flame',
    716: 'of Fire',
    717: 'of Burning',
    718: 'of Incineration',
    719: 'of Shock',
    720: 'of Lightning',
    721: 'of Thunder',
    722: 'of Storms',
    723: 'of Shock',
    724: 'of Lightning',
    725: 'of Thunder',
    726: 'of Storms',
    727: 'of Shock',
    728: 'of Lightning',
    729: 'of Thunder',
    730: 'of Storms',
    731: 'of Dexterity',
    732: 'of Dexterity',
    733: 'of Strength',
    734: 'of Strength',
    735: 'of Thorns',
    736: 'of Frost',
    737: 'of Flame',
    738: 'of Blight',
    739: 'of Shock',
    740: 'of Regeneration',
    741: 'of Energy',
    742: 'of Light',
    743: 'of the Leech',
    744: 'of the Locust',
    745: 'of the Lamprey',
    746: 'of the Bat',
    747: 'of the Wraith',
    748: 'of the Vampire',
    749: 'of Acidity',
    750: 'of Acidity',
    751: 'of Acidity',
    752: 'of Acidity',
    753: 'of Acidity',
    754: 'of Kindling',
    755: 'of Kindling',
    756: 'of Kindling',
    757: 'of Kindling',
    758: 'of Kindling',
    759: 'of Numbing',
    760: 'of Numbing',
    761: 'of Numbing',
    762: 'of Numbing',
    763: 'of Numbing',
    764: 'of Conductivity',
    765: 'of Conductivity',
    766: 'of Conductivity',
    767: 'of Conductivity',
    768: 'of Conductivity',
    769: 'of Thaumaturgy',
    770: 'of Thaumaturgy',
    771: 'of Thaumaturgy',
    772: 'of Thaumaturgy',
    773: 'of Thaumaturgy',
    774: 'of Force',
    775: 'of Force',
    776: 'of Force',
    777: 'of Force',
    778: 'of Force',
    779: 'of Miasma Bolt',
    780: 'of Miasma Bolt',
    781: 'of Lethargy',
    782: 'of Lethargy',
    783: 'of Rancor',
    784: 'of Rancor',
    785: 'of Apocalypse',
    786: 'of Apocalypse',
}

_RARE_PREFIXES: dict[int, str] = {
    1: 'Beast',
    2: 'Eagle',
    3: 'Raven',
    4: 'Viper',
    5: 'GhoulRI',
    6: 'Skull',
    7: 'Blood',
    8: 'Dread',
    9: 'Doom',
    10: 'Grim',
    11: 'Bone',
    12: 'Death',
    13: 'Shadow',
    14: 'Storm',
    15: 'Rune',
    16: 'PlagueRI',
    17: 'Stone',
    18: 'Wraithra',
    19: 'Spirit',
    20: 'Storm',
    21: 'Demon',
    22: 'Cruel',
    23: 'Empyrion',
    24: 'Bramble',
    25: 'Pain',
    26: 'Loath',
    27: 'Glyph',
    28: 'Imp',
    29: 'Fiendra',
    30: 'Hailstone',
    31: 'Gale',
    32: 'Dire',
    33: 'Soul',
    34: 'Brimstone',
    35: 'Corpse',
    36: 'Carrion',
    37: 'Holocaust',
    38: 'Havoc',
    39: 'Bitter',
    40: 'Entropy',
    41: 'Chaos',
    42: 'Order',
    43: 'Rule',
    44: 'Warp',
    45: 'Rift',
    46: 'Corruption',
}

_RARE_SUFFIXES: dict[int, str] = {
    1: 'bite',
    2: 'scratch',
    3: 'scalpel',
    4: 'fang',
    5: 'gutter',
    6: 'thirst',
    7: 'razor',
    8: 'scythe',
    9: 'edge',
    10: 'saw',
    11: 'splitter',
    12: 'cleaver',
    13: 'sever',
    14: 'sunder',
    15: 'rend',
    16: 'mangler',
    17: 'slayer',
    18: 'reaver',
    19: 'spawn',
    20: 'gnash',
    21: 'star',
    22: 'blow',
    23: 'smasher',
    24: 'Bane',
    25: 'crusher',
    26: 'breaker',
    27: 'grinder',
    28: 'crack',
    29: 'mallet',
    30: 'knell',
    31: 'lance',
    32: 'spike',
    33: 'impaler',
    34: 'skewer',
    35: 'prod',
    36: 'scourge',
    37: 'wand',
    38: 'wrack',
    39: 'barb',
    40: 'needle',
    41: 'dart',
    42: 'bolt',
    43: 'quarrel',
    44: 'fletch',
    45: 'flight',
    46: 'nock',
    47: 'horn',
    48: 'stinger',
    49: 'quill',
    50: 'goad',
    51: 'branch',
    52: 'spire',
    53: 'song',
    54: 'call',
    55: 'cry',
    56: 'spell',
    57: 'chant',
    58: 'weaver',
    59: 'gnarl',
    60: 'visage',
    61: 'crest',
    62: 'circlet',
    63: 'veil',
    64: 'hood',
    65: 'mask',
    66: 'brow',
    67: 'casque',
    68: 'visor',
    69: 'cowl',
    70: 'hide',
    71: 'Pelt',
    72: 'carapace',
    73: 'coat',
    74: 'wrap',
    75: 'suit',
    76: 'cloak',
    77: 'shroud',
    78: 'jack',
    79: 'mantle',
    80: 'guard',
    81: 'badge',
    82: 'rock',
    83: 'aegis',
    84: 'ward',
    85: 'tower',
    86: 'shield',
    87: 'wing',
    88: 'mark',
    89: 'emblem',
    90: 'hand',
    91: 'fist',
    92: 'claw',
    93: 'clutches',
    94: 'grip',
    95: 'grasp',
    96: 'hold',
    97: 'touch',
    98: 'finger',
    99: 'knuckle',
    100: 'shank',
    101: 'spur',
    102: 'tread',
    103: 'stalker',
    104: 'greave',
    105: 'blazer',
    106: 'nails',
    107: 'trample',
    108: 'Brogues',
    109: 'track',
    110: 'slippers',
    111: 'clasp',
    112: 'buckle',
    113: 'harness',
    114: 'lock',
    115: 'fringe',
    116: 'winding',
    117: 'chain',
    118: 'strap',
    119: 'lash',
    120: 'cord',
    121: 'knot',
    122: 'circle',
    123: 'loop',
    124: 'eye',
    125: 'turn',
    126: 'spiral',
    127: 'coil',
    128: 'gyre',
    129: 'band',
    130: 'whorl',
    131: 'talisman',
    132: 'heart',
    133: 'noose',
    134: 'necklace',
    135: 'collar',
    136: 'beads',
    137: 'torc',
    138: 'gorget',
    139: 'scarab',
    140: 'wood',
    141: 'brand',
    142: 'bludgeon',
    143: 'cudgel',
    144: 'loom',
    145: 'harp',
    146: 'master',
    147: 'barRI',
    148: 'hew',
    149: 'crook',
    150: 'mar',
    151: 'shell',
    152: 'stake',
    153: 'picket',
    154: 'pale',
    155: 'flange',
}



# ─── Modern format helpers ────────────────────────────────────────────────────


def _full_property_list_valid(
    raw: bytes | bytearray,
    bit_start: int,
    max_bit: int,
    min_stats: int = 0,
) -> bool:
    """
    Strict validator: return True only if the property list starting at bit_start
    is fully parseable (all stat_ids known) AND terminates with the 0x1FF sentinel
    within max_bit. Used for non-unique/set quality detection where we lack uid/sid
    bounds for disambiguation.

    min_stats: require at least this many known stats before accepting the sentinel.
    Pass min_stats=1 in Phase 2 to reject empty property lists (normal-item false positives).
    """
    reader = BitReader(raw, bit_start)
    stat_count = 0
    for _ in range(64):
        if reader.tell() + 9 > max_bit:
            return False
        sid = reader.read(9)
        if sid == 0x1FF:
            return stat_count >= min_stats
        if sid not in _STAT_TABLE:
            return False
        save_bits, _, save_param = _STAT_TABLE[sid]
        needed = save_param + save_bits
        if reader.tell() + needed > max_bit:
            return False
        if save_param:
            reader.read(save_param)
        reader.read(save_bits)
        stat_count += 1
    return False


def _phase1_property_list_valid(
    raw: bytes | bytearray,
    bit_start: int,
    max_bit: int,
    min_valid: int = 3,
) -> bool:
    """
    Phase 1 validator for set/unique detection.

    Returns True if:
      - The property list terminates with the 0x1FF sentinel (fully clean parse), OR
      - At least `min_valid` known stats were parsed before hitting an unknown stat_id.

    Callers use two tiers:
      Tier 1 (min_valid=3): strict pass — very low false positive risk.
      Tier 2 (min_valid=1): lenient fallback for items with D2R stats early in
        their property list; only used when Tier 1 finds no candidates.
    """
    reader = BitReader(raw, bit_start)
    valid_count = 0
    for _ in range(64):
        if reader.tell() + 9 > max_bit:
            break
        sid = reader.read(9)
        if sid == 0x1FF:
            return True
        if sid in _PROPERTY_BLOCKLIST:
            return False  # character stat — definitely a false-positive position
        if sid not in _STAT_TABLE:
            return valid_count >= min_valid
        save_bits, _, save_param = _STAT_TABLE[sid]
        if reader.tell() + save_param + save_bits > max_bit:
            break
        if save_param:
            reader.read(save_param)
        reader.read(save_bits)
        valid_count += 1
    return False


def _skip_quality_data(reader: BitReader, quality: int, class_specific: bool = False) -> dict:
    """
    Read quality-specific bits that follow the mult_pics/class_specific flags
    in a Modern format item. Modifies reader position in-place.

    Returns a dict with extracted IDs for magic/rare items:
      magic items (q=3): {"magic_prefix_id": int, "magic_suffix_id": int}
        prefix_id=0 → no prefix, suffix_id=0 → no suffix
      rare/crafted (q=4/6): {"rare_name1": int, "rare_name2": int}
      all others: {}

    Bit counts by quality (D2 stash format):
      0 = normal:   0 bits
      1 = inferior: 3 bits (quality_prefix index)
      2 = superior: 0 bits
      3 = magic:    prefix(11) + has_suffix(1) + suffix(11) — both always consumed for
                    non-class items; class-specific items conditionally skip suffix.
      4 = rare:     8+8 bits (rare name IDs) + 6 affix slots (1-bit has_affix + 11-bit id each)
      6 = crafted:  same as rare
      8 = tempered: same as rare (D2R tempered items)
    """
    if quality == 1:
        reader.read(3)
        return {}
    elif quality == 3:
        prefix_id = reader.read(11)
        has_suffix = reader.read(1)
        if has_suffix:
            suffix_id = reader.read(11)
        elif not class_specific:
            # Non-class: always consume the full 23 bits even when has_suffix=0.
            reader.read(11)
            suffix_id = 0
        else:
            suffix_id = 0
        return {"magic_prefix_id": prefix_id, "magic_suffix_id": suffix_id}
    elif quality in (4, 6):
        name1 = reader.read(8)    # rare name ID 1
        name2 = reader.read(8)    # rare name ID 2
        for _ in range(6):        # 3 prefix + 3 suffix slots (each: 1-bit has_affix + 11-bit id)
            if reader.read(1):
                reader.read(11)
        return {"rare_name1": name1, "rare_name2": name2}
    elif quality == 8:
        reader.read(8)    # tempered modifier 1
        reader.read(8)    # tempered modifier 2
    # quality 0 (normal) and 2 (superior): no quality data bits
    return {}


def _is_modern_format(data: bytes) -> bool:
    """Return True if data is a Modern stash (version field == 2)."""
    if len(data) < 8:
        return False
    version = struct.unpack_from("<I", data, 4)[0]
    return version == 2


def _find_modern_page_jm_offsets(data: bytes) -> list[int]:
    """
    Locate all page JM markers in a Modern stash file using forward navigation.

    Page 0 starts immediately after the 64-byte header. Each subsequent page is found
    by reading the size_field from the 64-byte separator that precedes it: that field
    encodes the slot size of the page it introduces (JM+count+items+next_separator).
    Navigation stops when no JM is found at the expected position or data is exhausted.
    """
    if len(data) < MODERN_HEADER_SIZE + 4:
        return []

    page0_size = struct.unpack_from("<I", data, 16)[0]
    offsets: list[int] = [MODERN_HEADER_SIZE]  # page 0 always starts right after header

    cur = MODERN_HEADER_SIZE + page0_size  # position of page 1's JM
    while cur + 1 < len(data):
        if data[cur : cur + 2] != b"JM":
            break
        offsets.append(cur)
        sep_start = cur - MODERN_SEP_SIZE
        if sep_start < 0:
            break
        slot_size = struct.unpack_from("<I", data, sep_start + 16)[0]
        if slot_size == 0:
            break
        cur += slot_size

    return offsets


def _find_item_starts_modern(raw: bytes | bytearray, item_count: int) -> list[int]:
    """
    Find item start byte positions in Modern format page data.
    Stash items reliably start with first_byte=0x10 (identified flag at bit 4)
    and fourth_byte=0x00. Returns up to item_count positions.
    """
    starts: list[int] = []
    i = 0
    while i + 3 < len(raw) and len(starts) < item_count:
        if raw[i] == 0x10 and raw[i + 3] == 0x00:
            starts.append(i)
            i += 4  # skip past matched bytes to avoid overlapping hits
        else:
            i += 1
    return starts


def _decode_huffman_item_code(raw: bytes | bytearray, item_byte_start: int) -> str:
    """
    Decode the 4-character Huffman item type code from a Modern D2R stash item.

    The encoding starts at bit 53 (LSB-first) from item_byte_start.
    Returns the 4-char string (e.g. 'cm1 ', 'rin ', 'r03 ') or '' on failure.
    Empirically confirmed for cm1, cm2, cm3, rin, r03, fhl (Full Helm).
    """
    reader = BitReader(raw, item_byte_start * 8 + _MOD_HUFFMAN_CODE_START)
    max_bit = len(raw) * 8
    code: list[str] = []
    for _ in range(4):
        saved = reader.tell()
        found = False
        for length in range(2, 10):
            if saved + length > max_bit:
                break
            reader.seek(saved)
            v = reader.read(length)
            ch = _HUFFMAN_REVERSE.get((v, length))
            if ch is not None:
                code.append(ch)
                found = True
                break
        if not found:
            return ""
    return "".join(code)


def _parse_single_item_modern(
    raw: bytes | bytearray,
    byte_start: int,
    byte_end: int,
) -> D2IItem:
    """
    Extract quality and stats from a Modern format item.

    D2R uses a variable-length item type encoding so the quality field is not at a
    fixed bit offset.  We scan _MOD_QUALITY_SCAN_START..._MOD_QUALITY_SCAN_END in
    two phases:

    Phase 1 — set/unique (quality 5/7):
      Tight validation using uid/sid catalog bounds + _is_valid_property_list.

    Phase 2 — all other qualities (normal/inferior/superior/magic/rare/crafted/tempered):
      Requires the full property list to parse cleanly AND end with the 0x1FF sentinel
      (_full_property_list_valid). This stricter check compensates for the lack of
      uid/sid bounds.

    Flag bits (relative to item byte_start, LSB-first, no JM prefix):
      bit 4  = identified  (always 1 for stash items — confirmed by 0x10 first byte)
      bit 12 = is_ear
      bit 13 = newbie
      bit 19 = is_simple
      bit 20 = is_ethereal
    These mirror the legacy D2 bit layout minus the 16-bit JM prefix offset.
    """
    base = byte_start * 8

    # Flag bits — read directly from the raw bytes (faster than BitReader for fixed offsets)
    byte2 = raw[byte_start + 2] if byte_start + 2 < len(raw) else 0
    is_simple   = bool((byte2 >> 3) & 1)  # bit 19 from item start = bit 3 of byte 2
    is_ethereal = bool((byte2 >> 4) & 1)  # bit 20 from item start = bit 4 of byte 2
    is_ear      = bool((raw[byte_start + 1] >> 4) & 1) if byte_start + 1 < len(raw) else False  # bit 12

    quality    = 0
    unique_id: int | None = None
    set_id:    int | None = None
    item_level = 0
    properties: list[str] = []
    p1_unique_id: int | None = None  # preserved across conflict resolution
    p1_set_id:    int | None = None

    if not is_simple and not is_ear:
        reader = BitReader(raw, base)
        max_bit = byte_end * 8

        # ── Phase 1: set (q=5) and unique (q=7) ──────────────────────────────
        # Two-tier scan using uid/sid catalog bounds for disambiguation.
        #
        # Tier 1 (min_valid=3): strict — requires 3 known stats OR sentinel before
        #   any unknown stat.  Very low false positive rate.
        # Tier 2 (min_valid=1): lenient fallback — only runs if Tier 1 finds nothing.
        #   Catches real set/unique items whose property lists begin with D2R-specific
        #   stats that aren't yet in _STAT_TABLE, at the cost of slightly higher (but
        #   still low) false positive risk from the tight ilvl + uid/sid filters.
        #
        # We track Phase 1 results separately so Phase 2 can override a weak hit.
        # "Weak" = _phase1_property_list_valid passed but _full_property_list_valid
        # did not (property list has unknown stats).  A Phase 2 full-validated result
        # beats a Phase 1 weak result — this prevents magic/rare items from being
        # mis-identified as set/unique when the scan lands on a false-positive position.
        p1_quality:    int       = 0
        p1_ilvl:       int       = 0
        p1_unique_id:  int | None = None
        p1_set_id:     int | None = None
        p1_props_start: int      = -1
        p1_full:       bool      = False  # did Phase 1 candidate also pass full validation?

        for min_valid in (3, 1):
            for q_bit in range(_MOD_QUALITY_SCAN_START, _MOD_QUALITY_SCAN_END):
                reader.seek(base + q_bit)
                q = reader.read(4)
                if q not in (5, 7):
                    continue

                # Validate ilvl (7 bits immediately before quality)
                ilvl = BitReader(raw, base + q_bit - 7).read(7)
                if not (1 <= ilvl <= 99):
                    continue

                # Skip mult_pics flag (+ 11-bit picture_id if set) and class_specific flag.
                # D2R Modern expanded the Classic D2 3-bit picture_id to 11 bits.
                mult_pics = reader.read(1)
                if mult_pics:
                    reader.read(11)
                class_specific = reader.read(1)
                if class_specific:
                    reader.read(11)

                qdata = reader.read(12)

                if q == 7 and qdata > _MOD_MAX_UNIQUE_ID:
                    continue
                if q == 5 and qdata > _MOD_MAX_SET_ID:
                    continue

                props_pos = reader.tell()
                if not _phase1_property_list_valid(raw, props_pos, max_bit, min_valid):
                    continue

                # Record candidate — also check full validation for conflict resolution
                p1_quality    = q
                p1_ilvl       = ilvl
                p1_props_start = props_pos
                p1_full       = _full_property_list_valid(raw, props_pos, max_bit)
                if q == 7:
                    p1_unique_id = qdata
                else:
                    p1_set_id = qdata
                break  # stop inner q_bit loop

            if p1_quality != 0:
                break  # found in this tier — don't try the next tier

        # ── Phase 2: all other qualities (normal/inferior/superior/magic/rare/crafted/tempered) ──
        # Two-tier validation:
        #   Full  (_full_property_list_valid): all stat IDs known + list ends with sentinel. Best.
        #   Lite  (_is_valid_property_list):   2 consecutive known stat IDs. Fallback.
        # q=0 (normal, e.g. runes) is included but deprioritised — 0000 is common in bitstreams.
        #
        # Phase 2 ALWAYS runs, even when Phase 1 found a fully-validated result.
        # Rationale: Phase 1 can produce fully-validated false positives when its quality-data
        # parsing happens to consume the same number of bits as the real structure, landing at the
        # actual property list coincidentally.  Phase 2 reads the quality-specific data correctly
        # (magic prefix/suffix, rare name IDs, etc.) so a Phase 2 full+non-normal result is more
        # trustworthy than a Phase 1 fully-validated result.
        best_props_start: int = -1   # -1 = nothing found yet
        best_q:    int = 0
        best_ilvl: int = 0
        best_full: bool = False      # True = passed _full_property_list_valid
        best_magic_prefix_id: int = 0  # magic prefix ID when best_q=3
        best_magic_suffix_id: int = 0  # magic suffix ID when best_q=3
        best_rare_name1: int = 0       # rare name word 1 when best_q=4/6
        best_rare_name2: int = 0       # rare name word 2 when best_q=4/6

        # Bit 82 from item start: 0 = normal item, 1 = non-normal (magic/rare/crafted/etc.).
        # Empirically confirmed across all test items.  Used to gate non-zero quality
        # candidates in Phase 2 and prevent false positives on normal items.
        _b82 = bool((raw[byte_start + 10] >> 2) & 1) if byte_start + 10 < len(raw) else True

        for q_bit in range(_MOD_QUALITY_SCAN_START, _MOD_QUALITY_SCAN_END_WIDE):
            reader.seek(base + q_bit)
            q = reader.read(4)
            if q not in (0, 1, 2, 3, 4, 6, 8):
                continue

            # Skip non-zero quality candidates when bit 82 marks this as a normal item.
            if q != 0 and not _b82:
                continue

            # Validate ilvl (7 bits immediately before quality).
            # Magic items (q=3) allow ilvl up to 127; other qualities enforce the tighter 1-99
            # range that was empirically validated.  The extended range is needed because some
            # magic charms store ilvl values above 99 at their true quality bit offset.
            ilvl = BitReader(raw, base + q_bit - 7).read(7)
            max_ilvl = 127 if q == 3 else 99
            if not (1 <= ilvl <= max_ilvl):
                continue

            # Skip mult_pics flag (+ 11-bit picture_id if set) and class_specific flag.
            # D2R Modern expanded the Classic D2 3-bit picture_id to 11 bits.
            mult_pics = reader.read(1)
            if mult_pics:
                reader.read(11)
            class_specific = reader.read(1)
            if class_specific:
                reader.read(11)

            # Read quality-specific data (magic prefix/suffix, rare names/affixes, etc.)
            qd = _skip_quality_data(reader, q, class_specific=bool(class_specific))

            props_start = reader.tell()
            if props_start >= max_bit:
                continue

            # Require at least 1 stat for full validation — an empty property list
            # (just the sentinel) is almost certainly a false positive for a non-normal item.
            is_full = _full_property_list_valid(raw, props_start, max_bit, min_stats=1)
            if not is_full and not _is_valid_property_list(raw, props_start, max_bit):
                continue

            # Determine if this candidate beats the current best:
            #   1. Nothing found yet → always take it.
            #   2. Upgrade from lite to full validation → take it.
            #   3. Same validation tier, prefer higher quality value.
            #      (q=1/2 are weakly distinctive and often false-positives; q=3+ are more reliable)
            if (best_props_start < 0
                    or (is_full and not best_full)
                    or (is_full == best_full and q > best_q)):
                best_props_start = props_start
                best_q    = q
                best_ilvl = ilvl
                best_full = is_full
                best_magic_prefix_id = qd.get("magic_prefix_id", 0)
                best_magic_suffix_id = qd.get("magic_suffix_id", 0)
                best_rare_name1 = qd.get("rare_name1", 0)
                best_rare_name2 = qd.get("rare_name2", 0)
                if is_full and q >= 3:
                    break  # Full validation + magic/rare/set/unique/crafted/tempered: can't do better

        # ── Conflict resolution ────────────────────────────────────────────────
        # Priority:
        #   1. Phase 2 full + non-normal quality → wins over everything.
        #      Phase 2 reads quality-specific data correctly so a full result is authoritative.
        #   2. Phase 1 full → wins when Phase 2 found nothing full+non-normal.
        #   3. Phase 2 lite → wins over Phase 1 weak (not fully validated).
        #   4. Phase 1 weak → fallback when Phase 2 also found nothing useful.
        if best_props_start >= 0 and best_full and best_q != 0:
            # Phase 2 full + non-normal beats Phase 1 regardless of p1_full
            quality    = best_q
            item_level = best_ilvl
            unique_id  = None
            set_id     = None
            properties = _format_properties(
                _parse_property_list(raw, best_props_start, max_bit)
            )
        elif p1_quality != 0 and p1_full:
            # Phase 1 fully validated, Phase 2 didn't find a better result
            quality    = p1_quality
            item_level = p1_ilvl
            unique_id  = p1_unique_id
            set_id     = p1_set_id
            properties = _format_properties(
                _parse_property_list(raw, p1_props_start, max_bit)
            )
        elif best_props_start >= 0:
            # Phase 2 lite result
            p2_beats_p1 = (p1_quality == 0) or not p1_full
            if p2_beats_p1:
                quality    = best_q
                item_level = best_ilvl
                unique_id  = None
                set_id     = None
                properties = _format_properties(
                    _parse_property_list(raw, best_props_start, max_bit)
                )
            elif p1_quality != 0:
                # Phase 1 weak wins over Phase 2 lite
                quality    = p1_quality
                item_level = p1_ilvl
                unique_id  = p1_unique_id
                set_id     = p1_set_id
                properties = _format_properties(
                    _parse_property_list(raw, p1_props_start, max_bit)
                )
        elif p1_quality != 0:
            # Phase 2 found nothing — fall back to Phase 1
            quality    = p1_quality
            item_level = p1_ilvl
            unique_id  = p1_unique_id
            set_id     = p1_set_id
            properties = _format_properties(
                _parse_property_list(raw, p1_props_start, max_bit)
            )

    # ── Build magic/rare display names ────────────────────────────────────────
    # Only applicable when Phase 2 won (Phase 1 only finds q=5/7, never magic/rare).
    magic_prefix: str | None = None
    magic_suffix: str | None = None
    rare_name: str | None = None

    if quality == 3:
        magic_prefix = _MAGIC_PREFIXES.get(best_magic_prefix_id) if best_magic_prefix_id else None
        magic_suffix = _MAGIC_SUFFIXES.get(best_magic_suffix_id) if best_magic_suffix_id else None
    elif quality in (4, 6):
        p = _RARE_PREFIXES.get(best_rare_name1, "")
        s = _RARE_SUFFIXES.get(best_rare_name2, "")
        p_clean = p.rstrip("RI") if p else ""   # strip internal D2R 'RI' suffix artifact
        s_cap   = s.title() if s else ""
        combined = f"{p_clean} {s_cap}".strip()
        if combined:
            rare_name = combined

    return D2IItem(
        byte_start=byte_start,
        byte_end=byte_end,
        item_type=_decode_huffman_item_code(raw, byte_start),
        quality=quality,
        unique_id=unique_id,
        set_id=set_id,
        item_level=item_level,
        is_ethereal=is_ethereal,
        socket_count=0,
        is_simple=is_simple,
        is_ear=is_ear,
        properties=properties,
        p1_unique_id=p1_unique_id,
        p1_set_id=p1_set_id,
        magic_prefix=magic_prefix,
        magic_suffix=magic_suffix,
        rare_name=rare_name,
    )


def _parse_page_items_modern(raw: bytearray, item_count: int) -> list[D2IItem]:
    """Parse all items from a Modern format page's raw data."""
    if item_count == 0:
        return []

    starts = _find_item_starts_modern(raw, item_count)
    items: list[D2IItem] = []

    for i, byte_start in enumerate(starts):
        byte_end = starts[i + 1] if i + 1 < len(starts) else len(raw)
        try:
            item = _parse_single_item_modern(raw, byte_start, byte_end)
            items.append(item)
        except Exception:
            pass  # skip malformed items; grail hook is non-fatal anyway

    return items


# ─── Legacy item parsing ───────────────────────────────────────────────────────

def _parse_single_item(raw: bytes | bytearray, byte_start: int) -> tuple[D2IItem | None, int]:
    """
    Parse one legacy item starting at byte_start (the 'J' of 'JM').
    Returns (item, next_byte_start) or (None, byte_start+2) on error.
    """
    if byte_start + 2 > len(raw):
        return None, byte_start + 2

    if raw[byte_start] != 0x4A or raw[byte_start + 1] != 0x4D:
        return None, byte_start + 2

    reader = BitReader(raw, byte_start * 8)

    reader.read(16)  # JM marker

    reader.read(4)
    _identified = reader.read(1)
    reader.read(1)
    reader.read(6)
    is_ear = bool(reader.read(1))
    _newbie = reader.read(1)
    reader.read(5)
    is_simple = bool(reader.read(1))
    is_ethereal = bool(reader.read(1))
    reader.read(1)
    _personalized = reader.read(1)
    reader.read(1)
    _runeword = bool(reader.read(1))
    reader.read(1)
    reader.read(54)  # location/position/grid

    type_bytes = bytearray(4)
    for i in range(4):
        type_bytes[i] = reader.read(8)
    item_type = type_bytes.decode("ascii", errors="replace").rstrip("\x00")

    socket_count = reader.read(3)

    quality = 0
    unique_id = None
    set_id = None
    item_level = 0

    if not is_simple and not is_ear:
        _nid = reader.read(32)
        item_level = reader.read(7)
        quality = reader.read(4)

        _multiple_pictures = reader.read(1)
        if _multiple_pictures:
            reader.read(3)

        _class_specific = reader.read(1)
        if _class_specific:
            reader.read(11)

        if quality == 1:
            reader.read(3)
        elif quality == 2:
            pass
        elif quality == 3:
            reader.read(3)
        elif quality == 4:
            reader.read(11)
            reader.read(11)
        elif quality == 5:
            set_id = reader.read(12)
        elif quality == 6:
            reader.read(8)
            reader.read(8)
        elif quality == 7:
            unique_id = reader.read(12)
        elif quality == 8:
            reader.read(8)
            reader.read(8)

    item_byte_end = (reader.tell() + 7) // 8

    item = D2IItem(
        byte_start=byte_start,
        byte_end=item_byte_end,
        item_type=item_type,
        quality=quality,
        unique_id=unique_id,
        set_id=set_id,
        item_level=item_level,
        is_ethereal=is_ethereal,
        socket_count=socket_count,
        is_simple=is_simple,
        is_ear=is_ear,
    )
    return item, item_byte_end


def _parse_page_items(raw: bytearray, item_count: int) -> list[D2IItem]:
    """
    Parse items from a legacy page's raw bytes by scanning for JM markers.
    Consumes socket_count sub-item JM blocks after each top-level item.
    """
    items: list[D2IItem] = []

    if item_count == 0:
        return items

    jm_positions: list[int] = []
    pos = 0
    while pos < len(raw) - 1:
        if raw[pos] == 0x4A and raw[pos + 1] == 0x4D:
            jm_positions.append(pos)
            pos += 2
        else:
            pos += 1

    if not jm_positions:
        return items

    jm_idx = 0
    while jm_idx < len(jm_positions) and len(items) < item_count:
        byte_start = jm_positions[jm_idx]
        item, _ = _parse_single_item(raw, byte_start)
        jm_idx += 1

        if item is None:
            continue

        subs_consumed = 0
        while subs_consumed < item.socket_count and jm_idx < len(jm_positions):
            jm_idx += 1
            subs_consumed += 1

        if jm_idx < len(jm_positions):
            item.byte_end = jm_positions[jm_idx]
        else:
            item.byte_end = len(raw)

        items.append(item)

    return items


# ─── Page serialization helpers ───────────────────────────────────────────────

def remove_items_from_page(page: D2IPage, indices: list[int]) -> D2IPage:
    """Return a new D2IPage with items at `indices` removed."""
    if not indices:
        return page

    idx_set = set(indices)
    new_raw = bytearray()
    for i, item in enumerate(page.items):
        if i not in idx_set:
            new_raw.extend(page.raw_bytes[item.byte_start:item.byte_end])

    new_count = max(0, page.item_count - len(idx_set))

    if page.is_modern:
        # Modern format: empty pages use raw_bytes=bytearray() (truly zero bytes).
        # The serializer will compute the correct size_field in the preceding separator.
        new_page = D2IPage(
            flags=0,
            name="",
            raw_bytes=new_raw,
            item_count=new_count,
            items=[],
            is_modern=True,
            preceding_separator=page.preceding_separator,
        )
        if new_count > 0:
            new_page.items = _parse_page_items_modern(new_raw, new_count)
    else:
        new_page = D2IPage(
            flags=page.flags,
            name=page.name,
            raw_bytes=new_raw,
            item_count=new_count,
            items=[],
            is_modern=False,
        )
        new_page.items = _parse_page_items(new_raw, new_count)

    return new_page


def insert_item_into_page(page: D2IPage, item_bytes: bytes) -> D2IPage:
    """Append item bytes to end of page, increment item_count."""
    new_raw = bytearray(page.raw_bytes) + bytearray(item_bytes)
    new_count = page.item_count + 1

    new_page = D2IPage(
        flags=page.flags,
        name=page.name,
        raw_bytes=new_raw,
        item_count=new_count,
        items=[],
        is_modern=page.is_modern,
        preceding_separator=page.preceding_separator,
    )
    if page.is_modern:
        new_page.items = _parse_page_items_modern(new_raw, new_count)
    else:
        new_page.items = _parse_page_items(new_raw, new_count)
    return new_page


# ─── File I/O ─────────────────────────────────────────────────────────────────

def parse_d2i(path: Path) -> D2IStash:
    """Parse a .d2i stash file (legacy or Modern format)."""
    data = path.read_bytes()
    if len(data) < 12:
        raise ValueError(f"File too short: {len(data)} bytes")

    magic, version = struct.unpack_from("<II", data, 0)

    if _is_modern_format(data):
        return _parse_d2i_modern(data, magic, version)
    else:
        return _parse_d2i_legacy(data, magic, version)


def _parse_d2i_legacy(data: bytes, magic: int, version: int) -> D2IStash:
    """Parse legacy format stash."""
    num_pages = struct.unpack_from("<I", data, 8)[0]
    offset = 12

    stash = D2IStash(magic=magic, version=version, num_pages=num_pages)

    for page_idx in range(num_pages):
        if offset + 10 > len(data):
            raise ValueError(f"Truncated at page {page_idx}")

        flags = struct.unpack_from("<I", data, offset)[0]
        offset += 4

        name_len = struct.unpack_from("<H", data, offset)[0]
        offset += 2
        name = data[offset:offset + name_len].decode("utf-8", errors="replace")
        offset += name_len

        if data[offset:offset + 2] != b"JM":
            raise ValueError(
                f"Expected JM at page {page_idx}, offset {offset}, got {data[offset:offset+2]!r}"
            )
        offset += 2

        item_count = struct.unpack_from("<I", data, offset)[0]
        offset += 4

        raw_start = offset
        remaining = bytearray(data[raw_start:])
        items = _parse_page_items(remaining, item_count)

        if items:
            raw_end = items[-1].byte_end
        else:
            raw_end = 0

        raw_bytes = remaining[:raw_end]
        offset = raw_start + raw_end

        page = D2IPage(
            flags=flags,
            name=name,
            raw_bytes=bytearray(raw_bytes),
            item_count=item_count,
            items=items,
            is_modern=False,
        )
        stash.pages.append(page)

    return stash


def _parse_d2i_modern(data: bytes, magic: int, version: int) -> D2IStash:
    """Parse Modern format stash (version == 2)."""
    if len(data) < MODERN_HEADER_SIZE:
        raise ValueError(f"Modern stash too short: {len(data)} bytes")

    raw_header = bytes(data[:MODERN_HEADER_SIZE])
    gold = struct.unpack_from("<I", data, 12)[0]
    jm_offsets = _find_modern_page_jm_offsets(data)
    if not jm_offsets:
        raise ValueError("Modern stash: no pages found")

    num_pages = len(jm_offsets)
    stash = D2IStash(
        magic=magic,
        version=version,
        num_pages=num_pages,
        is_modern=True,
        raw_header=raw_header,
        gold=gold,
    )

    for page_idx, jm_off in enumerate(jm_offsets):
        if jm_off + 4 > len(data):
            raise ValueError(f"Truncated at Modern page {page_idx}")

        item_count = struct.unpack_from("<H", data, jm_off + 2)[0]
        data_start = jm_off + 4

        # data_end: exclude the 64-byte separator that precedes the next page (or EOF for last page)
        if page_idx + 1 < num_pages:
            data_end = jm_offsets[page_idx + 1] - MODERN_SEP_SIZE
        else:
            data_end = len(data)

        raw_bytes = bytearray(data[data_start:data_end])
        items = _parse_page_items_modern(raw_bytes, item_count)

        # Extract the 64-byte separator preceding this page's JM (absent for page 0)
        if page_idx == 0:
            preceding_sep = b""
        else:
            sep_start = jm_off - MODERN_SEP_SIZE
            preceding_sep = bytes(data[sep_start : jm_off])

        page = D2IPage(
            flags=0,
            name="",
            raw_bytes=raw_bytes,
            item_count=item_count,
            items=items,
            is_modern=True,
            preceding_separator=preceding_sep,
        )
        stash.pages.append(page)

    return stash


def serialize_d2i(stash: D2IStash) -> bytes:
    """Reconstruct .d2i bytes from a D2IStash."""
    if stash.is_modern:
        return _serialize_d2i_modern(stash)
    else:
        return _serialize_d2i_legacy(stash)


def _serialize_d2i_legacy(stash: D2IStash) -> bytes:
    out = bytearray()
    out += struct.pack("<III", stash.magic, stash.version, stash.num_pages)
    for page in stash.pages:
        out += struct.pack("<I", page.flags)
        name_bytes = page.name.encode("utf-8")
        out += struct.pack("<H", len(name_bytes))
        out += name_bytes
        out += b"JM"
        out += struct.pack("<I", page.item_count)
        out += page.raw_bytes
    return bytes(out)


def _serialize_d2i_modern(stash: D2IStash) -> bytes:
    """
    Reconstruct Modern format stash bytes.

    Layout:
      64-byte header
      Page 0: JM + item_count(2) + raw_bytes  (no preceding separator; header provides leading zeros)
      Page 1+: [64-byte separator] + JM + item_count(2) + raw_bytes

    Separator structure: magic(4)+version(4)+unk1(4)+gold=0(4)+size_field(4)+zeros(44)
      size_field = slot size of the page that follows = 4+len(raw_bytes)+64 for non-last pages.
      Exception: if the stored separator has field-at-offset-20 != 0 (terminal marker),
      it is preserved byte-for-byte (the last page's separator uses a different encoding).
    """
    out = bytearray(stash.raw_header)
    # Write current gold value (may differ from raw_header if gold was deposited/withdrawn)
    struct.pack_into("<I", out, 12, stash.gold)
    total_pages = len(stash.pages)

    for page_idx, page in enumerate(stash.pages):
        if page_idx > 0:
            sep = page.preceding_separator
            # Check for terminal marker (field at offset 20 of separator != 0 → last-page sentinel)
            terminal = len(sep) >= 24 and struct.unpack_from("<I", sep, 20)[0] != 0
            if terminal:
                # Preserve the terminal separator exactly; D2R uses it as a fixed sentinel
                out += sep
            else:
                # Reconstruct separator with a fresh size_field.
                # Slot size = JM(2) + count(2) + raw_bytes + trailing separator(64).
                # The trailing separator exists for every page that is NOT the last one.
                # Since this separator is non-terminal, the page it introduces also has a
                # trailing separator (the next page's preceding_separator), so +64 applies.
                slot_size = 4 + len(page.raw_bytes) + MODERN_SEP_SIZE
                out += struct.pack("<IIIII", 0xAA55AA55, 2, 105, 0, slot_size)
                out += b"\x00" * 44

        out += b"JM"
        out += struct.pack("<H", page.item_count)
        out += page.raw_bytes

    return bytes(out)


# ─── Validation ───────────────────────────────────────────────────────────────

def validate_page_items(page: D2IPage) -> bool:
    """
    Verify that item byte ranges are consistent with raw_bytes length.
    Returns True if valid, False if there's a mismatch.
    """
    if not page.items:
        return True

    for item in page.items:
        if item.byte_start < 0 or item.byte_end > len(page.raw_bytes):
            return False
        if item.byte_start >= item.byte_end:
            return False

    sorted_items = sorted(page.items, key=lambda i: i.byte_start)
    for i in range(len(sorted_items) - 1):
        if sorted_items[i].byte_end > sorted_items[i + 1].byte_start:
            return False

    return True
