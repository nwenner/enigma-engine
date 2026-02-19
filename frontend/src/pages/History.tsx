import { useState } from "react";
import { useHistory } from "../api/hooks";
import type { SyncOperationResponse } from "../api/types";

// Backend stores naive UTC datetimes; append Z so JS parses them as UTC
// before toLocaleString() converts to the browser's local timezone.
const fmtUtc = (s: string) => new Date(s.endsWith("Z") ? s : s + "Z").toLocaleString();

const STATUS_STYLES: Record<string, string> = {
  success: "bg-green-900/40 text-green-300 border-green-800",
  failed: "bg-red-900/40 text-red-300 border-red-800",
  running: "bg-blue-900/40 text-blue-300 border-blue-800",
  pending: "bg-amber-900/40 text-amber-300 border-amber-800",
};

export default function History() {
  const [page, setPage] = useState(1);
  const { data, isLoading, error } = useHistory(page);

  const totalPages = data ? Math.ceil(data.total / data.page_size) : 0;

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <h1 className="text-2xl font-bold text-d2gold mb-6">Sync History</h1>

      {error && (
        <div className="bg-red-950/50 border border-red-800 rounded p-3 text-red-300 text-sm mb-4">
          Error loading history
        </div>
      )}

      {isLoading && (
        <div className="text-amber-700 text-center py-8">Loading history...</div>
      )}

      {!isLoading && (data?.items ?? []).length === 0 && (
        <div className="text-amber-700 text-center py-8">No sync history yet</div>
      )}

      <div className="space-y-3">
        {(data?.items ?? []).map((op) => (
          <OperationRow key={op.id} operation={op} />
        ))}
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2 mt-6">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
            className="px-3 py-1.5 text-sm border border-d2bg-border rounded text-amber-400 hover:bg-d2bg-elevated disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            ← Prev
          </button>
          <span className="text-amber-600 text-sm">
            Page {page} of {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
            className="px-3 py-1.5 text-sm border border-d2bg-border rounded text-amber-400 hover:bg-d2bg-elevated disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            Next →
          </button>
        </div>
      )}
    </div>
  );
}

function OperationRow({ operation }: { operation: SyncOperationResponse }) {
  const [expanded, setExpanded] = useState(false);
  const dirLabel =
    operation.direction === "pc_to_deck" ? "PC → Steam Deck" : "Steam Deck → PC";

  const duration =
    operation.completed_at
      ? Math.round(
          (new Date(operation.completed_at).getTime() -
            new Date(operation.started_at).getTime()) /
            1000
        )
      : null;

  return (
    <div className="bg-d2bg-surface border border-d2bg-border rounded-lg overflow-hidden">
      <div
        className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-d2bg-elevated/30 transition-colors"
        onClick={() => setExpanded((v) => !v)}
      >
        <span className="text-amber-600 text-xs w-4">{expanded ? "▼" : "▶"}</span>
        <span
          className={`text-xs px-2 py-0.5 rounded border ${
            STATUS_STYLES[operation.status] ?? STATUS_STYLES.pending
          }`}
        >
          {operation.status}
        </span>
        <span className="text-amber-300 text-sm flex-1">{dirLabel}</span>
        <span className="text-amber-700 text-xs">
          {fmtUtc(operation.started_at)}
        </span>
        {duration !== null && (
          <span className="text-amber-700 text-xs">{duration}s</span>
        )}
        <span className="text-amber-700 text-xs">
          {operation.file_count} file{operation.file_count !== 1 ? "s" : ""}
        </span>
      </div>

      {expanded && (
        <div className="border-t border-d2bg-border px-4 py-3 bg-d2bg/30 space-y-2">
          {operation.error_message && (
            <div className="bg-red-950/50 border border-red-800 rounded p-2 text-red-300 text-xs">
              {operation.error_message}
            </div>
          )}
          {operation.files.length === 0 && (
            <p className="text-amber-700 text-xs">No file records</p>
          )}
          {operation.files.map((f) => (
            <div
              key={f.id}
              className="flex items-center gap-2 text-xs bg-d2bg-elevated border border-d2bg-border rounded px-3 py-1.5"
            >
              <span className={f.success ? "text-green-400" : "text-red-400"}>
                {f.success ? "✓" : "✗"}
              </span>
              <span className="text-amber-200 font-medium flex-1">{f.filename}</span>
              {f.char_snapshot && (
                <span className="text-amber-600">
                  {(f.char_snapshot as { name?: string }).name} Lvl{" "}
                  {(f.char_snapshot as { level?: number }).level}
                </span>
              )}
              <span className="text-amber-700">
                {(f.bytes_transferred / 1024).toFixed(1)} KB
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
