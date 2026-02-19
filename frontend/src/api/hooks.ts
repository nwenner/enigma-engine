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
} from "./types";

// ─── Characters ─────────────────────────────────────────────────────────────

export function useCharacters(source: "pc" | "deck" | "all" = "all") {
  return useQuery<CharacterInfo[]>({
    queryKey: ["characters", source],
    queryFn: () => api.get(`/characters?source=${source}`).then((r) => r.data),
  });
}

// ─── Sync ────────────────────────────────────────────────────────────────────

export function usePreflight() {
  return useQuery<PreflightResponse>({
    queryKey: ["preflight"],
    queryFn: () => api.get("/sync/preflight").then((r) => r.data),
    staleTime: 10_000,
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

export function useStartSync() {
  const qc = useQueryClient();
  return useMutation<SyncStatusResponse, Error, "pc_to_deck" | "deck_to_pc">({
    mutationFn: (direction) =>
      api.post("/sync", { direction }).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["preflight"] });
    },
  });
}

// ─── Backups ─────────────────────────────────────────────────────────────────

export function useBackups() {
  return useQuery<SnapshotResponse[]>({
    queryKey: ["backups"],
    queryFn: () => api.get("/backups").then((r) => r.data),
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
