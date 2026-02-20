import { useState } from "react";
import {
  useCharacters,
  useStartSync,
  usePreflight,
  useLastSync,
  useAutoSyncStatus,
  useDismissAutoSync,
  useTriggerAutoSync,
} from "../api/hooks";
import CharacterCard from "../components/CharacterCard";
import SyncStatusModal from "../components/SyncStatusModal";
import type { CharacterInfo, SyncStatusResponse } from "../api/types";

// ─── Recommendation logic ─────────────────────────────────────────────────────

const SYNC_THRESHOLD_SECONDS = 60;

type Direction = "pc_to_deck" | "deck_to_pc";
type Recommendation = Direction | "in_sync" | null;

function computeRecommendation(
  chars: CharacterInfo[],
  lastSync: SyncStatusResponse | null
): Recommendation {
  if (!lastSync?.completed_at) return null;
  const d2s = chars.filter((c) => c.filename.endsWith(".d2s"));
  const hasPc = d2s.some((c) => c.source === "pc");
  const hasDeck = d2s.some((c) => c.source === "deck");
  if (!hasPc || !hasDeck) return null;
  const syncTime = new Date(lastSync.completed_at).getTime() / 1000;
  const pcNewer = d2s.some(
    (c) => c.source === "pc" && c.modified_at > syncTime + SYNC_THRESHOLD_SECONDS
  );
  const deckNewer = d2s.some(
    (c) => c.source === "deck" && c.modified_at > syncTime + SYNC_THRESHOLD_SECONDS
  );
  if (deckNewer && !pcNewer) return "deck_to_pc";
  if (pcNewer && !deckNewer) return "pc_to_deck";
  if (deckNewer && pcNewer) return null;
  return "in_sync";
}

// ─── Deduplication ────────────────────────────────────────────────────────────

function deduplicateChars(chars: CharacterInfo[]): {
  unified: CharacterInfo[];
  newerMap: Map<string, "pc" | "deck" | null>;
} {
  const byName = new Map<string, { pc?: CharacterInfo; deck?: CharacterInfo }>();

  for (const c of chars) {
    const entry = byName.get(c.name) ?? {};
    entry[c.source] = c;
    byName.set(c.name, entry);
  }

  const unified: CharacterInfo[] = [];
  const newerMap = new Map<string, "pc" | "deck" | null>();

  for (const [name, entries] of byName) {
    if (entries.pc && entries.deck) {
      const winner =
        entries.pc.modified_at >= entries.deck.modified_at ? entries.pc : entries.deck;
      unified.push(winner);
      if (entries.pc.modified_at === entries.deck.modified_at) {
        newerMap.set(name, null);
      } else {
        newerMap.set(name, entries.pc.modified_at > entries.deck.modified_at ? "pc" : "deck");
      }
    } else {
      const only = (entries.pc ?? entries.deck)!;
      unified.push(only);
      newerMap.set(name, null);
    }
  }

  unified.sort((a, b) => b.modified_at - a.modified_at);
  return { unified, newerMap };
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function RecommendationBanner({ rec }: { rec: Recommendation }) {
  if (rec === "in_sync") {
    return (
      <div className="bg-green-950/25 border border-green-800/40 px-4 py-3 text-green-400 text-sm mb-6 flex items-center gap-2">
        <span>✓</span>
        <span>Save files are in sync</span>
      </div>
    );
  }
  if (rec === "deck_to_pc") {
    return (
      <div className="bg-d2gold/8 border border-d2gold/30 px-4 py-3 text-d2gold text-sm mb-6 flex items-center gap-2">
        <span>🎮</span>
        <span>Steam Deck has newer saves — sync Deck → PC</span>
      </div>
    );
  }
  if (rec === "pc_to_deck") {
    return (
      <div className="bg-d2gold/8 border border-d2gold/30 px-4 py-3 text-d2gold text-sm mb-6 flex items-center gap-2">
        <span>🖥️</span>
        <span>PC has newer saves — sync PC → Steam Deck</span>
      </div>
    );
  }
  return null;
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

// ─── Dashboard ────────────────────────────────────────────────────────────────

export default function Dashboard() {
  const { data: allChars, isLoading, error } = useCharacters("all");
  const { data: preflight } = usePreflight();
  const { data: lastSync } = useLastSync();
  const startSync = useStartSync();
  const dismissAutoSync = useDismissAutoSync();
  const triggerAutoSync = useTriggerAutoSync();
  const [activeSyncId, setActiveSyncId] = useState<number | null>(null);

  const { unified, newerMap } = allChars
    ? deduplicateChars(allChars)
    : { unified: [], newerMap: new Map<string, "pc" | "deck" | null>() };

  const rec = allChars ? computeRecommendation(allChars, lastSync ?? null) : null;

  const handleSync = async (direction: Direction) => {
    const result = await startSync.mutateAsync(direction);
    setActiveSyncId(result.id);
  };

  const isRecommended = (direction: Direction) => rec === direction;

  return (
    <div className="p-6 max-w-4xl mx-auto animate-fadeIn">
      {/* Header */}
      <div className="mb-7">
        <h1 className="font-diablo text-d2gold text-2xl tracking-widest">Dashboard</h1>
        <p className="text-slate-500 text-sm mt-1">Sync save files between your PC and Steam Deck</p>
      </div>

      {/* Recommendation banner */}
      <RecommendationBanner rec={rec} />

      {/* Sync buttons */}
      <div className="flex gap-3 justify-center mb-4">
        <button
          onClick={() => handleSync("pc_to_deck")}
          disabled={startSync.isPending}
          className={isRecommended("pc_to_deck") ? "btn-d2-filled" : "btn-d2"}
        >
          {isRecommended("pc_to_deck") && <span>★</span>}
          PC → Steam Deck
        </button>
        <button
          onClick={() => handleSync("deck_to_pc")}
          disabled={startSync.isPending}
          className={isRecommended("deck_to_pc") ? "btn-d2-filled" : "btn-d2"}
        >
          {isRecommended("deck_to_pc") && <span>★</span>}
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

      {/* Unified character list */}
      <div className="card-d2">
        <div className="px-4 py-3 border-b border-d2bg-border flex items-center gap-2">
          <h2 className="font-diablo text-d2gold text-sm tracking-widest">Characters</h2>
          <span className="text-slate-600 text-xs font-normal">({unified.length})</span>
        </div>

        <div className="p-4">
          {isLoading && (
            <div className="text-slate-500 text-sm py-8 text-center">Loading characters...</div>
          )}

          {error && !isLoading && (
            <div className="text-slate-500 text-sm py-8 text-center">Could not load characters</div>
          )}

          {!isLoading && unified.length === 0 && !error && (
            <div className="text-slate-500 text-sm py-8 text-center">No characters found</div>
          )}

          <div className="space-y-2">
            {unified.map((c) => (
              <CharacterCard
                key={c.name}
                character={c}
                newerOn={newerMap.get(c.name) ?? null}
              />
            ))}
          </div>
        </div>
      </div>

      {activeSyncId !== null && (
        <SyncStatusModal
          syncId={activeSyncId}
          onClose={() => setActiveSyncId(null)}
        />
      )}
    </div>
  );
}
