import { useSyncStatus } from "../api/hooks";

interface Props {
  syncId: number;
  onClose: () => void;
}

const STATUS_LABELS: Record<string, string> = {
  pending: "Waiting to start...",
  running: "Syncing files...",
  success: "Sync complete!",
  failed: "Sync failed",
};

const STATUS_COLORS: Record<string, string> = {
  pending: "text-amber-400",
  running: "text-blue-400",
  success: "text-green-400",
  failed: "text-red-400",
};

export default function SyncStatusModal({ syncId, onClose }: Props) {
  const { data: status } = useSyncStatus(syncId, true);
  const isDone = status?.status === "success" || status?.status === "failed";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
      <div className="bg-d2bg-surface border border-d2bg-border rounded-lg p-6 max-w-md w-full mx-4 shadow-2xl">
        <h2 className="text-d2gold font-bold text-lg mb-4">Sync Operation #{syncId}</h2>

        {!status && (
          <div className="flex items-center gap-2 text-amber-400">
            <Spinner />
            <span>Connecting...</span>
          </div>
        )}

        {status && (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              {!isDone && <Spinner />}
              {status.status === "success" && <span className="text-green-400">✓</span>}
              {status.status === "failed" && <span className="text-red-400">✗</span>}
              <span className={`font-medium ${STATUS_COLORS[status.status] ?? "text-amber-300"}`}>
                {STATUS_LABELS[status.status] ?? status.status}
              </span>
            </div>

            <div className="text-sm text-amber-600 space-y-1">
              <div>
                Direction:{" "}
                <span className="text-amber-300">
                  {status.direction === "pc_to_deck" ? "PC → Steam Deck" : "Steam Deck → PC"}
                </span>
              </div>
              {status.file_count > 0 && (
                <div>
                  Files synced:{" "}
                  <span className="text-amber-300">{status.file_count}</span>
                </div>
              )}
              {status.completed_at && (
                <div>
                  Completed:{" "}
                  <span className="text-amber-300">
                    {new Date(status.completed_at).toLocaleTimeString()}
                  </span>
                </div>
              )}
            </div>

            {status.error_message && (
              <div className="bg-red-950/50 border border-red-800 rounded p-3 text-red-300 text-sm">
                {status.error_message}
              </div>
            )}
          </div>
        )}

        {isDone && (
          <div className="mt-5 flex justify-end">
            <button
              onClick={onClose}
              className="px-4 py-2 bg-d2gold hover:bg-d2gold-light text-d2bg font-bold rounded text-sm transition-colors"
            >
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
      className="animate-spin h-4 w-4 text-amber-400"
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
    >
      <circle
        className="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="4"
      />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
      />
    </svg>
  );
}
