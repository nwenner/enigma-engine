import { useState } from "react";
import { useRespecCharacter } from "../api/hooks";

interface Props {
  filename: string;
  characterName: string;
  hasPendingSync?: boolean;
  onClose: () => void;
}

export default function RespecModal({ filename, characterName, hasPendingSync, onClose }: Props) {
  const [target, setTarget] = useState<"pc" | "deck" | null>(null);
  const [done, setDone] = useState(false);
  const respec = useRespecCharacter();

  const handleApply = async () => {
    if (!target) return;
    try {
      await respec.mutateAsync({ filename, target });
      setDone(true);
    } catch {
      // error displayed from respec.error below
    }
  };

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="card-d2 w-full max-w-md">
        <div className="px-4 py-3 border-b border-d2bg-border">
          <h2 className="font-diablo text-d2gold tracking-widest text-sm">
            Respec {characterName}
          </h2>
        </div>

        <div className="p-4">
          {done ? (
            <div className="text-center py-2">
              <div className="text-green-400 text-sm mb-4">
                ✓ Respec applied. Backup saved.
              </div>
              <button onClick={onClose} className="btn-d2 px-6 py-2 text-sm">
                Close
              </button>
            </div>
          ) : (
            <>
              <p className="text-slate-400 text-sm mb-4 leading-relaxed">
                All invested stat and skill points will be refunded. A backup is
                created automatically before applying.
              </p>

              <p className="text-slate-500 text-xs mb-2 uppercase tracking-wider">
                Apply to
              </p>
              <div className="flex gap-2 mb-4">
                {(["pc", "deck"] as const).map((m) => (
                  <button
                    key={m}
                    onClick={() => setTarget(m)}
                    className={`flex-1 py-2 text-sm border transition-all ${
                      target === m
                        ? "bg-d2gold/15 text-d2gold border-d2gold/50"
                        : "bg-d2bg-elevated text-slate-400 border-d2bg-border hover:border-slate-600 hover:text-slate-200"
                    }`}
                  >
                    {m === "pc" ? "PC" : "Steam Deck"}
                  </button>
                ))}
              </div>

              {hasPendingSync && (
                <div className="bg-amber-950/40 border border-amber-700/50 text-amber-300 text-xs px-3 py-2 rounded mb-3">
                  ⚠ A pending sync will be discarded when you apply this respec. Re-sync manually afterward.
                </div>
              )}

              {respec.error && (
                <div className="bg-red-950/30 border border-red-800/50 p-2 text-red-400 text-xs mb-4">
                  {(respec.error as any)?.response?.data?.detail ?? respec.error.message}
                </div>
              )}

              <div className="flex gap-2 justify-end">
                <button
                  onClick={onClose}
                  disabled={respec.isPending}
                  className="btn-d2-ghost text-sm px-4 py-2"
                >
                  Cancel
                </button>
                <button
                  onClick={handleApply}
                  disabled={!target || respec.isPending}
                  className="btn-d2 text-sm px-4 py-2"
                >
                  {respec.isPending ? "Applying…" : "Apply Respec"}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
