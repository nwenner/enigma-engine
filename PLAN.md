# Item Parser Strategic Plan

## Why We Keep Spinning (Honest Diagnosis)

Three compounding problems:

1. **No reference implementation.** We're reverse-engineering a binary format by guessing
   field widths and offsets, then checking against one or two live items. Every edge case
   requires another round-trip. The C# parser you found would short-circuit most of this.

2. **The file is too large to navigate efficiently.** At 4,903 lines, d2i_parser.py is mostly
   static data tables (~3,300 lines of dicts). Every session I spend tokens re-reading
   context I've already read. This directly eats into your daily session budget.

3. **No actionable resume document.** MEMORY.md is good for architecture, but doesn't tell
   a fresh session "here's the exact bug, here's what failed, here's the exact next step."
   Each session re-investigates the same ground.

---

## Immediate Fix First (The Viridian Bug)

We have everything we need to fix this RIGHT NOW in this session.

**Root cause:** prefix_id stored in .d2i uses Classic D2 row numbering.
Our `_MAGIC_PREFIXES` table was built from D2R's magicprefix.txt (which inserted ~204 new rows,
shifting IDs). ID 203 = 'Viridian' in Classic D2 → 'Tireless' in D2R row 203.

**Why the last fix didn't work:** The stat-based lookup falls back to the file
`/app/data/tmp/excel/magicprefix.txt` at runtime. Either the file isn't accessible in Docker
at the path the code expects, or `_CHARM_PREFIXES_BY_STAT` cached as `{}` (empty = falsy)
before the file was found, and `if not lookup: return None` short-circuits.

**The actual fix:** Hard-code the charm prefix data directly as a Python constant —
no file I/O, no Docker path dependency, no caching issues. The data was already generated
from magicprefix.txt and is ready to embed.

**Steps:**
1. Replace `_CHARM_PREFIXES_BY_STAT` global + `_get_charm_prefix_by_stat()` loader
   with a hard-coded `_CHARM_PREFIX_TABLE` constant (data is ready)
2. Update `_lookup_charm_prefix_name` to use the table directly (3-line change)
3. Rebuild Docker → verify Viridian shows correctly

---

## Phase 0: Fix the Context Problem (Before Next Session)

### A. Extract data tables to a separate file
Split d2i_parser.py into:
- `backend/services/_d2i_tables.py` — all static dicts (~3,300 lines):
  `_STAT_TABLE`, `_SKILL_NAMES`, `MOD_ITEM_NAMES`, `_MAGIC_PREFIXES`, `_MAGIC_SUFFIXES`,
  `_RARE_PREFIXES`, `_RARE_SUFFIXES`, `_CHARM_PREFIX_TABLE`, `_HUFFMAN_REVERSE`
- `backend/services/d2i_parser.py` — logic only (~1,600 lines, with one import line added)

**Why this matters for sessions:** I can read the 1,600-line logic file completely in one
read instead of paging through 4,903 lines. Edits are faster to validate. Fewer tokens wasted.

### B. Create memory/parser-status.md
A focused resume doc that a fresh session reads first. Contains:
- Current known bugs with exact reproduction steps
- What has been tried and why it failed (so we don't repeat)
- The immediate next action (no re-investigation needed)
- Key line numbers for the relevant code sections

This is updated at the end of every session. A fresh session reads this first,
then reads only the relevant 100-200 lines of the logic file. No re-exploration needed.

---

## Phase 1: Name + Type Only (D2R Softcore Priority)

Goal: Every item in the stash shows correct **base name**, **quality badge**, and **display name**.
Stats are explicitly out of scope for this phase.

### What "done" looks like for Phase 1:
- Small Charm → "Viridian Small Charm" (not "Tireless Small Charm")
- Unique charm → "Annihilus" (not "Unique Small Charm")
- Rare belt → "Death Knell" (not "Rare Belt")
- Magic sword → "Cruel Crystal Sword of Evisceration"
- Normal base → "Monarch"

### Items to build/fix:
1. **Charm prefix fix** (Immediate, this session)
2. **Charm suffix fix** — verify suffix names aren't also affected by ID shifting
3. **Other magic item prefix/suffix** — are non-charm magic items affected too?
   Rings, amulets, weapons, armor may have the same Classic D2 vs D2R ID mismatch.
   Test matrix needed.
4. **Quality detection accuracy** — document any known misclassifications

### Test matrix approach:
Pick 10-15 real items from your SC stash across all item types.
For each: note expected name, check what we display, file as specific bug.
Work through them one at a time. This prevents chasing phantom issues.

---

## Phase 2: Find and Integrate the C# Reference Parser

You mentioned finding a C# library that handles D2R item parsing correctly.
This is the highest-leverage thing we can do to stop the reverse-engineering guessing game.

**What to do:**
1. Find the exact library/repo you found (search conversation history or GitHub)
2. Document it in memory/parser-status.md with: repo URL, what it parses, key files
3. Use it as a validation oracle: for any item where our output differs from the reference,
   the reference is correct and we debug our code against it
4. If the reference handles something we haven't implemented (item type codes, affix IDs),
   port that logic directly rather than inventing our own

Candidates to check:
- `nokka/d2s` (Go) — well-maintained D2 save parser
- `d2-stash-organizer` by Yolwoocle (JavaScript) — D2R stash specific
- The C# library you found (unknown name — search your browser history or GitHub bookmarks)

---

## Phase 3: Stats (Later)

Only after Phase 1 is solid and validated. Stats are display-only — they don't affect
your ability to USE the stash to find and manage items.

---

## Session Efficiency Rules Going Forward

1. **Read parser-status.md first** — no re-exploration
2. **One bug at a time** — fix it, verify it, update parser-status.md, then next
3. **Viridian-class bugs** (wrong prefix/suffix names) — fix with hard-coded tables, not file I/O
4. **No new features** until current bugs are fixed and test matrix passes

---

## This Session's Agenda (proposed)

1. Apply Viridian fix (hard-coded charm prefix table) — ~15 min
2. Extract data tables to `_d2i_tables.py` — ~20 min
3. Create memory/parser-status.md — ~10 min
4. If time: test matrix — pick 5 items, check names, file any new bugs

Approve this plan and I'll execute in order. Each step is independently verifiable.
