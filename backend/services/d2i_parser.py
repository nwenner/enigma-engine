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
from ._d2i_tables import (
    _STAT_TABLE,
    _SKILL_NAMES,
    _DMG_PAIRS,
    MODERN_HEADER_SIZE,
    MODERN_SEP_SIZE,
    _MOD_QUALITY_SCAN_START,
    _MOD_QUALITY_SCAN_END,
    _MOD_QUALITY_SCAN_END_WIDE,
    _MOD_MAX_UNIQUE_ID,
    _MOD_MAX_SET_ID,
    _MOD_HUFFMAN_CODE_START,
    _HUFFMAN_REVERSE,
    MOD_ITEM_NAMES,
    _MAGIC_PREFIXES,
    _MAGIC_SUFFIXES,
    _CHARM_PREFIX_TABLE,
    _SKILLTAB_PREFIX_NAMES,
    _RARE_PREFIXES,
    _RARE_SUFFIXES,
    _PROPERTY_BLOCKLIST,
    _CLASS_NAMES,
    _PROC_EVENTS,
)


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




def _lookup_charm_prefix_name(
    item_code: str,
    stat_list: list[tuple[int, int, int]],
) -> str | None:
    """Return a magic charm's prefix name from its actual parsed stats.

    Bypasses stored prefix_id entirely — Classic D2 and D2R use different row
    numbering in magicprefix.txt so stored IDs are unreliable for charms.

    item_code: Huffman-decoded 4-char code ('cm1 ', 'cm2 ', 'cm3 ').
    stat_list: (stat_id, param, display_value) triples from _parse_property_list.
    """
    charm_itype_map = {'cm1': 'scha', 'cm2': 'mcha', 'cm3': 'lcha'}
    itype = charm_itype_map.get(item_code.strip())
    if not itype:
        return None
    itype_table = _CHARM_PREFIX_TABLE.get(itype, {})
    for stat_id, param, stored_val in stat_list:
        # Skill-tab bonus (Grand Charms only): stat 188, param encodes class+tab.
        # Binary encoding: (class_id << 3) | tab_within_class
        # Convert to mod1param (class_id * 3 + tab) for _SKILLTAB_PREFIX_NAMES lookup.
        if stat_id == 188 and itype == 'lcha':
            class_id = param >> 3
            tab = param & 7
            if tab <= 2:
                name = _SKILLTAB_PREFIX_NAMES.get(class_id * 3 + tab)
                if name:
                    return name
            continue
        ranges = itype_table.get(stat_id)
        if not ranges:
            continue
        for stored_min, stored_max, name in ranges:
            if stored_min <= stored_val <= stored_max:
                return name
    return None


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


def _property_list_end(
    raw: bytes | bytearray,
    bit_start: int,
    max_bit: int,
    min_stats: int = 0,
) -> int:
    """
    Like _full_property_list_valid but returns the bit position immediately after
    the 0x1FF sentinel on success, or -1 on failure.  Used as a tiebreaker in
    Phase 2: among two equally-validated magic item (q=3) candidates, prefer the
    one whose property list ends closest to max_bit (the item boundary), since
    false-positive property lists tend to terminate well before the real item end.
    """
    reader = BitReader(raw, bit_start)
    stat_count = 0
    for _ in range(64):
        if reader.tell() + 9 > max_bit:
            return -1
        sid = reader.read(9)
        if sid == 0x1FF:
            return reader.tell() if stat_count >= min_stats else -1
        if sid not in _STAT_TABLE:
            return -1
        save_bits, _, save_param = _STAT_TABLE[sid]
        needed = save_param + save_bits
        if reader.tell() + needed > max_bit:
            return -1
        if save_param:
            reader.read(save_param)
        reader.read(save_bits)
        stat_count += 1
    return -1


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
        best_prop_end: int = -1      # bit position after sentinel (for q=3 tiebreaker)
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

            # For magic items (q=3), compute where the property list sentinel falls.
            # Used as a tiebreaker: among equal candidates the one whose sentinel lands
            # closest to the item boundary (max_bit) is most likely the real item, since
            # false-positive property lists tend to end well before the true item end.
            prop_end = (
                _property_list_end(raw, props_start, max_bit, min_stats=1)
                if is_full and q == 3 else -1
            )

            # Determine if this candidate beats the current best:
            #   1. Nothing found yet → always take it.
            #   2. Upgrade from lite to full validation → take it.
            #   3. Same validation tier, prefer higher quality value.
            #      (q=1/2 are weakly distinctive and often false-positives; q=3+ are more reliable)
            #   4. For q=3 magic ties: prefer the candidate whose property list ends
            #      closest to max_bit (the item boundary); false positives tend to end early.
            is_better = (
                best_props_start < 0
                or (is_full and not best_full)
                or (is_full == best_full and q > best_q)
                or (is_full and best_full and q == 3 == best_q and prop_end > best_prop_end)
            )
            if is_better:
                best_props_start = props_start
                best_q    = q
                best_ilvl = ilvl
                best_full = is_full
                best_prop_end = prop_end
                best_magic_prefix_id = qd.get("magic_prefix_id", 0)
                best_magic_suffix_id = qd.get("magic_suffix_id", 0)
                best_rare_name1 = qd.get("rare_name1", 0)
                best_rare_name2 = qd.get("rare_name2", 0)
                if is_full and q >= 3:
                    break  # Full validation + magic/rare/crafted/tempered: can't do better.

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
        log.debug(
            "MAGIC item %r @ byte %d: q_bit_area=%d..%d  best_q_bit=%d  "
            "pid=%d→%r  sid=%d→%r  ilvl=%d  full=%s  prop_end=%d  max_bit=%d",
            _decode_huffman_item_code(raw, byte_start), byte_start,
            _MOD_QUALITY_SCAN_START, _MOD_QUALITY_SCAN_END_WIDE,
            best_props_start,  # approximate (props_start, not q_bit itself)
            best_magic_prefix_id, magic_prefix,
            best_magic_suffix_id, magic_suffix,
            best_ilvl, best_full, best_prop_end, max_bit,
        )
        # For magic charms: stat-based lookup overrides stored prefix_id.
        # Stored prefix_id uses Classic D2 row numbering; D2R magicprefix.txt uses different
        # row numbers, making the ID→name mapping unreliable for charms.
        item_code_for_prefix = _decode_huffman_item_code(raw, byte_start)
        if item_code_for_prefix.startswith("cm") and best_props_start >= 0:
            raw_stats = _parse_property_list(raw, best_props_start, max_bit)
            stat_name = _lookup_charm_prefix_name(item_code_for_prefix, raw_stats)
            if stat_name:
                magic_prefix = stat_name
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
