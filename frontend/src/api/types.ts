export interface CharacterInfo {
  filename: string;
  name: string;
  class_id: number;
  class_name: string;
  level: number;
  hardcore: boolean;
  ever_died: boolean;
  expansion: boolean;
  modified_at: number;      // epoch seconds
  last_updated_at: string;  // ISO datetime
}

export interface SyncStatusResponse {
  id: number;
  direction:
    | "pc_to_deck"
    | "deck_to_pc"
    | "checkin_pc"
    | "checkin_deck"
    | "app_to_pc"
    | "app_to_deck";
  status: "pending" | "running" | "success" | "failed";
  error_message: string | null;
  started_at: string;
  completed_at: string | null;
  file_count: number;
}

export interface FileCompareEntry {
  filename: string;
  device_mtime: number | null;
  app_mtime: number | null;
}

export interface SyncCompareResponse {
  device_older: FileCompareEntry[];
  device_newer: FileCompareEntry[];
  device_only: FileCompareEntry[];
  app_only: FileCompareEntry[];
  has_app_data: boolean;
  pushed_since_season_start: boolean;
}

export interface PreflightResponse {
  pc_running: boolean | null;
  deck_running: boolean | null;
  pc_error: string | null;
  deck_error: string | null;
  safe_to_sync: boolean;
}

export interface SnapshotResponse {
  id: number;
  source_machine: string;
  snapshot_path: string;
  file_count: number;
  characters: CharacterInfo[] | null;
  created_at: string;
  sync_operation_id: number | null;
  label: string;
}

export interface FileRecordResponse {
  id: number;
  filename: string;
  source_machine: string;
  dest_machine: string;
  bytes_transferred: number;
  success: boolean;
  error_message: string | null;
  char_snapshot: CharacterInfo | null;
  synced_at: string;
}

export interface SyncOperationResponse {
  id: number;
  direction: string;
  status: string;
  error_message: string | null;
  started_at: string;
  completed_at: string | null;
  file_count: number;
  files: FileRecordResponse[];
}

export interface HistoryResponse {
  total: number;
  page: number;
  page_size: number;
  items: SyncOperationResponse[];
}

export interface MachineSettings {
  host: string;
  port: number;
  username: string;
  password: string;
  auth_type: "password" | "key";
  save_path: string;
  key_uploaded: boolean;
}

export interface SettingsResponse {
  pc: MachineSettings;
  deck: MachineSettings;
}

export interface TestConnectionResponse {
  success: boolean;
  message: string;
}

export interface NotificationConfig {
  type: "none" | "ses";
  aws_profile: string;
  aws_region: string;
  ses_from: string;
  ses_to: string;
}

export interface AutoSyncState {
  status: "idle" | "pending" | "conflict";
  direction: "pc_to_deck" | "deck_to_pc" | null;
  detected_at: string | null;
  expires_at: string | null;
  reason: string | null;
  staged_path: string | null;
  staged_file_count: number | null;
}

export interface AutoSyncStatus {
  enabled: boolean;
  poll_interval: number;
  state: AutoSyncState | null;
}

export interface GrailItem {
  catalog_id: number;
  item_code: string;
  name: string;
  base_item: string;
  quality: "unique" | "set";
  set_name: string | null;
  sort_order: number;
  found: boolean;
  find_count: number;
  found_at: string | null;
  last_found_at: string | null;
  is_deposited: boolean;
}

export interface StashItem {
  page_item_index: number;
  item_type: string;       // 4-char Huffman-decoded code e.g. "cm1", "rin"
  name: string | null;
  base_item: string | null;
  quality: number;
  quality_name: string;
  unique_id: number | null;
  set_id: number | null;
  is_ear: boolean;
  is_simple: boolean;
  item_level: number;
  is_ethereal: boolean;
  properties: string[];
}

export interface StashTab {
  index: number;
  item_count: number;
  items: StashItem[];
}

export interface StashResponse {
  machine: string;
  hardcore: boolean;
  gold: number;
  vault_gold: number;
  tabs: StashTab[];
  snapshot_at: string | null;
}

