# Codebase Concerns

**Analysis Date:** 2026-03-28

## Tech Debt

**Inline schema migrations in `init_db()` instead of a migration tool:**
- Issue: Every schema change is appended as `try/except ALTER TABLE` blocks inside `backend/database.py:init_db()`. This approach is fragile — order-dependent, silently ignores all exceptions, and has grown to ~140 lines of migration code mixed with table creation.
- Files: `backend/database.py` (lines 21–154)
- Impact: No rollback capability. Migrations that partially fail leave schema in an unknown state — the bare `except Exception: pass` means any error other than "column already exists" is silently swallowed. This already caused data loss previously.
- Fix approach: Migrate to Alembic. Generate initial revision from current models, add future changes as versioned migration scripts.

**`print()` statements left in production sync path:**
- Issue: Two `print()` calls exist in `backend/services/backup_manager.py` at lines 294 and 426 inside the core sync flow (`run_sync`). The rest of the codebase uses `logging`.
- Files: `backend/services/backup_manager.py:294`, `backend/services/backup_manager.py:426`
- Impact: Inconsistent observability; `print()` bypasses log level filtering, format, and handlers.
- Fix approach: Replace with `log.info(...)`.

**Pervasive bare `except Exception` catching:**
- Issue: Nearly every router endpoint wraps the entire handler body in `except Exception as e` and re-raises as HTTP 500 or 400. This masks the actual exception type, prevents targeted handling (e.g., retrying only on network errors vs. aborting on parse errors), and collapses all failures to the same response shape.
- Files: `backend/routers/sync.py` (13 occurrences), `backend/routers/stash.py` (6), `backend/routers/grail.py` (2), `backend/routers/backups.py` (4), `backend/routers/settings.py` (2), `backend/routers/rewards.py` (2), `backend/routers/characters.py` (2), `backend/routers/seasons.py` (1), `backend/database.py` (3)
- Impact: Difficult to distinguish SSH failures from parse errors from DB errors in logs. Some catch sites silently swallow errors with no logging (`backend/routers/autosync.py:86`, `backend/routers/autosync.py:128`).
- Fix approach: Catch specific exception types (`SSHConnectionError`, `HTTPException`, `D2SParseError`). Use `except Exception` only as a final fallback with structured logging.

**`_fernet()` function re-derives encryption key on every call:**
- Issue: `backend/routers/settings.py:_fernet()` imports `base64` and `hashlib` inline, re-derives the Fernet key from the secret on every invocation, and creates a new `Fernet` instance each time. Called during every SSH connection attempt.
- Files: `backend/routers/settings.py:43–48`
- Impact: Minor CPU overhead per-call; inline imports are non-idiomatic.
- Fix approach: Cache the `Fernet` instance (e.g., via `lru_cache` or module-level lazy init).

**`staging_dir` created in `config.py` but never initialized at startup:**
- Issue: `backend/config.py` defines `staging_dir` as `data_dir / "staging"`. The lifespan in `backend/main.py` creates `tmp_dir` but not `staging_dir`. The staging directory is referenced in `backend/routers/sync.py:166` for cleanup.
- Files: `backend/config.py:26`, `backend/main.py:26–36`, `backend/routers/sync.py:166`
- Impact: If `staging_dir` does not exist before sync runs, cleanup path may fail silently (`shutil.rmtree(ignore_errors=True)` masks this).
- Fix approach: Add `cfg.staging_dir.mkdir(parents=True, exist_ok=True)` to `main.py:lifespan`.

**`auto_sync.py` watcher task has no cancellation/shutdown handling:**
- Issue: `run_auto_sync_watcher()` is launched via `asyncio.create_task()` in `main.py:35` with no reference stored, no cancellation on shutdown, and no `yield`-after-shutdown cleanup. The `lifespan` context manager does not cancel the task on exit.
- Files: `backend/main.py:35`, `backend/services/auto_sync.py:390–645`
- Impact: On Uvicorn shutdown, the task is abandoned mid-poll. If mid-sync, file writes may be incomplete. Graceful shutdown is not guaranteed.
- Fix approach: Store the task reference, cancel it in the lifespan's shutdown block, and add a short `asyncio.wait_for` grace period.

---

## Security Considerations

**No API authentication:**
- Risk: All endpoints are unauthenticated. Any process on the Docker host network can call `POST /api/sync/push`, `DELETE /api/grail/reset`, `POST /api/seasons/{id}/start`, etc.
- Files: `backend/main.py` (no auth middleware), all router files
- Current mitigation: The app is designed for private LAN use only. Docker networking limits exposure.
- Recommendations: Add optional API key authentication (env var `APP_API_KEY`); configure Docker to bind only to localhost if not LAN-accessible.

