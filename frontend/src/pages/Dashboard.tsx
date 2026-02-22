import { useState } from "react";
import { NavLink } from "react-router-dom";
import {
  useCharacters,
  useStartSync,
  usePreflight,
  useLastSync,
  useAutoSyncStatus,
  useDismissAutoSync,
  useTriggerAutoSync,
  useBackups,
} from "../api/hooks";
import CharacterCard from "../components/CharacterCard";
import SyncStatusModal from "../components/SyncStatusModal";
import type { CharacterInfo, SnapshotResponse, SyncStatusResponse } from "../api/types";

// ─── Stale check ──────────────────────────────────────────────────────────────

const SYNC_THRESHOLD_SECONDS = 60;

function isStale(chars: CharacterInfo[], lastSync: SyncStatusResponse | null): boolean {
  if (!lastSync?.completed_at) return false;
  const syncTime = new Date(lastSync.completed_at).getTime() / 1000;
  return chars.some((c) => c.modified_at > syncTime + SYNC_THRESHOLD_SECONDS);
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function RecommendationBanner({
  chars,
  lastSync,
}: {
  chars: CharacterInfo[];
  lastSync: SyncStatusResponse | null;
}) {
  if (!lastSync?.completed_at) return null;

  if (isStale(chars, lastSync)) {
    return (
      <div className="bg-d2gold/8 border border-d2gold/30 px-4 py-3 text-d2gold text-sm mb-6 flex items-center gap-2">
        <span>⚠️</span>
        <span>Saves modified since last sync — choose a direction above</span>
      </div>
    );
  }

  return (
    <div className="bg-green-950/25 border border-green-800/40 px-4 py-3 text-green-400 text-sm mb-6 flex items-center gap-2">
      <span>✓</span>
      <span>Save files are in sync</span>
    </div>
  );
}

function AutoSyncStatusLine({
  onDismiss,
  dismissPending,
  onSyncNow,
  syncNowPending,
}: {
  onDismiss: () => void;
  dismissPending: boolean;
  onSyncNow: () => void;
  syncNowPending: boolean;
}) {
  const { data: autosync } = useAutoSyncStatus();

  if (!autosync?.enabled) return null;

  const state = autosync.state;

  if (!state || state.status === "idle") {
    return (
      <p className="text-slate-600 text-xs mt-3 text-center tracking-wide">
        Auto-sync: monitoring
      </p>
    );
  }

  if (state.status === "pending") {
    const source = state.direction === "pc_to_deck" ? "PC" : "Steam Deck";
    const dest = state.direction === "pc_to_deck" ? "Steam Deck" : "PC";
    const count = state.staged_file_count;
    const hasStaged = !!state.staged_path;

    return (
      <div className="mt-4 bg-d2bg-elevated border border-d2gold/25 p-4 animate-fadeIn">
        <div className="flex items-start gap-3 mb-4">
          <span className="text-d2gold text-lg leading-none mt-0.5">⏳</span>
          <div>
            <p className="text-d2gold font-semibold text-sm tracking-wide">Auto-sync pending</p>
            {hasStaged ? (
              <p className="text-slate-400 text-xs mt-1 leading-relaxed">
                {count} save{count === 1 ? "" : "s"} captured from {source} and held locally —
                will push to {dest} automatically when it comes online.
              </p>
            ) : (
              <p className="text-slate-400 text-xs mt-1 leading-relaxed">
                Waiting for {dest} to come online to sync {source} → {dest}.
              </p>
            )}
          </div>
        </div>
        <div className="flex gap-2 justify-end">
          <button
            onClick={onDismiss}
            disabled={dismissPending || syncNowPending}
            className="btn-d2-ghost text-xs px-3 py-1.5"
          >
            Discard
          </button>
          <button
            onClick={onSyncNow}
            disabled={syncNowPending || dismissPending}
            className="btn-d2 text-xs px-3 py-1.5"
          >
            {syncNowPending ? "Starting…" : "Sync now"}
          </button>
        </div>
      </div>
    );
  }

  if (state.status === "conflict") {
    return (
      <div className="mt-4 bg-red-950/20 border border-red-800/40 p-4 animate-fadeIn">
        <div className="flex items-start gap-3 mb-4">
          <span className="text-red-400 text-lg leading-none mt-0.5">⚠️</span>
          <div>
            <p className="text-red-400 font-semibold text-sm tracking-wide">Auto-sync conflict</p>
            <p className="text-slate-400 text-xs mt-1 leading-relaxed">
              Both machines have played since the last sync. Choose a direction manually
              using the buttons above, then dismiss this notice.
            </p>
          </div>
        </div>
        <div className="flex justify-end">
          <button
            onClick={onDismiss}
            disabled={dismissPending}
            className="btn-d2-ghost text-xs px-3 py-1.5"
          >
            Dismiss
          </button>
        </div>
      </div>
    );
  }

  return null;
}

// ─── Latest Backup ────────────────────────────────────────────────────────────

const CLASS_ICONS: Record<number, string> = {
  0: "🏹", 1: "🔥", 2: "💀", 3: "🛡️", 4: "⚔️", 5: "🌿", 6: "🗡️", 7: "🔮",
};

function relativeTime(iso: string): string {
  const ms = Date.now() - new Date(iso.endsWith("Z") ? iso : iso + "Z").getTime();
  const s = ms / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  if (s < 86400 * 7) return `${Math.floor(s / 86400)}d ago`;
  return new Date(iso.endsWith("Z") ? iso : iso + "Z").toLocaleDateString();
}

function LatestBackup({ snapshot }: { snapshot: SnapshotResponse }) {
  // snapshot.characters stores D2SCharacter.to_dict() shape (no modified_at/last_updated_at)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const chars: any[] = snapshot.characters ?? [];

  return (
    <div className="card-d2">
      <div className="px-4 py-3 border-b border-d2bg-border flex items-center justify-between">
        <h2 className="font-diablo text-d2gold text-sm tracking-widest">Latest Backup</h2>
        <NavLink
          to="/backups"
          className="text-slate-500 text-xs hover:text-d2gold transition-colors tracking-wide"
        >
          View all →
        </NavLink>
      </div>

      <div className="px-4 py-3">
        {/* Metadata row */}
        <div className="flex items-center gap-2.5 flex-wrap mb-3">
          <span className={`text-[10px] px-2 py-0.5 border tracking-wide ${
            snapshot.source_machine === "pc"
              ? "bg-violet-950/40 text-violet-400 border-violet-900/60"
              : "bg-cyan-950/40 text-cyan-400 border-cyan-900/60"
          }`}>
            {snapshot.source_machine === "pc" ? "PC" : "Steam Deck"}
          </span>
          <span className="text-slate-300 text-sm">{relativeTime(snapshot.created_at)}</span>
          <span className="text-slate-600 text-xs">·</span>
          <span className="text-slate-500 text-xs">
            {snapshot.file_count} file{snapshot.file_count !== 1 ? "s" : ""}
          </span>
        </div>

        {/* Character list */}
        {chars.length > 0 ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
            {chars.map((c, i) => (
              <div
                key={i}
                className="flex items-center gap-2 bg-d2bg-elevated border border-d2bg-border px-2.5 py-1.5"
              >
                <span className="text-sm leading-none opacity-80">
                  {CLASS_ICONS[c.class_id] ?? "🎮"}
                </span>
                <span className="text-slate-100 text-xs font-medium truncate">{c.name}</span>
                <span className="text-slate-500 text-xs ml-auto shrink-0">
                  {c.class_name} · {c.level}
                </span>
                {c.hardcore && (
                  <span className="text-[9px] bg-red-950/60 text-red-400 px-1 border border-red-900/80 shrink-0">
                    HC
                  </span>
                )}
              </div>
            ))}
          </div>
        ) : (
          <p className="text-slate-600 text-xs">No character data in this snapshot.</p>
        )}
      </div>
    </div>
  );
}

