import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api from "./client";
import type {
  CharacterInfo,
  SyncStatusResponse,
  PreflightResponse,
  SnapshotResponse,
  HistoryResponse,
  SettingsResponse,
  TestConnectionResponse,
  MachineSettings,
  AutoSyncStatus,
  NotificationConfig,
  GrailProgress,
  StashResponse,
  VaultItemResponse,
  GoldVaultResponse,
} from "./types";

// ─── Characters ─────────────────────────────────────────────────────────────

export function useCharacters(refetchInterval?: number) {
  return useQuery<CharacterInfo[]>({
    queryKey: ["characters"],
    queryFn: () => api.get("/characters").then((r) => r.data),
    refetchInterval,
  });
}

export function useRefreshCharacters() {
  const qc = useQueryClient();
  return useMutation<CharacterInfo[], Error, void>({
    mutationFn: () => api.post("/characters/refresh").then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["characters"] }),
  });
}

// ─── Sync ────────────────────────────────────────────────────────────────────

export function usePreflight(refetchInterval?: number) {
  return useQuery<PreflightResponse>({
    queryKey: ["preflight"],
    queryFn: () => api.get("/sync/preflight").then((r) => r.data),
    staleTime: 30_000,
    refetchInterval: refetchInterval ?? 60_000,
  });
}

export function useSyncStatus(id: number | null, enabled: boolean) {
  return useQuery<SyncStatusResponse>({
    queryKey: ["sync", id],
    queryFn: () => api.get(`/sync/${id}/status`).then((r) => r.data),
    enabled: enabled && id !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === "pending" || status === "running") return 1_000;
      return false;
    },
  });
}

export function useLastSync(refetchInterval?: number) {
  return useQuery<SyncStatusResponse | null>({
    queryKey: ["sync", "last"],
    queryFn: () => api.get("/sync/last").then((r) => r.data),
    staleTime: 30_000,
    refetchInterval,
  });
}

export function useStartSync() {
  const qc = useQueryClient();
  return useMutation<SyncStatusResponse, Error, "pc_to_deck" | "deck_to_pc">({
    mutationFn: (direction) =>
      api.post("/sync", { direction }).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["preflight"] });
      qc.invalidateQueries({ queryKey: ["sync", "last"] });
      qc.invalidateQueries({ queryKey: ["autosync"] });
    },
  });
}

// ─── Backups ─────────────────────────────────────────────────────────────────

export function useBackups(refetchInterval?: number) {
  return useQuery<SnapshotResponse[]>({
    queryKey: ["backups"],
    queryFn: () => api.get("/backups").then((r) => r.data),
    refetchInterval,
  });
}

export function useDeleteBackup() {
  const qc = useQueryClient();
  return useMutation<void, Error, number>({
    mutationFn: (id) => api.delete(`/backups/${id}`).then(() => undefined),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["backups"] }),
  });
}

export function useRestoreBackup() {
  const qc = useQueryClient();
  return useMutation<{ success: boolean; message: string; files_restored: number }, Error, number>({
    mutationFn: (id) => api.post(`/backups/${id}/restore`).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["backups"] }),
  });
}

export function useCreateSnapshot() {
  const qc = useQueryClient();
  return useMutation<SnapshotResponse, Error, "pc" | "deck">({
    mutationFn: (machine) =>
      api.post("/backups/snapshot", { machine }).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["backups"] });
      qc.invalidateQueries({ queryKey: ["stash"] });
    },
  });
}

// ─── History ─────────────────────────────────────────────────────────────────

export function useHistory(page: number, pageSize = 20) {
  return useQuery<HistoryResponse>({
    queryKey: ["history", page, pageSize],
    queryFn: () =>
      api.get(`/history?page=${page}&page_size=${pageSize}`).then((r) => r.data),
  });
}

// ─── Settings ────────────────────────────────────────────────────────────────

export function useSettings() {
  return useQuery<SettingsResponse>({
    queryKey: ["settings"],
    queryFn: () => api.get("/settings").then((r) => r.data),
  });
}

