import { useState } from "react";
import {
  useCharacters,
  useStartSync,
  usePreflight,
  useLastSync,
  useAutoSyncStatus,
  useDismissAutoSync,
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
  const syncTime = new Date(lastSync.completed_at).getTime() / 1000;
  const d2s = chars.filter((c) => c.filename.endsWith(".d2s"));
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
}: {
  onDismiss: () => void;
  dismissPending: boolean;
}) {
  const { data: autosync } = useAutoSyncStatus();

  if (!autosync?.enabled) return null;

  const state = autosync.state;

  if (!state || state.status === "idle") {
    return (
      <p className="text-amber-800 text-xs mt-3">Auto-sync: monitoring</p>
    );
  }

  if (state.status === "pending") {
    const dest = state.direction === "pc_to_deck" ? "Steam Deck" : "PC";
    return (
      <div className="mt-3 flex items-center gap-3 text-xs text-amber-600">
        <span>
          Auto-sync: pending {state.direction?.replace("_to_", " → ")}, waiting for{" "}
          {dest} to come online
        </span>
        <button
          onClick={onDismiss}
          disabled={dismissPending}
          className="text-amber-400 underline hover:text-amber-300 disabled:opacity-50"
        >
          Dismiss
        </button>
      </div>
    );
  }

  if (state.status === "conflict") {
    return (
      <div className="mt-3 flex items-center gap-3 text-xs text-red-400">
        <span>
          ⚠️ Auto-sync paused: both machines have unseen progress — choose a direction
          manually
        </span>
        <button
          onClick={onDismiss}
          disabled={dismissPending}
          className="text-amber-400 underline hover:text-amber-300 disabled:opacity-50"
        >
          Dismiss
        </button>
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

      {/* Auto-sync status line */}
      <div className="text-center mb-6">
        <AutoSyncStatusLine
          onDismiss={() => dismissAutoSync.mutate()}
          dismissPending={dismissAutoSync.isPending}
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
