import { useState } from "react";
import { useBackups, useDeleteBackup, useRestoreBackup } from "../api/hooks";
import ConfirmDialog from "../components/ConfirmDialog";
import type { SnapshotResponse } from "../api/types";

const fmtUtc = (s: string) => new Date(s.endsWith("Z") ? s : s + "Z").toLocaleString();

export default function Backups() {
  const { data: backups, isLoading, error, refetch } = useBackups();
  const deleteBackup = useDeleteBackup();
  const restoreBackup = useRestoreBackup();

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

  return (
    <div className="p-6 max-w-4xl mx-auto animate-fadeIn">
      <div className="flex items-center justify-between mb-7">
        <div>
          <h1 className="font-diablo text-d2gold text-2xl tracking-widest">Backups</h1>
          <p className="text-slate-500 text-sm mt-1">Automatic snapshots taken before each sync</p>
        </div>
        <button onClick={() => refetch()} className="btn-d2-ghost text-xs px-3 py-1.5">
          Refresh
        </button>
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

      {isLoading && (
        <div className="text-slate-500 text-center py-10">Loading backups...</div>
      )}

      {!isLoading && (backups ?? []).length === 0 && (
        <div className="text-slate-500 text-center py-10 text-sm">
          No backups yet — backups are created automatically before each sync
        </div>
      )}

      <div className="space-y-3">
        {(backups ?? []).map((snap) => (
          <SnapshotRow
            key={snap.id}
            snapshot={snap}
            onDelete={() => setConfirmDelete(snap.id)}
            onRestore={() => setConfirmRestore(snap.id)}
          />
        ))}
      </div>

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
        <div className="flex gap-2" onClick={(e) => e.stopPropagation()}>
          <button onClick={onRestore} className="btn-d2 text-xs px-3 py-1.5">
            Restore
          </button>
          <button onClick={onDelete} className="btn-d2-danger text-xs px-3 py-1.5">
            Delete
          </button>
        </div>
      </div>

      {expanded && chars.length > 0 && (
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
      )}
    </div>
  );
}