export function useUpdateSettings() {
  const qc = useQueryClient();
  return useMutation<
    SettingsResponse,
    Error,
    { pc?: Partial<MachineSettings>; deck?: Partial<MachineSettings> }
  >({
    mutationFn: (body) => api.put("/settings", body).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["settings"] }),
  });
}

export function useTestConnection() {
  return useMutation<TestConnectionResponse, Error, "pc" | "deck">({
    mutationFn: (machine) =>
      api.post("/settings/test-connection", { machine }).then((r) => r.data),
  });
}

export function useUploadKey() {
  const qc = useQueryClient();
  return useMutation<
    { success: boolean; message: string },
    Error,
    { machine: "pc" | "deck"; file: File }
  >({
    mutationFn: ({ machine, file }) => {
      const form = new FormData();
      form.append("file", file);
      return api
        .post(`/settings/upload-key/${machine}`, form, {
          headers: { "Content-Type": "multipart/form-data" },
        })
        .then((r) => r.data);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["settings"] }),
  });
}

// ─── Auto-Sync ───────────────────────────────────────────────────────────────

export function useAutoSyncStatus() {
  return useQuery<AutoSyncStatus>({
    queryKey: ["autosync", "status"],
    queryFn: () => api.get("/autosync/status").then((r) => r.data),
    refetchInterval: 15_000,
  });
}

export function useDismissAutoSync() {
  const qc = useQueryClient();
  return useMutation<void, Error, void>({
    mutationFn: () => api.post("/autosync/dismiss").then(() => undefined),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["autosync"] }),
  });
}

export function useTriggerAutoSync() {
  const qc = useQueryClient();
  return useMutation<{ success: boolean; operation_id: number }, Error, void>({
    mutationFn: () => api.post("/autosync/trigger").then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["autosync"] });
      qc.invalidateQueries({ queryKey: ["sync", "last"] });
    },
  });
}

// ─── Notifications ───────────────────────────────────────────────────────────

export function useNotificationConfig() {
  return useQuery<NotificationConfig>({
    queryKey: ["notifications", "config"],
    queryFn: () => api.get("/notifications/config").then((r) => r.data),
  });
}

export function useUpdateNotificationConfig() {
  const qc = useQueryClient();
  return useMutation<NotificationConfig, Error, NotificationConfig>({
    mutationFn: (body) => api.put("/notifications/config", body).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  });
}

export function useTestNotification() {
  return useMutation<{ success: boolean; message: string }, Error, void>({
    mutationFn: () => api.post("/notifications/test").then((r) => r.data),
  });
}

export function useUpdateAutoSyncConfig() {
  const qc = useQueryClient();
  return useMutation<AutoSyncStatus, Error, { enabled: boolean; poll_interval_seconds: number }>({
    mutationFn: (body) => api.put("/autosync/config", body).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["autosync"] }),
  });
}

// ─── Holy Grail ───────────────────────────────────────────────────────────────

export function useGrailProgress(mode: "sc" | "hc") {
  return useQuery<GrailProgress>({
    queryKey: ["grail", mode],
    queryFn: () => api.get(`/grail/${mode}`).then((r) => r.data),
  });
}

export function useSeedCatalog() {
  const qc = useQueryClient();
  return useMutation<{ success: boolean; count: number }, Error, File>({
    mutationFn: (file) => {
      const form = new FormData();
      form.append("file", file);
      return api
        .post("/grail/catalog/seed", form, {
          headers: { "Content-Type": "multipart/form-data" },
        })
        .then((r) => r.data);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["grail"] });
    },
  });
}

export function useRetrieveGrailItem() {
  const qc = useQueryClient();
  return useMutation<
    { success: boolean; message: string },
    Error,
    { mode: "sc" | "hc"; catalogId: number; machine: "pc" | "deck" }
  >({
    mutationFn: ({ mode, catalogId, machine }) =>
      api
        .post(`/grail/${mode}/${catalogId}/retrieve`, { machine })
        .then((r) => r.data),
    onSuccess: (_data, { mode }) => {
      qc.invalidateQueries({ queryKey: ["grail", mode] });
    },
  });
}