**Default `secret_key` in `config.py`:**
- Risk: The default `secret_key = "change-me-in-production-32-chars!!"` is used to derive the Fernet encryption key for SSH passwords stored in the DB. If not overridden, SSH credentials are "encrypted" with a publicly known key.
- Files: `backend/config.py:7`, `backend/routers/settings.py:43–48`
- Current mitigation: None — the default is accepted silently.
- Recommendations: Add a startup assertion that `SECRET_KEY` is not the default value, or at minimum log a prominent warning on startup.

**Hardcoded app URL in notification email body:**
- Risk: `backend/services/notify.py:91` hardcodes `http://enigma-engine.local:8080` in the conflict notification email body. If deployed under a different hostname or port, the link is wrong.
- Files: `backend/services/notify.py:91`
- Fix approach: Make the base URL a config setting (`APP_BASE_URL`) with a default of `http://enigma-engine.local:8080`.

**SSH key files stored with no explicit permission enforcement:**
- Risk: Uploaded SSH private keys are written to `data/keys/{machine}.pem` with default umask permissions. Paramiko requires restrictive permissions (0600) on key files or it raises an error. The upload endpoint does not call `os.chmod`.
- Files: `backend/routers/settings.py:207–228`
- Current mitigation: Paramiko will refuse to use a key with world-readable permissions, failing loudly rather than silently leaking.
- Recommendations: Explicitly set `os.chmod(key_path, 0o600)` after upload.

---

## Fragile Areas

**`CHARM_PREFIX_TABLE` stat value ranges need ongoing calibration:**
- Files: `backend/services/item_parsing/tables/affixes.py:19`
- Why fragile: The comment on line 19 states: "stat 119 (item_tohit_percent) ranges are from old parser — may need adjustment." The `CHARM_PREFIX_TABLE` is the source of truth for charm name display in the stash. Wrong ranges produce wrong item names silently — the item just shows its type code instead of a readable name.
- Safe modification: Update ranges based on in-game D2R data files (`ItemStatCost.txt`, `MagicPrefix.txt`). Always test with known items from the real stash fixture.
- Test coverage: `tests/item_parsing/test_name_resolution.py` covers some charm names but conditionally skips when specific items are not in the fixture.

**Item stash visual grid not rendered — items shown as flat list:**
- Files: `frontend/src/pages/Stash.tsx` (all item card components)
- Why fragile: `position_x`/`position_y` are parsed from item flags (`backend/services/item_parsing/item_flags.py:66–67`) and stored on `ParsedItem`, but the frontend ignores them entirely. Items render as a scrollable card list per tab, not the D2R 10×10 grid layout.
- Impact: Cosmetic. Users cannot visually locate items by their in-game grid position. Not a correctness issue.

**Runeword quality badge displays "NRM" instead of quality name:**
- Files: `frontend/src/pages/Stash.tsx:58–60`
- Why fragile: Runeword items have base-armor quality (2 = Normal). The `qualityLabel(quality)` function returns "NRM" for quality 2. No special case exists for runewords even though `item.is_runeword` is available.
- Impact: Cosmetic — deferred per project memory.

**Boss Summon: Diablo Clone detection uses base ring type `"rin"` not Stone of Jordan unique_id:**
- Files: `backend/services/boss_summon_service.py:52`
- Why fragile: The comment "SoJ — base ring type; acceptable for personal use" acknowledges this matches ANY ring deposited to tab 5, not specifically a Stone of Jordan. Any ring in tab 5 triggers the Dclone progress check.
- Impact: False-positive detection if non-SoJ ring is placed in the portal tab.
- Safe modification: Once a SoJ reward library entry exists, `reward_unique_ids` matching logic (lines 164–208) will automatically narrow detection to the specific unique_id.

---

## Test Coverage Gaps

**`BossSummonService` core logic has no dedicated tests:**
- What's not tested: `check_boss_summon_progress()`, `retrieve_boss_summon_items()`, `_parse_unique_id_from_bytes()`, `_match_item_against_set()`
- Files: `backend/services/boss_summon_service.py` (510 lines), `backend/routers/boss_summon.py`
- Risk: Stash modification logic runs on live save files. A parsing regression in boss summon detection would be invisible until in-game testing.
- Priority: High — writes binary stash files.

**Grail deposit/retrieve service (`grail_service.py`) has no dedicated unit tests:**
- What's not tested: `deposit_tab5()`, `retrieve_item_to_tab5()`, `preview_tab5()`, `process_portal_tab_hook()`
- Files: `backend/services/grail_service.py` (516 lines)
- Risk: These write to the shared stash binary. Tests in `tests/item_parsing/test_grail.py` test the item parsing layer only — not the service-level deposit/retrieve flow or the backup-before-write guard.
- Priority: High — directly modifies .d2i files.

**Notification service (`notify.py`) has no tests:**
- What's not tested: `_send_ses_email()`, `notify_conflict()` provider dispatch, config loading
- Files: `backend/services/notify.py`
- Risk: Low — broken notifications are non-critical. AWS SES errors are logged and swallowed.
- Priority: Low.