// ─── Dashboard ────────────────────────────────────────────────────────────────

type Direction = "pc_to_deck" | "deck_to_pc";

export default function Dashboard() {
  const { data: autoSyncStatus } = useAutoSyncStatus();
  const refetchMs = autoSyncStatus?.poll_interval ? autoSyncStatus.poll_interval * 1000 : undefined;

  const { data: chars, isLoading, error } = useCharacters(refetchMs);
  const { data: preflight } = usePreflight(refetchMs);
  const { data: lastSync } = useLastSync(refetchMs);
  const { data: backups } = useBackups(refetchMs);
  const startSync = useStartSync();
  const dismissAutoSync = useDismissAutoSync();
  const triggerAutoSync = useTriggerAutoSync();
  const [activeSyncId, setActiveSyncId] = useState<number | null>(null);

  const sortedChars = [...(chars ?? [])].sort((a, b) => b.modified_at - a.modified_at);

  const latestSnapshot = backups && backups.length > 0
    ? [...backups].sort(
        (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      )[0]
    : null;

  const handleSync = async (direction: Direction) => {
    const result = await startSync.mutateAsync(direction);
    setActiveSyncId(result.id);
  };

  return (
    <div className="p-4 sm:p-6 max-w-4xl mx-auto animate-fadeIn">
      {/* Header */}
      <div className="mb-7">
        <h1 className="font-diablo text-d2gold text-2xl tracking-widest">Dashboard</h1>
        <p className="text-slate-500 text-sm mt-1">Sync save files between your PC and Steam Deck</p>
      </div>

      {/* Recommendation banner */}
      <RecommendationBanner chars={chars ?? []} lastSync={lastSync ?? null} />

      {/* Sync buttons */}
      <div className="flex flex-col sm:flex-row gap-3 justify-center mb-4">
        <button
          onClick={() => handleSync("pc_to_deck")}
          disabled={startSync.isPending}
          className="btn-d2 w-full sm:w-auto"
        >
          PC → Steam Deck
        </button>
        <button
          onClick={() => handleSync("deck_to_pc")}
          disabled={startSync.isPending}
          className="btn-d2 w-full sm:w-auto"
        >
          Steam Deck → PC
        </button>
      </div>

      {/* D2R running warning */}
      {preflight && !preflight.safe_to_sync && (preflight.pc_running || preflight.deck_running) && (
        <div className="bg-red-950/30 border border-red-800/50 px-4 py-3 text-red-400 text-sm mb-4 text-center">
          ⚠️ D2R is running — close the game before syncing
        </div>
      )}

      {startSync.error && (
        <div className="bg-red-950/30 border border-red-800/50 p-3 text-red-400 text-sm mb-4">
          {startSync.error.message}
        </div>
      )}

      {/* Auto-sync status */}
      <div className="mb-6">
        <AutoSyncStatusLine
          onDismiss={() => dismissAutoSync.mutate()}
          dismissPending={dismissAutoSync.isPending}
          onSyncNow={() =>
            triggerAutoSync.mutateAsync().then((r) => setActiveSyncId(r.operation_id))
          }
          syncNowPending={triggerAutoSync.isPending}
        />
      </div>

      {/* Character list */}
      <div className="card-d2">
        <div className="px-4 py-3 border-b border-d2bg-border flex items-center gap-2">
          <h2 className="font-diablo text-d2gold text-sm tracking-widest">Characters</h2>
          <span className="text-slate-600 text-xs font-normal">({sortedChars.length})</span>
        </div>

        <div className="p-4">
          {isLoading && (
            <div className="text-slate-500 text-sm py-8 text-center">Loading characters...</div>
          )}

          {error && !isLoading && (
            <div className="text-slate-500 text-sm py-8 text-center">Could not load characters</div>
          )}

          {!isLoading && sortedChars.length === 0 && !error && (
            <div className="text-slate-500 text-sm py-8 text-center">No characters found</div>
          )}

          <div className="space-y-2">
            {sortedChars.map((c) => (
              <CharacterCard key={c.filename} character={c} />
            ))}
          </div>
        </div>
      </div>

      {/* Latest Backup */}
      {latestSnapshot && (
        <div className="mt-4">
          <LatestBackup snapshot={latestSnapshot} />
        </div>
      )}

      {activeSyncId !== null && (
        <SyncStatusModal
          syncId={activeSyncId}
          onClose={() => setActiveSyncId(null)}
        />
      )}
    </div>
  );
}