export function useDepositTab5() {
  const qc = useQueryClient();
  return useMutation<
    { success: boolean; registered: string[]; skipped: string[]; errors: string[] },
    Error,
    { machine: "pc" | "deck" }
  >({
    mutationFn: ({ machine }) =>
      api.post("/grail/deposit", { machine }).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["grail"] });
    },
  });
}

export function useUnmarkGrailEntry() {
  const qc = useQueryClient();
  return useMutation<{ success: boolean }, Error, { mode: "sc" | "hc"; catalogId: number }>({
    mutationFn: ({ mode, catalogId }) =>
      api.delete(`/grail/${mode}/${catalogId}`).then((r) => r.data),
    onSuccess: (_data, { mode }) => {
      qc.invalidateQueries({ queryKey: ["grail", mode] });
    },
  });
}

export function useResetGrail() {
  const qc = useQueryClient();
  return useMutation<{ success: boolean; deleted: number }, Error, void>({
    mutationFn: () => api.post("/grail/reset").then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["grail"] });
    },
  });
}

// ─── Stash / Vault ────────────────────────────────────────────────────────────

export function useStash(mode: "sc" | "hc") {
  return useQuery<StashResponse>({
    queryKey: ["stash", mode],
    queryFn: () => api.get(`/stash?mode=${mode}`).then((r) => r.data),
    staleTime: 0,
    retry: false,
  });
}

export function useVaultItems(mode: "sc" | "hc") {
  return useQuery<VaultItemResponse[]>({
    queryKey: ["vault", "items", mode],
    queryFn: () => api.get(`/vault/items?mode=${mode}`).then((r) => r.data),
  });
}

export function useVaultGold(mode: "sc" | "hc") {
  return useQuery<GoldVaultResponse>({
    queryKey: ["vault", "gold", mode],
    queryFn: () => api.get(`/vault/gold?mode=${mode}`).then((r) => r.data),
  });
}

export function useDepositGold() {
  const qc = useQueryClient();
  return useMutation<
    { success: boolean; stash_gold: number; vault_gold: number },
    Error,
    { machine: "pc" | "deck"; mode: "sc" | "hc"; amount: number }
  >({
    mutationFn: (body) => api.post("/stash/gold/deposit", body).then((r) => r.data),
    onSuccess: (_data, { mode }) => {
      qc.invalidateQueries({ queryKey: ["vault", "gold", mode] });
    },
  });
}

export function useWithdrawGold() {
  const qc = useQueryClient();
  return useMutation<
    { success: boolean; stash_gold: number; vault_gold: number },
    Error,
    { machine: "pc" | "deck"; mode: "sc" | "hc"; amount: number }
  >({
    mutationFn: (body) => api.post("/stash/gold/withdraw", body).then((r) => r.data),
    onSuccess: (_data, { mode }) => {
      qc.invalidateQueries({ queryKey: ["vault", "gold", mode] });
    },
  });
}

export function useStoreItem() {
  const qc = useQueryClient();
  return useMutation<
    { success: boolean; name: string | null; quality: number; quality_name: string },
    Error,
    { machine: "pc" | "deck"; mode: "sc" | "hc"; tab: number; item_index: number }
  >({
    mutationFn: (body) => api.post("/stash/item/store", body).then((r) => r.data),
    onSuccess: (_data, { mode }) => {
      qc.invalidateQueries({ queryKey: ["vault", "items", mode] });
    },
  });
}

export function useRetrieveVaultItem() {
  const qc = useQueryClient();
  return useMutation<
    { success: boolean; message: string },
    Error,
    { itemId: number; machine: "pc" | "deck"; mode: "sc" | "hc" }
  >({
    mutationFn: ({ itemId, machine, mode }) =>
      api.post(`/vault/items/${itemId}/retrieve`, { machine, mode }).then((r) => r.data),
    onSuccess: (_data, { mode }) => {
      qc.invalidateQueries({ queryKey: ["vault", "items", mode] });
    },
  });
}
