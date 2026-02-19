import { useState } from "react";
import { useCharacters, useStartSync, usePreflight } from "../api/hooks";
import CharacterCard from "../components/CharacterCard";
import SyncStatusModal from "../components/SyncStatusModal";
import type { CharacterInfo } from "../api/types";

function getMachineNewest(chars: CharacterInfo[]): Map<string, "pc" | "deck" | null> {
  // For each character name, find which source has the newer file
  const byName = new Map<string, { pc?: number; deck?: number }>();

  for (const c of chars) {
    const entry = byName.get(c.name) ?? {};
    entry[c.source] = c.modified_at;
    byName.set(c.name, entry);
  }

  const result = new Map<string, "pc" | "deck" | null>();
  for (const [name, times] of byName) {
    if (times.pc !== undefined && times.deck !== undefined) {
      result.set(name, times.pc > times.deck ? "pc" : times.deck > times.pc ? "deck" : null);
    } else {
      result.set(name, null);
    }
  }
  return result;
}

export default function Dashboard() {
  const { data: allChars, isLoading, error } = useCharacters("all");
  const { data: preflight } = usePreflight();
  const startSync = useStartSync();
  const [activeSyncId, setActiveSyncId] = useState<number | null>(null);

  const pcChars = allChars?.filter((c) => c.source === "pc") ?? [];
  const deckChars = allChars?.filter((c) => c.source === "deck") ?? [];
  const newerMap = allChars ? getMachineNewest(allChars) : new Map();

  const handleSync = async (direction: "pc_to_deck" | "deck_to_pc") => {
    const result = await startSync.mutateAsync(direction);
    setActiveSyncId(result.id);
  };

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-d2gold">Dashboard</h1>
          <p className="text-amber-700 text-sm mt-0.5">Sync save files between your PC and Steam Deck</p>
        </div>

        {preflight && !preflight.safe_to_sync && (preflight.pc_running || preflight.deck_running) && (
          <div className="bg-red-950/50 border border-red-800 rounded px-3 py-2 text-red-300 text-sm">
            ⚠️ D2R is running — close the game before syncing
          </div>
        )}
      </div>

      {/* Sync buttons */}
      <div className="flex gap-3 justify-center mb-8">
        <button
          onClick={() => handleSync("pc_to_deck")}
          disabled={startSync.isPending}
          className="flex items-center gap-2 px-5 py-2.5 bg-d2gold hover:bg-d2gold-light text-d2bg font-bold rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          PC → Steam Deck
        </button>
        <button
          onClick={() => handleSync("deck_to_pc")}
          disabled={startSync.isPending}
          className="flex items-center gap-2 px-5 py-2.5 bg-d2gold hover:bg-d2gold-light text-d2bg font-bold rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Steam Deck → PC
        </button>
      </div>

      {startSync.error && (
        <div className="bg-red-950/50 border border-red-800 rounded p-3 text-red-300 text-sm mb-6">
          {startSync.error.message}
        </div>
      )}

      {/* Side-by-side panels */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <MachinePanel
          title="Windows PC"
          icon="🖥️"
          chars={pcChars}
          newerMap={newerMap}
          isLoading={isLoading}
          error={error as Error | null}
          online={preflight?.pc_error === null && preflight?.pc_error !== undefined ? true : undefined}
        />
        <MachinePanel
          title="Steam Deck"
          icon="🎮"
          chars={deckChars}
          newerMap={newerMap}
          isLoading={isLoading}
          error={error as Error | null}
          online={preflight?.deck_error === null && preflight?.deck_error !== undefined ? true : undefined}
        />
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

interface MachinePanelProps {
  title: string;
  icon: string;
  chars: CharacterInfo[];
  newerMap: Map<string, "pc" | "deck" | null>;
  isLoading: boolean;
  error: Error | null;
  online?: boolean;
}

function MachinePanel({ title, icon, chars, newerMap, isLoading, error }: MachinePanelProps) {
  return (
    <div className="bg-d2bg-surface border border-d2bg-border rounded-lg p-4">
      <h2 className="text-d2gold font-semibold text-base mb-3 flex items-center gap-2">
        <span>{icon}</span>
        {title}
        <span className="ml-auto text-amber-700 font-normal text-sm">
          {chars.length} character{chars.length !== 1 ? "s" : ""}
        </span>
      </h2>

      {isLoading && (
        <div className="text-amber-600 text-sm py-4 text-center">Loading characters...</div>
      )}

      {error && !isLoading && (
        <div className="text-amber-700 text-sm py-4 text-center">
          Could not load characters
        </div>
      )}

      {!isLoading && chars.length === 0 && !error && (
        <div className="text-amber-700 text-sm py-4 text-center">No characters found</div>
      )}

      <div className="space-y-2">
        {chars.map((c) => (
          <CharacterCard
            key={c.filename}
            character={c}
            newerOn={newerMap.get(c.name) ?? null}
          />
        ))}
      </div>
    </div>
  );
}