**Demon vault restore flow has partial test coverage:**
- What's not tested: `restore_demon_to_d2s()` checksum recalculation, `lf` section splicing
- Files: `backend/services/demon_service.py`, `backend/routers/demon.py`
- Risk: Checksum error corrupts the `.d2s` character file permanently.
- Priority: Medium — restore creates a backup, so corruption is recoverable.

**`test_item_parsing/test_grail.py` conditionally skips most test cases:**
- Files: `tests/item_parsing/test_grail.py:37`, `tests/item_parsing/test_grail.py:69`, `tests/item_parsing/test_grail.py:87`
- What's not tested: All three test classes skip with `pytest.skip` if the fixture stash has no items in the relevant tabs. The tests are dependent on a real stash fixture having the right items populated.
- Risk: Test suite passes green even if grail parsing is broken, as long as fixture tabs are empty.
- Priority: Medium — fix by adding synthetic fixture stash bytes with known items.

---

## Performance Bottlenecks

**Auto-sync watcher opens a new DB session every 30 seconds for each KV read:**
- Problem: `_get_autosync_setting()` calls `AsyncSessionLocal()` as a context manager, creating a new session per call. The watcher loop calls this multiple times per iteration for `autosync_enabled`, `autosync_poll_interval`, `autosync_pc_enabled`, `autosync_deck_enabled`, and `autosync_state`.
- Files: `backend/services/auto_sync.py:54–56`, `backend/services/auto_sync.py:395–415`
- Cause: Settings reads are not batched within a single session per poll cycle.
- Improvement path: Open one session per poll cycle, batch all reads within it.

**`_fernet()` creates a new Fernet instance per SSH connection:**
- Problem: Every SSH operation calls `_get_conn_kwargs()` → `decrypt()` → `_fernet()`, which re-derives the key and constructs a new `Fernet` object each time.
- Files: `backend/routers/settings.py:43–48`
- Cause: No caching of the Fernet instance.
- Improvement path: `@lru_cache` on `_fernet()` since the key derives from the immutable `secret_key` setting.

---

## Scaling Limits

**SQLite single-writer constraint:**
- Current capacity: Adequate for 1–2 concurrent users on a LAN.
- Limit: SQLite's write serialization causes contention if multiple write operations (sync + grail deposit + auto-sync push) occur simultaneously. The `asyncio.Lock` in `sync.py` only serializes sync operations — grail, vault, and rewards writes are unguarded.
- Scaling path: Migrate to PostgreSQL if multi-user or concurrent write scenarios arise.

**All backup files stored on the Docker host volume with no total size cap:**
- Current capacity: `pre_sync` keeps 5, `manual`/`game_close` keeps 1, others keep 5. Season archives are never pruned.
- Limit: Each snapshot is a full copy of the save directory. Season archives accumulate indefinitely. On a small SSD (`/app/data` volume), this can grow silently.
- Scaling path: Add a configurable maximum for season archive count, or a total backup size warning in the Backups UI.

---

## Dependencies at Risk

**`paramiko` used as synchronous SFTP client inside `asyncio.to_thread`:**
- Risk: All SFTP operations block a thread pool worker. If multiple concurrent SFTP calls happen (e.g., auto-sync + manual checkin), thread pool exhaustion could cause latency spikes.
- Impact: Manageable at current single-user scale. Under concurrent load (e.g., future multi-user support), could cause request timeouts.
- Migration plan: Replace with `asyncssh` for native async SFTP, or ensure thread pool size is configured in Uvicorn.

**`boto3` loaded unconditionally at module import:**
- Risk: `backend/services/notify.py` imports `boto3` at the top level. If AWS credentials are not configured, `boto3` Session creation succeeds but `client.send_email()` fails at call time. However, the import itself will fail if `boto3` is not installed.
- Files: `backend/services/notify.py:18`
- Impact: If `boto3` is removed from the dependency list, the entire app fails to start even for installs that do not use SES notifications.
- Migration plan: Lazy-import `boto3` inside `_send_ses_email()` to prevent startup failure when SES is not configured.

---

## Missing Critical Features

**No authentication or access control:**
- Problem: Any process on the Docker network can trigger destructive operations (reset grail, start/end seasons, delete backups, push saves to remote machines).
- Blocks: Safe multi-device LAN exposure, user sharing the app URL with others.

**Item grid positions parsed but not displayed:**
- Problem: `position_x` and `position_y` are extracted from item flags and stored on `ParsedItem`, but the Stash page renders items as a flat card list rather than a visual 10×10 grid.
- Files: `frontend/src/pages/Stash.tsx`, `backend/services/item_parsing/item_flags.py:66–67`
- Blocks: Visual parity with in-game stash layout.

---

*Concerns audit: 2026-03-28*
