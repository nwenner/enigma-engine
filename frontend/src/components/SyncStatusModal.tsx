import { useSyncStatus } from "../api/hooks";
import { fmtUtcTime } from "../utils/dates";

interface Props {
  syncId: number;
  onClose: () => void;
}

function formatDirection(direction: string): string {
  switch (direction) {
    case "checkin_pc":   return "PC → Vault";
    case "checkin_deck": return "Steam Deck → Vault";
    case "app_to_pc":   return "Vault → PC";
    case "app_to_deck": return "Vault → Steam Deck";
    case "pc_to_deck":  return "PC → Steam Deck";
    case "deck_to_pc":  return "Steam Deck → PC";
    default:            return direction;
  }
}

const STATUS_LABELS: Record<string, string> = {
  pending: "Waiting to start...",
  running: "Syncing files...",
  success: "Sync complete!",
  failed: "Sync failed",
};

const STATUS_COLORS: Record<string, string> = {
  pending: "text-d2gold",
  running: "text-blue-400",
  success: "text-green-400",
  failed: "text-red-400",
};

export default function SyncStatusModal({ syncId, onClose }: Props) {
  const { data: status } = useSyncStatus(syncId, true);
  const isDone = status?.status === "success" || status?.status === "failed";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm animate-fadeIn">
      <div className="card-d2 p-6 max-w-md w-full mx-4 shadow-2xl shadow-black/60">
        <h2 className="font-diablo text-d2gold text-base tracking-wide mb-5">
          Sync Operation #{syncId}
        </h2>

        {!status && (
          <div className="flex items-center gap-3 text-slate-400">
            <Spinner />
            <span className="text-sm">Connecting...</span>
          </div>
        )}

        {status && (
          <div className="space-y-4">
            <div className="flex items-center gap-3">
              {!isDone && <Spinner />}
              {status.status === "success" && (
                <span className="text-green-400 text-lg">✓</span>
              )}
              {status.status === "failed" && (
                <span className="text-red-400 text-lg">✗</span>
              )}
              <span className={`font-semibold ${STATUS_COLORS[status.status] ?? "text-slate-300"}`}>
                {STATUS_LABELS[status.status] ?? status.status}
              </span>
            </div>

            <div className="text-sm text-slate-500 space-y-1.5 border-t border-d2bg-border pt-3">
              <div className="flex justify-between">
                <span>Direction</span>
                <span className="text-slate-300">
                  {formatDirection(status.direction)}
                </span>
              </div>
              {status.file_count > 0 && (
                <div className="flex justify-between">
                  <span>Files synced</span>
                  <span className="text-slate-300">{status.file_count}</span>
                </div>
              )}
              {status.completed_at && (
                <div className="flex justify-between">
                  <span>Completed</span>
                  <span className="text-slate-300">
                    {fmtUtcTime(status.completed_at)}
                  </span>
                </div>
              )}
            </div>

            {status.error_message && (
              <div className="bg-red-950/40 border border-red-800/60 p-3 text-red-300 text-sm">
                {status.error_message}
              </div>
            )}
          </div>
        )}

        {isDone && (
          <div className="mt-5 flex justify-end">
            <button onClick={onClose} className="btn-d2">
              Close
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function Spinner() {
  return (
    <svg
      className="animate-spin h-4 w-4 text-d2gold shrink-0"
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
    >
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  );
}
