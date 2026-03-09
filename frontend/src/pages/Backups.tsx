import { useState } from "react";
import { useBackups, useDeleteBackup, useRestoreBackup, useCreateSnapshot, usePreflight } from "../api/hooks";
import Collapsible from "../components/Collapsible";
import ConfirmDialog from "../components/ConfirmDialog";
import type { SnapshotResponse } from "../api/types";
import { fmtUtc } from "../utils/dates";

function LabelBadge({ label }: { label: string }) {
  let text: string;
  let cls: string;
  if (label === "pre_sync") {
    text = "Safety";
    cls = "bg-slate-800/60 text-slate-400 border-slate-700/60";
  } else if (label.startsWith("pre_vault")) {
    text = "Vault";
    cls = "bg-violet-950/40 text-violet-400 border-violet-900/60";
  } else {
    text = "Grail";
    cls = "bg-yellow-950/40 text-yellow-400 border-yellow-900/60";
  }
  return (
    <span className={`text-[10px] px-2 py-0.5 border tracking-wide ${cls}`}>
      {text}
    </span>
  );
}

export default function Backups() {
  const { data: backups, isLoading, error, refetch } = useBackups();
  const deleteBackup = useDeleteBackup();
  const restoreBackup = useRestoreBackup();
  const createSnapshot = useCreateSnapshot();
  const { data: preflight } = usePreflight();

  const pcOnline = preflight?.pc_error === null;
  const deckOnline = preflight?.deck_error === null;

  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);
  const [confirmRestore, setConfirmRestore] = useState<number | null>(null);
  const [toast, setToast] = useState<{ type: "success" | "error"; msg: string } | null>(null);

  const showToast = (type: "success" | "error", msg: string) => {
    setToast({ type, msg });
    setTimeout(() => setToast(null), 4000);
  };

  const handleDelete = async (id: number) => {
    setConfirmDelete(null);
    try {
      await deleteBackup.mutateAsync(id);
      showToast("success", "Backup deleted");
    } catch {
      showToast("error", "Failed to delete backup");
    }
  };

  const handleRestore = async (id: number) => {
    setConfirmRestore(null);
    try {
      const result = await restoreBackup.mutateAsync(id);
      showToast("success", result.message);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Restore failed";
      showToast("error", msg);
    }
  };

  const handleSnapshot = async (machine: "pc" | "deck") => {
    try {
      await createSnapshot.mutateAsync(machine);
      showToast("success", `${machine.toUpperCase()} snapshot created`);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Snapshot failed";
      showToast("error", msg);
    }
  };

  const snapshotPending = createSnapshot.isPending;
  const snapshotMachine = snapshotPending
    ? (createSnapshot.variables as "pc" | "deck" | undefined)
    : undefined;

  return (
    <div className="p-4 sm:p-6 max-w-4xl mx-auto animate-fadeIn">
      <div className="flex items-center justify-between mb-7">
        <div>
          <h1 className="font-diablo text-d2gold text-2xl tracking-widest">Backups</h1>
          <p className="text-slate-500 text-sm mt-1">Safety, grail, and vault backups — latest snapshot always preserved above</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => handleSnapshot("pc")}
            disabled={snapshotPending || !pcOnline}
            title={!pcOnline ? "PC is offline" : undefined}
            className="btn-d2-ghost text-xs px-3 py-1.5"
          >
            {snapshotMachine === "pc" ? "Snapshotting…" : "Snapshot PC"}
          </button>
          <button
            onClick={() => handleSnapshot("deck")}
            disabled={snapshotPending || !deckOnline}
            title={!deckOnline ? "Steam Deck is offline" : undefined}
            className="btn-d2-ghost text-xs px-3 py-1.5"
          >
            {snapshotMachine === "deck" ? "Snapshotting…" : "Snapshot Deck"}
          </button>
          <button onClick={() => refetch()} className="btn-d2-ghost text-xs px-3 py-1.5">
            Refresh
          </button>
        </div>
      </div>

      {toast && (
        <div
          className={`mb-5 p-3 border text-sm animate-fadeIn ${
            toast.type === "success"
              ? "bg-green-950/30 border-green-800/50 text-green-400"
              : "bg-red-950/30 border-red-800/50 text-red-400"
          }`}
        >
          {toast.msg}
        </div>
      )}

      {error && (
        <div className="bg-red-950/30 border border-red-800/50 p-3 text-red-400 text-sm mb-5">
          Error loading backups
        </div>
      )}

      {(() => {
        const allBackups = backups ?? [];
        const latestSnapshot = allBackups.find(
          (s) => s.label === "manual" || s.label === "game_close"
        );
        const regularBackups = allBackups.filter(
          (s) => s.label !== "manual" && s.label !== "game_close"
        );

        return (
          <>
            {/* Latest Snapshot - pinned */}
            <div className="card-d2 p-4 border-l-2 border-l-d2gold/40 mb-6">
              <p className="text-slate-600 text-[10px] uppercase tracking-wider mb-3">Latest Snapshot</p>
              {isLoading ? (
                <div className="text-slate-600 text-sm">Loading...</div>
              ) : latestSnapshot ? (
                <div className="flex items-center gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2.5 flex-wrap">
                      <span className={`text-[10px] px-2 py-0.5 border tracking-wide ${
                        latestSnapshot.source_machine === "pc"
                          ? "bg-violet-950/40 text-violet-400 border-violet-900/60"
                          : "bg-cyan-950/40 text-cyan-400 border-cyan-900/60"
                      }`}>
                        {latestSnapshot.source_machine === "pc" ? "PC" : "Steam Deck"}
                      </span>
                      <span className="text-slate-200 text-sm font-medium">{fmtUtc(latestSnapshot.created_at)}</span>
                      <span className="text-slate-500 text-xs">
                        {latestSnapshot.file_count} file{latestSnapshot.file_count !== 1 ? "s" : ""}
                      </span>
                      {(latestSnapshot.characters ?? []).length > 0 && (
                        <span className="text-slate-500 text-xs">
                          · {latestSnapshot.characters!.length} character{latestSnapshot.characters!.length !== 1 ? "s" : ""}
                        </span>
                      )}
                    </div>
                  </div>
                  <button
                    onClick={() => setConfirmRestore(latestSnapshot.id)}
                    className="btn-d2 text-xs px-3 py-1.5 shrink-0"
                  >
                    Restore
                  </button>
                </div>
              ) : (
                <p className="text-slate-600 text-sm">
                  No snapshot yet — take a manual snapshot or wait for auto-sync
                </p>
              )}
            </div>

            {/* Safety / Grail / Vault backups */}
            {!isLoading && regularBackups.length === 0 && (
              <div className="text-slate-500 text-center py-10 text-sm">
                No safety backups yet — created automatically before each sync
              </div>
            )}

            <div className="space-y-3">
              {regularBackups.map((snap) => (
                <SnapshotRow
                  key={snap.id}
                  snapshot={snap}
                  onDelete={() => setConfirmDelete(snap.id)}
                  onRestore={() => setConfirmRestore(snap.id)}
                />
              ))}
            </div>
          </>
        );
      })()}

      {confirmDelete !== null && (
        <ConfirmDialog
          title="Delete Backup"
          message="This will permanently delete the backup files from disk. This cannot be undone."
          confirmLabel="Delete"
          danger
          onConfirm={() => handleDelete(confirmDelete)}
          onCancel={() => setConfirmDelete(null)}
        />
      )}

      {confirmRestore !== null && (
        <ConfirmDialog
          title="Restore Backup"
          message="This will overwrite the current save files on the machine with files from this backup. Make sure D2R is not running."
          confirmLabel="Restore"
          onConfirm={() => handleRestore(confirmRestore)}
          onCancel={() => setConfirmRestore(null)}
        />
      )}
    </div>
  );
}

