# Enigma Engine — Agent Reference

This project uses six specialist sub-agents defined in `.claude/agents/`. Each agent carries persistent project memory at `.claude/agent-memory/<agent-name>/` and knows the project's conventions in depth.

**How to invoke**: Use the `Agent` tool with `subagent_type` set to the agent name (e.g., `subagent_type: "backend-expert"`).

**General rule**: Prefer invoking a specialist agent over working directly when the task falls clearly in their domain. They have deeper context, accumulated memory of past decisions, and won't need re-orientation.

---

## backend-expert

**Invoke when**: Writing a new FastAPI router or endpoint, adding service layer logic, defining Pydantic request/response schemas, working with asyncio or paramiko SFTP patterns, or writing pytest unit tests. If the task touches `backend/routers/`, `backend/services/`, or `tests/`, invoke this agent.

**Key expertise**:
- Router / Service split architecture (routers: HTTP only; services: pure business logic)
- Non-negotiable constraints: binary safety rule, D2R running check, sync lock
- AsyncMock test patterns: `side_effect` for multiple `execute()` calls, patching at source module
- paramiko patterns: wrapping sync SFTP calls in `asyncio.to_thread`, conn kwargs conventions
- **Testing requirement**: Every code change must include unit tests. Coverage target is 90%+ for touched files. Run: `python3 -m pytest tests/ --cov=backend --cov-report=term-missing --cov-fail-under=90 -q`

---

## frontend-expert

**Invoke when**: Writing or modifying React components, adding TanStack Query hooks to `hooks.ts`, adding TypeScript types to `types.ts`, wiring a new page into `App.tsx` routing, or writing Vitest unit tests. If the task touches `frontend/src/`, invoke this agent.

**Key expertise**:
- TanStack Query v5 patterns: explicit generics, `queryKey` conventions, `invalidateQueries` on mutation
- TypeScript strict mode: `noUnusedLocals` + `noUnusedParameters` as compile errors; `T | null` for nullable fields
- D2-themed Tailwind design tokens: `d2gold`, `d2bg`, `d2bg-surface`, `font-diablo`, custom animations
- Vitest + Testing Library bootstrap (no frontend tests exist yet — agent knows the full setup)

---

## db-expert

**Invoke when**: Adding a new SQLAlchemy model, writing a migration block in `database.py`, designing a schema for a new feature, writing async SQLAlchemy queries, or writing unit tests that mock `AsyncSession`. If the task involves `models.py`, `database.py`, `ALTER TABLE`, or `session.execute` patterns, invoke this agent.

**Key expertise**:
- All models in single file `backend/models.py` (Column() style, not mapped_column())
- Migrations via manual `ALTER TABLE` blocks in `init_db()` — no Alembic
- Async query patterns: `select()`, `scalars()`, `session.execute()`, scalar results
- `AsyncMock` session patterns for unit tests

---

## feature-planner

**Invoke when**: Starting any new feature or capability — before writing any code. Trigger phrases: "I want to add", "let's build", "plan out", or any description of a capability that doesn't exist yet.

**Key expertise**:
- Scoping questions: season-scoped?, binary writes required?, which machines affected?
- Explores the closest analogous existing feature to maximize reuse
- Produces specific file paths, reuse opportunities, and an ordered task list
- Knows all 12 implemented features and how they interrelate

---

## ux-expert

**Invoke when**: Reviewing a page for usability issues, checking mobile/Steam Deck responsiveness, choosing Tailwind classes for a new layout, critiquing interaction flows, or ensuring touch targets and text sizes meet Steam Deck browser constraints. Invoke before shipping any new page or significant UI change.

**Key expertise**:
- Steam Deck browser constraints: touch targets, text size minimums, viewport dimensions
- Tailwind layout patterns for the D2-themed design system
- Interaction flow critique: loading states, error states, empty states
- Advisory role only — recommends specific Tailwind classes but does not write implementation files

---

## binary-investigator

**Invoke when**: Investigating unknown `.d2s` or `.d2i` file sections, mapping new offsets, calibrating parser bit widths, empirically verifying byte layouts, or debugging a parser that produces wrong output. If the task involves hex dumps, byte offsets, bit fields, or "what does this section contain", invoke this agent.

**Key expertise**:
- Empirical diffing methodology: snapshot pairs, hex comparison, controlled mutations
- D2R Modern vs Classic format differences (e.g., magic item prefix/suffix bit widths)
- `item_parsing/` package internals: `BitReader`, Huffman decode, deterministic field positions
- Known section layouts: `lf` demon section (96 + 24 bytes), `gf` stats block, checksum recalculation

---

## Agent Memory

Each agent maintains persistent memory at `.claude/agent-memory/<agent-name>/MEMORY.md`. These files accumulate discoveries, pattern decisions, and context specific to each domain. When starting a task in an agent's domain, the agent pre-loads its memory automatically.

Memory directories:
```
.claude/agent-memory/backend-expert/
.claude/agent-memory/frontend-expert/
.claude/agent-memory/db-expert/
.claude/agent-memory/feature-planner/
.claude/agent-memory/ux-expert/
.claude/agent-memory/binary-investigator/
```
