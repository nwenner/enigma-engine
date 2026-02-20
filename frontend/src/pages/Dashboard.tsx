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
  // Can't determine sync status if we don't have data from both machines
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
  if (deckNewer && pcNewer) return null; // conflict — let user decide
  return "in_sync";
}

// ─── Deduplication ────────────────────────────────────────────────────────────

function deduplicateChars(chars: CharacterInfo[]): {
  unified: CharacterInfo[];
  newerMap: Map<string, "pc" | "deck" | null>;
} {
  // For each character name, pick the entry with the newer mtime
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
      // Both machines have this character
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

  // Sort: newer first
  unified.sort((a, b) => b.modified_at - a.modified_at);

  return { unified, newerMap };
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function RecommendationBanner({ rec }: { rec: Recommendation }) {
  if (rec === "in_sync") {
    return (
      <div className="bg-green-950/30 border border-green-800/50 rounded-lg px-4 py-3 text-green-300 text-sm mb-6">
        ✓ Save files are in sync
      </div>
    );
  }
  if (rec === "deck_to_pc") {
    return (
      <div className="bg-d2gold/10 border border-d2gold/40 rounded-lg px-4 py-3 text-d2gold text-sm mb-6">
        🎮 Steam Deck has newer saves — sync Deck → PC
      </div>
    );
  }
  if (rec === "pc_to_deck") {
    return (
      <div className="bg-d2gold/10 border border-d2gold/40 rounded-lg px-4 py-3 text-d2gold text-sm mb-6">
        🖥️ PC has newer saves — sync PC → Steam Deck
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
      <p className="text-amber-800 text-xs mt-3 text-center">Auto-sync: monitoring</p>
    );
  }

  if (state.status === "pending") {
    const source = state.direction === "pc_to_deck" ? "PC" : "Steam Deck";
    const dest = state.direction === "pc_to_deck" ? "Steam Deck" : "PC";
    const count = state.staged_file_count;
    const hasStaged = !!state.staged_path;

    return (
      <div className="mt-4 bg-amber-950/30 border border-amber-700/50 rounded-lg p-4 text-left">
        <div className="flex items-start gap-3 mb-3">
          <span className="text-amber-400 text-lg leading-none mt-0.5">⏳</span>
          <div>
            <p className="text-amber-300 font-semibold text-sm">Auto-sync pending</p>
            {hasStaged ? (
              <p className="text-amber-500 text-xs mt-1">
                {count} save{count === 1 ? "" : "s"} captured from {source} and held locally —
                push to {dest} automatically when it comes online, or sync now.
              </p>
            ) : (
              <p className="text-amber-500 text-xs mt-1">
                Waiting for {dest} to come online to sync {source} → {dest}.
              </p>
            )}
          </div>
        </div>
        <div className="flex gap-2 justify-end">
          <button
            onClick={onDismiss}
            disabled={dismissPending || syncNowPending}
            className="px-3 py-1.5 text-xs text-amber-700 border border-amber-800/50 rounded hover:border-amber-700 hover:text-amber-600 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Discard
          </button>
          <button
            onClick={onSyncNow}
            disabled={syncNowPending || dismissPending}
            className="px-3 py-1.5 text-xs bg-amber-700/40 text-amber-300 border border-amber-600/50 rounded hover:bg-amber-700/60 hover:text-amber-200 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {syncNowPending ? "Starting…" : "Sync now"}
          </button>
        </div>
      </div>
    );
  }

  if (state.status === "conflict") {
    return (
      <div className="mt-4 bg-red-950/30 border border-red-800/50 rounded-lg p-4 text-left">
        <div className="flex items-start gap-3 mb-3">
          <span className="text-red-400 text-lg leading-none mt-0.5">⚠️</span>
          <div>
            <p className="text-red-300 font-semibold text-sm">Auto-sync conflict</p>
            <p className="text-red-400/80 text-xs mt-1">
              Both machines have played since the last sync. Choose a direction manually
              using the buttons above, then dismiss this notice.
            </p>
          </div>
        </div>
        <div className="flex justify-end">
          <button
            onClick={onDismiss}
            disabled={dismissPending}
            className="px-3 py-1.5 text-xs text-amber-700 border border-amber-800/50 rounded hover:border-amber-700 hover:text-amber-600 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
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

  const isRecommended = (direction: Direction) =>
    rec === direction;

  const buttonClass = (direction: Direction) =>
    isRecommended(direction)
      ? "flex items-center gap-2 px-5 py-2.5 bg-d2gold hover:bg-d2gold-light text-d2bg font-bold rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
      : "flex items-center gap-2 px-5 py-2.5 border border-d2bg-border text-amber-400 hover:border-d2gold/50 hover:text-amber-300 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed";

  const buttonLabel = (direction: Direction, base: string) =>
    isRecommended(direction) ? `★ ${base}` : base;

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-d2gold">Dashboard</h1>
        <p className="text-amber-700 text-sm mt-0.5">
          Sync save files between your PC and Steam Deck
        </p>
      </div>

      {/* Recommendation banner */}
      <RecommendationBanner rec={rec} />

      {/* Sync buttons */}
      <div className="flex gap-3 justify-center mb-4">
        <button
          onClick={() => handleSync("pc_to_deck")}
          disabled={startSync.isPending}
          className={buttonClass("pc_to_deck")}
        >
          {buttonLabel("pc_to_deck", "PC → Steam Deck")}
        </button>
        <button
          onClick={() => handleSync("deck_to_pc")}
          disabled={startSync.isPending}
          className={buttonClass("deck_to_pc")}
        >
          {buttonLabel("deck_to_pc", "Steam Deck → PC")}
        </button>
      </div>

      {/* D2R running warning */}
      {preflight && !preflight.safe_to_sync && (preflight.pc_running || preflight.deck_running) && (
        <div className="bg-red-950/50 border border-red-800 rounded px-3 py-2 text-red-300 text-sm mb-4 text-center">
          ⚠️ D2R is running — close the game before syncing
        </div>
      )}

      {startSync.error && (
        <div className="bg-red-950/50 border border-red-800 rounded p-3 text-red-300 text-sm mb-4">
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
      <div className="bg-d2bg-surface border border-d2bg-border rounded-lg p-4">
        <h2 className="text-d2gold font-semibold text-base mb-3 flex items-center gap-2">
          Characters
          <span className="ml-1 text-amber-700 font-normal text-sm">
            ({unified.length})
          </span>
        </h2>

        {isLoading && (
          <div className="text-amber-600 text-sm py-6 text-center">
            Loading characters...
          </div>
        )}

        {error && !isLoading && (
          <div className="text-amber-700 text-sm py-6 text-center">
            Could not load characters
          </div>
        )}

        {!isLoading && unified.length === 0 && !error && (
          <div className="text-amber-700 text-sm py-6 text-center">
            No characters found
          </div>
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

      {activeSyncId !== null && (
        <SyncStatusModal
          syncId={activeSyncId}
          onClose={() => setActiveSyncId(null)}
        />
      )}
    </div>
  );
}