interface RowProps {
  snapshot: SnapshotResponse;
  onDelete: () => void;
  onRestore: () => void;
}

function SnapshotRow({ snapshot, onDelete, onRestore }: RowProps) {
  const [expanded, setExpanded] = useState(false);
  const chars = snapshot.characters ?? [];

  return (
    <div className="card-d2 overflow-hidden transition-all duration-200">
      <div
        className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-d2bg-elevated/40 transition-colors"
        onClick={() => setExpanded((v) => !v)}
      >
        <span className="text-slate-600 text-xs w-4 transition-transform duration-200" style={{ display: "inline-block", transform: expanded ? "rotate(90deg)" : "none" }}>
          ▶
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2.5 flex-wrap">
            <span className={`text-[10px] px-2 py-0.5 border tracking-wide ${
              snapshot.source_machine === "pc"
                ? "bg-violet-950/40 text-violet-400 border-violet-900/60"
                : "bg-cyan-950/40 text-cyan-400 border-cyan-900/60"
            }`}>
              {snapshot.source_machine === "pc" ? "PC" : "Steam Deck"}
            </span>
            <LabelBadge label={snapshot.label} />
            <span className="text-slate-200 text-sm font-medium">
              {fmtUtc(snapshot.created_at)}
            </span>
            <span className="text-slate-500 text-xs">
              {snapshot.file_count} file{snapshot.file_count !== 1 ? "s" : ""}
            </span>
            {chars.length > 0 && (
              <span className="text-slate-500 text-xs">
                · {chars.length} character{chars.length !== 1 ? "s" : ""}
              </span>
            )}
          </div>
        </div>
        <div className="flex gap-2 shrink-0" onClick={(e) => e.stopPropagation()}>
          <button onClick={onRestore} className="btn-d2 text-xs px-3 py-1.5">
            Restore
          </button>
          <button onClick={onDelete} className="btn-d2-danger text-xs px-3 py-1.5">
            Delete
          </button>
        </div>
      </div>

      <Collapsible open={expanded && chars.length > 0}>
        <div className="border-t border-d2bg-border px-4 py-3 bg-d2bg/40">
          <p className="text-slate-600 text-xs mb-2 uppercase tracking-wider">Characters in snapshot</p>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
            {chars.map((c, i) => (
              <div
                key={i}
                className="bg-d2bg-elevated border border-d2bg-border px-2.5 py-1.5 text-xs"
              >
                <span className="text-slate-100 font-medium">{c.name}</span>
                <span className="text-slate-500 ml-1.5">
                  {c.class_name} {c.level}
                </span>
              </div>
            ))}
          </div>
        </div>
      </Collapsible>
    </div>
  );
}
