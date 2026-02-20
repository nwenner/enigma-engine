import { useState } from "react";
import { useHistory } from "../api/hooks";
import Collapsible from "../components/Collapsible";
import type { SyncOperationResponse } from "../api/types";

const fmtUtc = (s: string) => new Date(s.endsWith("Z") ? s : s + "Z").toLocaleString();

const STATUS_STYLES: Record<string, string> = {
  success: "bg-green-950/40 text-green-400 border-green-900/60",
  failed: "bg-red-950/40 text-red-400 border-red-900/60",
  running: "bg-blue-950/40 text-blue-400 border-blue-900/60",
  pending: "bg-d2gold/10 text-d2gold border-d2gold/30",
};

export default function History() {
  const [page, setPage] = useState(1);
  const { data, isLoading, error } = useHistory(page);
  const totalPages = data ? Math.ceil(data.total / data.page_size) : 0;

  return (
    <div className="p-4 sm:p-6 max-w-5xl mx-auto animate-fadeIn">
      <div className="mb-7">
        <h1 className="font-diablo text-d2gold text-2xl tracking-widest">Sync History</h1>
      </div>

      {error && (
        <div className="bg-red-950/30 border border-red-800/50 p-3 text-red-400 text-sm mb-5">
          Error loading history
        </div>
      )}

      {isLoading && (
        <div className="text-slate-500 text-center py-10">Loading history...</div>
      )}

      {!isLoading && (data?.items ?? []).length === 0 && (
        <div className="text-slate-500 text-center py-10 text-sm">No sync history yet</div>
      )}

      <div className="space-y-2">
        {(data?.items ?? []).map((op) => (
          <OperationRow key={op.id} operation={op} />
        ))}
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-3 mt-6">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
            className="btn-d2-ghost text-xs px-3 py-1.5"
          >
            ← Prev
          </button>
          <span className="text-slate-500 text-sm tabular-nums">
            {page} / {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
            className="btn-d2-ghost text-xs px-3 py-1.5"
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
    <div className="card-d2 overflow-hidden">
      <div
        className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-d2bg-elevated/40 transition-colors"
        onClick={() => setExpanded((v) => !v)}
      >
        <span
          className="text-slate-600 text-xs w-4 transition-transform duration-200 inline-block"
          style={{ transform: expanded ? "rotate(90deg)" : "none" }}
        >
          ▶
        </span>
        <span
          className={`text-[10px] px-2 py-0.5 border tracking-wide uppercase ${
            STATUS_STYLES[operation.status] ?? STATUS_STYLES.pending
          }`}
        >
          {operation.status}
        </span>
        <span className="text-slate-200 text-sm flex-1">{dirLabel}</span>
        <span className="text-slate-500 text-xs tabular-nums hidden sm:block">
          {fmtUtc(operation.started_at)}
        </span>
        {duration !== null && (
          <span className="text-slate-600 text-xs tabular-nums">{duration}s</span>
        )}
        <span className="text-slate-600 text-xs tabular-nums">
          {operation.file_count} file{operation.file_count !== 1 ? "s" : ""}
        </span>
      </div>

      <Collapsible open={expanded}>
        <div className="border-t border-d2bg-border px-4 py-3 bg-d2bg/40 space-y-2">
          {operation.error_message && (
            <div className="bg-red-950/30 border border-red-800/50 p-2.5 text-red-400 text-xs">
              {operation.error_message}
            </div>
          )}
          {operation.files.length === 0 && (
            <p className="text-slate-600 text-xs">No file records</p>
          )}
          {operation.files.map((f) => (
            <div
              key={f.id}
              className="flex items-center gap-2.5 text-xs bg-d2bg-elevated border border-d2bg-border px-3 py-2"
            >
              <span className={f.success ? "text-green-400" : "text-red-400"}>
                {f.success ? "✓" : "✗"}
              </span>
              <span className="text-slate-100 font-medium flex-1 truncate min-w-0">{f.filename}</span>
              {f.char_snapshot && (
                <span className="text-slate-500">
                  {(f.char_snapshot as { name?: string }).name} Lvl{" "}
                  {(f.char_snapshot as { level?: number }).level}
                </span>
              )}
              <span className="text-slate-600 tabular-nums">
                {(f.bytes_transferred / 1024).toFixed(1)} KB
              </span>
            </div>
          ))}
        </div>
      </Collapsible>
    </div>
  );
}
