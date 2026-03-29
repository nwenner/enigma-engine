# DB Expert Memory — Enigma Engine

## All Models (backend/models.py)
14 SQLAlchemy ORM models, all Column() style in one file.

### Sync
- **SyncOperation**: id, direction(pc_to_deck|deck_to_pc), status(pending|running|success|failed), error_message, started_at, completed_at, file_count
- **SyncFileRecord**: id, sync_operation_id, filename, source_machine, dest_machine, bytes_transferred, success, error_message, char_snapshot(JSON), synced_at

### Snapshots
- **BackupSnapshot**: id, source_machine(pc|deck), snapshot_path, file_count, characters(JSON), created_at, sync_operation_id, label
  - Labels: game_close|manual|pre_sync|pre_grail_deposit|pre_grail_retrieve|pre_vault_gold|pre_vault_store|pre_vault_retrieve|season_archive|pre_seed_restore|pre_demon_restore

### Characters
- **Character**: id, uuid(unique), filename, season_id(FK→seasons nullable), name, class_id, class_name, level, hardcore, ever_died, expansion, difficulty_active, modified_at(Float), last_updated_at
  - Partial indexes: uq_active_character_filename (season_id IS NULL), uq_archived_character_filename_season (season_id IS NOT NULL)

### Settings (KV store)
- **Settings**: id, key(unique), value — stores SSH config (Fernet-encrypted), autosync_state(JSON), notification config, feature flags

### Seasons
- **Season**: id, name, started_at, ended_at, notes
- **SeasonMilestone**: id, season_id(FK), name, description, target_value, milestone_type, order_index
- **SeasonAchievement**: id, milestone_id(FK), achieved_at, claimed_at, reward_item_id(FK nullable)

### Grail
- **HolyGrailItem** (GrailCatalog): id, unique_id, name, base_item, image_url
- **GrailDeposit**: id, grail_item_id(FK), snapshot_id(FK), deposited_at
- **GrailRetrieve**: id, grail_item_id(FK), retrieved_at

### Vault
- **VaultItem**: id, season_id(FK nullable), name, item_type, raw_bytes(LargeBinary), stored_at
- **GoldVault**: id, balance(BigInteger)

### Domain
- **BoundDemon**: id, label, character_filename, demon_bytes(LargeBinary), notes, saved_at
- **SavedSeed**: id, label, seed_value(Integer), source_character, source_class, source_version, notes, tags(JSON), created_at

## Season Scoping Pattern
- `season_id IS NULL` → belongs to current active season
- `season_id = X` → archived to season X
- Always filter `Model.season_id == None` for current data
- **Global models** (no season_id): SavedSeed, Settings, HolyGrailItem, GoldVault, BoundDemon

## Migration System
Manual `ALTER TABLE` blocks in `database.py::init_db()` — NOT Alembic.
Guard with PRAGMA table_info check before each ALTER:
```python
existing = await conn.run_sync(lambda c: c.execute(text("PRAGMA table_info(table)")).fetchall())
col_names = {row[1] for row in existing}
if "new_col" not in col_names:
    await conn.execute(text("ALTER TABLE t ADD COLUMN new_col TEXT"))
```

## SQLite Constraints
- ADD COLUMN: supported
- No native arrays → use JSON column
- No ALTER COLUMN → workaround with new table if needed
- Partial indexes: sqlite_where=text("...") in Index()