export interface VaultItemResponse {
  id: number;
  name: string | null;
  base_item: string | null;
  quality: number;
  quality_name: string;
  tab: number;
  hardcore: boolean;
  stored_at: string;
  catalog_id: number | null;
  item_level: number;
  is_ethereal: boolean;
  properties: string[];
}

export interface GoldVaultResponse {
  hardcore: boolean;
  amount: number;
}

export interface GrailProgress {
  hardcore: boolean;
  unique_total: number;
  unique_found: number;
  set_total: number;
  set_found: number;
  items: GrailItem[];
}

// ─── Seasons ──────────────────────────────────────────────────────────────────

export interface SeasonMilestone {
  id: number;
  season_id: number;
  name: string;
  milestone_type: "level" | "cleared_normal" | "cleared_nightmare" | "cleared_hell";
  level_target: number | null;
  reward_item_name: string | null;
  reward_item_code: string | null;
  has_reward: boolean;
  time_limit_hours: number | null;
  is_expired: boolean;
  sort_order: number;
}

export interface SeasonAchievement {
  id: number;
  season_id: number;
  milestone_id: number;
  character_name: string;
  character_class: string;
  character_level: number;
  achieved_at: string;
  claimed_at: string | null;
}

export interface SeasonDetail {
  id: number;
  name: string;
  status: "setup" | "active" | "completed";
  started_at: string | null;
  ended_at: string | null;
  scheduled_end_at: string | null;
  duration_weeks: number | null;
  notes: string | null;
  created_at: string;
  milestones: SeasonMilestone[];
  achievements: SeasonAchievement[];
}

export interface SeasonListItem {
  id: number;
  name: string;
  status: "setup" | "active" | "completed";
  started_at: string | null;
  ended_at: string | null;
  scheduled_end_at: string | null;
  duration_weeks: number | null;
  created_at: string;
  milestone_count: number;
  achievement_count: number;
}

export interface MilestoneCreateInput {
  name: string;
  milestone_type: "level" | "cleared_normal" | "cleared_nightmare" | "cleared_hell";
  level_target?: number | null;
  sort_order: number;
  reward_item_hex?: string | null;
  reward_item_name?: string | null;
  reward_item_code?: string | null;
  time_limit_hours?: number | null;
}

export interface SeasonCreateInput {
  name: string;
  notes?: string | null;
  duration_weeks?: number | null;
  milestones: MilestoneCreateInput[];
}

export interface ValidateItemResponse {
  item_name: string | null;
  item_code: string | null;
  quality: number | null;
}

export interface CharacterStatEntry {
  name: string;
  class_name: string;
  level: number;
  ever_died: boolean;
  difficulty_active: number;  // 0=Normal, 1=Nightmare, 2=Hell
}

export interface SeasonStatsResponse {
  season_id: number;
  season_name: string;
  status: string;
  started_at: string | null;
  scheduled_end_at: string | null;
  days_elapsed: number;
  highest_level_sc: number | null;
  highest_level_hc: number | null;
  characters_sc: CharacterStatEntry[];
  characters_hc: CharacterStatEntry[];
  total_gold_vault_sc: number;
  total_gold_vault_hc: number;
  grail_uniques_sc: number;
  grail_sets_sc: number;
  grail_uniques_hc: number;
  grail_sets_hc: number;
  grail_catalog_total: number;
  grail_progress_pct: number;
}

// ─── Reward Library ───────────────────────────────────────────────────────────

export interface RewardOut {
  id: number;
  name: string;
  item_code: string | null;
  item_name: string | null;
  quality: number | null;
  quality_name: string | null;
  item_level: number | null;
  is_ethereal: boolean;
  notes: string | null;
  byte_len: number;
  created_at: string;
}

export interface ValidateRewardResponse {
  item_name: string | null;
  item_code: string | null;
  quality: number | null;
  quality_name: string | null;
  item_level: number | null;
  is_ethereal: boolean | null;
  byte_len: number;
  valid: boolean;
  error: string | null;
}
