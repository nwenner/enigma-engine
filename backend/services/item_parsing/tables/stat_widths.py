"""
Item stat bit-width table for property list skipping.

STAT_WIDTHS maps stat_id → total bits to consume per stat entry
  = save_param_bits + save_bits
Used by skip_properties() to advance past the property list to the 0x1FF sentinel.

Format of source data: stat_id → (save_bits, save_add, save_param_bits)
STAT_WIDTHS pre-computes save_param_bits + save_bits for each entry.
"""
from __future__ import annotations

# (save_bits, save_add, save_param_bits) for each stat_id.
# Preserved for any code that needs raw widths or save_add.
STAT_TABLE: dict[int, tuple[int, int, int]] = {
    0:   (8,  32, 0),   # strength
    1:   (7,  32, 0),   # energy
    2:   (7,  32, 0),   # dexterity
    3:   (7,  32, 0),   # vitality
    4:   (7,   0, 0),   # D2R stat 4 — confirmed save_bits=7 empirically from Goldwrap parsing
    5:   (8,   0, 0),   # D2R stat 5 — save_bits=8 best guess; appears on unique shields
    6:   (8,   0, 0),   # D2R stat 6 — save_bits=8 best guess; appears on unique swords/shields
    8:   (9,   0, 0),   # D2R stat 8 — empirically determined; appears in property lists
    10:  (1,   0, 0),   # D2R stat 10 — empirically determined; header stat on some charms
    12:  (9,   0, 0),   # D2R stat 12 — empirically determined; appears after stat 10/84
    14:  (9,   0, 0),   # D2R stat 14 — empirically determined; appears after stat 30 on gloves
    15:  (3,   0, 0),   # D2R stat 15 — confirmed save_bits=3 (only 3 bits remain after it in Grand Charm buffer)
    7:   (9,  32, 0),   # maxhp
    9:   (8,  32, 0),   # maxmana
    11:  (8,  32, 0),   # maxstamina
    16:  (9,   0, 0),   # item_armor_percent
    17:  (9,   0, 0),   # item_maxdamage_percent
    18:  (9,   0, 0),   # item_mindamage_percent
    19:  (10,  0, 0),   # tohit
    20:  (6,   0, 0),   # toblock
    21:  (6,   0, 0),   # mindamage
    22:  (7,   0, 0),   # maxdamage
    23:  (6,   0, 0),   # secondary_mindamage
    24:  (7,   0, 0),   # secondary_maxdamage
    25:  (8,   0, 0),   # damagepercent
    26:  (8,   0, 0),   # manarecovery
    27:  (8,   0, 0),   # manarecoverybonus
    28:  (8,   0, 0),   # staminarecoverybonus
    30:  (3,   0, 0),   # D2R stat 30 — confirmed save_bits=3; header stat on belts/gloves/boots preceding resist stats
    31:  (11, 10, 0),   # armorclass
    32:  (9,   0, 0),   # armorclass_vs_missile
    33:  (8,   0, 0),   # armorclass_vs_hth
    34:  (6,   0, 0),   # normal_damage_reduction
    35:  (6,   0, 0),   # magic_damage_reduction
    36:  (9, 200, 0),   # damageresist
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
    47:  (8,   0, 0),   # damageaura
    48:  (8,   0, 0),   # firemindam
    49:  (9,   0, 0),   # firemaxdam
    50:  (6,   0, 0),   # lightmindam
    51:  (10,  0, 0),   # lightmaxdam
    52:  (8,   0, 0),   # magicmindam
    53:  (9,   0, 0),   # magicmaxdam
    54:  (8,   0, 0),   # coldmindam
    55:  (9,   0, 0),   # coldmaxdam
    56:  (8,   0, 0),   # coldlength
    57:  (10,  0, 0),   # poisonmindam
    58:  (10,  0, 0),   # poisonmaxdam
    59:  (9,   0, 0),   # poisonlength
    60:  (7,   0, 0),   # lifedrainmindam
    61:  (7,   0, 0),   # lifedrainmaxdam
    62:  (7,   0, 0),   # manadrainmindam
    63:  (7,   0, 0),   # manadrainmaxdam
    64:  (12,  0, 0),   # unknown D2R stat
    65:  (7,   0, 0),   # stamdrainmaxdam
    66:  (8,   0, 0),   # stunlength
    67:  (7,  30, 0),   # velocitypercent
    68:  (7,  30, 0),   # attackrate
    69:  (8,   0, 0),   # unknown
    70:  (9,   0, 0),   # quantity
    71:  (8, 100, 0),   # value (vendor)
    72:  (9,   0, 0),   # durability
    73:  (8,   0, 0),   # maxdurability
    74:  (6,  30, 0),   # hpregen
    75:  (7,  20, 0),   # item_maxdurability_percent
    76:  (6,  10, 0),   # item_maxhp_percent
    77:  (6,  10, 0),   # item_maxmana_percent
    78:  (7,   0, 0),   # item_attackertakesdamage
    79:  (9, 100, 0),   # item_goldbonus
    80:  (8, 100, 0),   # item_magicbonus
    81:  (7,   0, 0),   # item_knockback
    82:  (9,  20, 0),   # item_timeduration
    83:  (3,   0, 3),   # item_addclassskills
    84:  (3,   0, 0),   # D2R stat 84 — empirically determined save_bits=3; header on some armor items
    85:  (9,  50, 0),   # item_addexperience
    86:  (7,   0, 0),   # item_healafterkill
    87:  (7,   0, 0),   # item_reducedprices
    88:  (1,   0, 0),   # item_doubleherbduration
    89:  (4,   4, 0),   # item_lightradius
    90:  (24,  0, 0),   # item_lightcolor
    91:  (8, 100, 0),   # item_req_percent
    92:  (7,   0, 0),   # item_levelreq
    93:  (7,  20, 0),   # item_fasterattackrate
    94:  (7,  64, 0),   # item_levelreqpct
    96:  (7,  20, 0),   # item_fastermovevelocity
    97:  (6,   0, 9),   # item_nonclassskill
    98:  (1,   0, 8),   # state
    99:  (7,  20, 0),   # item_fastergethitrate
    100: (8,   0, 0),   # D2R stat 100 — save_bits=8 best guess; appears on unique weapons
    101: (8,   0, 0),   # unknown
    103: (8,   0, 0),   # D2R stat 103 — save_bits=8 best guess; appears on rare armor items
    102: (7,  20, 0),   # item_fasterblockrate
    104: (1,   0, 0),   # skill_bypass_demons
    105: (7,  20, 0),   # item_fastercastrate
    107: (3,   0, 9),   # item_singleskill
    108: (1,   0, 0),   # item_restinpeace
    109: (9,   0, 0),   # curse_resistance
    110: (8,  20, 0),   # item_poisonlengthresist
    111: (9,  20, 0),   # item_normaldamage
    112: (7,  -1, 0),   # item_howl
    113: (7,   0, 0),   # item_stupidity
    114: (6,   0, 0),   # item_damagetomana
    115: (1,   0, 0),   # item_ignoretargetac
    116: (7,   0, 0),   # item_fractionaltargetac
    117: (7,   0, 0),   # item_preventheal
    118: (1,   0, 0),   # item_halffreezeduration
    119: (9,  20, 0),   # item_tohit_percent
    120: (7, 128, 0),   # item_damagetargetac
    121: (9,  20, 0),   # item_demondamage_percent
    122: (9,  20, 0),   # item_undeaddamage_percent
    123: (10,128, 0),   # item_demon_tohit
    124: (10,128, 0),   # item_undead_tohit
    125: (1,   0, 0),   # item_throwable
    126: (3,   0, 3),   # item_elemskill
    127: (3,   0, 0),   # item_allskills
    128: (5,   0, 0),   # item_attackertakeslightdamage
    129: (8,   0, 0),   # D2R stat 129 — save_bits=8 best guess; appears on magic amulets
    130: (8,   0, 0),   # D2R stat 130 — save_bits=8 best guess; appears on rare helms
    131: (11,  0, 0),   # D2R stat 131 — CONFIRMED save_bits=11 (leads to sentinel in Ruby Light Gauntlets)
    132: (6,   0, 0),   # bonearmor
    133: (7,   0, 0),   # bonearmormax
    134: (5,   0, 0),   # item_freeze
    135: (7,   0, 0),   # item_openwounds
    136: (7,   0, 0),   # item_crushingblow
    137: (7,   0, 0),   # item_kickdamage
    138: (7,   0, 0),   # item_manaafterkill
    139: (7,   0, 0),   # item_healafterdemonkill
    140: (7,   0, 0),   # item_extrablood
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
    151: (5,   0, 9),   # item_aura
    152: (1,   0, 0),   # item_indestructible
    153: (1,   0, 0),   # item_cannotbefrozen
    154: (7,  20, 0),   # item_staminadrainpct
    155: (7,   0, 10),  # item_reanimate
    156: (7,   0, 0),   # item_pierce
    157: (7,   0, 0),   # item_magicarrow
    158: (7,   0, 0),   # item_explosivearrow
    159: (6,   0, 0),   # item_throw_mindamage
    160: (7,   0, 0),   # item_throw_maxdamage
    161: (8,   0, 0),   # unknown
    166: (8,   0, 0),   # D2R stat 166 — save_bits=8 best guess; appears on rare jewelry
    167: (7,   0, 0),   # skill_conviction
    168: (7,   0, 0),   # skill_chillingarmor
    169: (8,   0, 0),   # unknown
    172: (2,   0, 0),   # alignment
    173: (8,   0, 0),   # target0
    174: (8,   0, 0),   # target1
    175: (8,   0, 0),   # unknown
    176: (8,   0, 0),   # conversion_level
    177: (8,   0, 0),   # conversion_maxhp
    178: (8,   0, 0),   # unit_dooverlay
    179: (9,   0, 10),  # attack_vs_montype
    180: (9,   0, 10),  # damage_vs_montype
    181: (3,   0, 0),   # fade
    182: (8,   0, 0),   # armor_override_percent
    183: (8,   0, 0),   # lasthitreactframe
    184: (8,   0, 0),   # create_season
    185: (8,   0, 0),   # bonus_mindamage
    186: (8,   0, 0),   # bonus_maxdamage
    187: (10,  0, 0),   # item_pierce_cold_immunity
    188: (3,   0, 16),  # item_addskill_tab
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
    204: (16,  0, 16),  # item_charged_skill
    205: (7,   0, 0),   # item_noconsume
    206: (8,   0, 0),   # passive_mastery_noconsume
    207: (8,   0, 0),   # passive_mastery_replenish_oncrit
    208: (9, 105, 0),   # mod lightning resist (displayed value = raw - 105)
    210: (8,   0, 0),   # D2R stat 210 — save_bits=8 best guess; appears on rare rings/jewelry
    211: (8,   0, 0),   # ua_defeated counter
    212: (8,   0, 0),   # unknown
    213: (8,   0, 0),   # passive_mastery_gethit_rate
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
    234: (6,   0, 0),   # item_absorb_cold_perlevel
    235: (6,   0, 0),   # item_absorb_fire_perlevel
    236: (6,   0, 0),   # item_absorb_ltng_perlevel
    237: (6,   0, 0),   # item_absorb_pois_perlevel
    238: (5,   0, 0),   # item_thorns_perlevel
    239: (6,   0, 0),   # item_find_gold_perlevel
    240: (6,   0, 0),   # item_find_magic_perlevel
    241: (6,   0, 0),   # item_regenstamina_perlevel
    242: (6,   0, 0),   # item_stamina_perlevel
    243: (6,   0, 0),   # item_damage_demon_perlevel
    244: (6,   0, 0),   # item_damage_undead_perlevel
    245: (6,   0, 0),   # item_tohit_demon_perlevel
    246: (6,   0, 0),   # item_tohit_undead_perlevel
    247: (6,   0, 0),   # item_crushingblow_perlevel
    248: (6,   0, 0),   # item_openwounds_perlevel
    249: (6,   0, 0),   # item_kick_damage_perlevel
    250: (6,   0, 0),   # item_deadlystrike_perlevel
    252: (6,   0, 0),   # item_replenish_durability
    253: (6,   0, 0),   # item_replenish_quantity
    254: (8,   0, 0),   # item_extra_stack
    255: (7,   0, 0),   # item_find_item
    256: (10,  0, 0),   # item_slash_damage
    257: (9,   0, 0),   # item_slash_damage_percent
    258: (10,  0, 0),   # item_crush_damage
    259: (10,  0, 0),   # item_thrust_damage
    260: (14,  0, 0),   # unknown D2R stat
    261: (9,   0, 0),   # item_crush_or_thrust_damage_percent
    262: (8,   0, 0),   # item_absorb_slash
    263: (8,   0, 0),   # item_absorb_crush
    264: (8,   0, 0),   # item_absorb_thrust
    265: (8,   0, 0),   # item_absorb_slash_percent
    266: (8,   0, 0),   # item_absorb_crush_percent
    267: (8,   0, 0),   # item_absorb_thrust_percent
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
    304: (22,  0, 0),   # item_find_gems_bytime
    305: (8,  50, 0),   # item_pierce_cold
    306: (8,  50, 0),   # item_pierce_fire
    307: (8,  50, 0),   # item_pierce_ltng
    308: (8,  50, 0),   # item_pierce_pois
    309: (8,   0, 0),   # item_damage_vs_monster
    310: (8,   0, 0),   # item_damage_percent_vs_monster
    311: (8,   0, 0),   # item_tohit_vs_monster
    312: (8,   0, 0),   # item_tohit_percent_vs_monster
    313: (8,   0, 0),   # item_ac_vs_monster
    314: (8,   0, 0),   # item_ac_percent_vs_monster
    315: (8,   0, 0),   # unknown
    316: (8,   0, 0),   # burningmin
    317: (9,   0, 0),   # burningmax
    318: (7,   0, 0),   # progressive_damage
    319: (7,   0, 0),   # progressive_steal
    320: (7,   0, 0),   # progressive_other
    321: (7,   0, 0),   # progressive_fire
    322: (7,   0, 0),   # progressive_cold
    323: (7,   0, 0),   # progressive_lightning
    324: (6,   0, 0),   # item_extra_charges
    325: (7,   0, 0),   # progressive_tohit
    326: (5,   0, 0),   # poison_count
    327: (8,   0, 0),   # damage_framerate
    328: (8,   0, 0),   # pierce_idx
    329: (9,  50, 0),   # passive_fire_mastery
    330: (9,  50, 0),   # passive_ltng_mastery
    331: (9,  50, 0),   # passive_cold_mastery
    332: (9,  50, 0),   # passive_pois_mastery
    333: (8,   0, 0),   # passive_fire_pierce
    334: (8,   0, 0),   # passive_ltng_pierce
    335: (8,   0, 0),   # passive_cold_pierce
    336: (8,   0, 0),   # passive_pois_pierce
    337: (8,   0, 0),   # passive_critical_strike
    338: (7,   0, 0),   # passive_dodge
    339: (7,   0, 0),   # passive_avoid
    340: (7,   0, 0),   # passive_evade
    341: (8,   0, 0),   # passive_warmth
    342: (8,   0, 0),   # passive_mastery_melee_th
    343: (8,   0, 0),   # passive_mastery_melee_dmg
    344: (8,   0, 0),   # passive_mastery_melee_crit
    345: (8,   0, 0),   # passive_mastery_throw_th
    346: (8,   0, 0),   # passive_mastery_throw_dmg
    347: (8,   0, 0),   # passive_mastery_throw_crit
    348: (8,   0, 0),   # passive_weaponblock
    349: (8,   0, 0),   # passive_summon_resist
    353: (8,   0, 0),   # D2R stat 353 — save_bits=8 best guess; appears on unique boots
    355: (1,   0, 0),   # shortparam1
    356: (2,   0, 0),   # questitemdifficulty
    357: (9,  50, 0),   # passive_mag_mastery
    358: (8,   0, 0),   # passive_mag_pierce
    359: (8,   0, 0),   # skill_cooldown
    360: (8,   0, 0),   # skill_missile_damage_scale
    361: (9,   0, 0),   # psychicward
    362: (9,   0, 0),   # psychicwardmax
    363: (8,   0, 0),   # unknown
    364: (8,   0, 0),   # customization_index
    365: (6,   0, 0),   # item_magic_damagemax_perlevel
    366: (8,   0, 0),   # passive_dmg_pierce
    367: (8,   0, 0),   # heraldtier
    396: (0,   0, 0),   # unknown D2R flag
    424: (0,   0, 0),   # unknown D2R flag
    **{k: (8, 0, 0) for k in range(368, 396)},   # D2R additions 368-395
    **{k: (8, 0, 0) for k in range(397, 424)},   # D2R additions 397-423
    **{k: (8, 0, 0) for k in range(425, 511)},   # D2R additions 425-510
    # Mod stat overrides (must come after catch-all ranges to take precedence)
    385: (8, 237, 0),   # mod extra gold from monsters (displayed value = raw - 237)
}

# Derived: stat_id → total bits to consume (save_param_bits + save_bits)
STAT_WIDTHS: dict[int, int] = {
    sid: (bits[2] + bits[0]) for sid, bits in STAT_TABLE.items()
}

# Stat IDs that are character/entity values — cannot legitimately appear in
# an item property list. Seeing one signals a mis-detected quality offset.
PROPERTY_BLOCKLIST: frozenset[int] = frozenset(
    {4, 5, 6, 8, 10, 12, 13, 14, 15, 29, 30, 353, 354}
)
