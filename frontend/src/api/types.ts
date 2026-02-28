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
  direction: "pc_to_deck" | "deck_to_pc";
  status: "pending" | "running" | "success" | "failed";
  error_message: string | null;
  started_at: string;
  completed_at: string | null;
  file_count: number;
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
