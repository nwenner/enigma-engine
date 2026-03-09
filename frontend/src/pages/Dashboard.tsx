import { useState } from "react";
import { NavLink } from "react-router-dom";
import {
  useStartSync,
  usePreflight,
  useLastSync,
  useAutoSyncStatus,
  useDismissAutoSync,
  useTriggerAutoSync,
  useActiveSeasonStats,
} from "../api/hooks";
import SyncStatusModal from "../components/SyncStatusModal";
import ConfirmDialog from "../components/ConfirmDialog";
import type { CharacterInfo, SeasonStatsResponse, SyncStatusResponse } from "../api/types";
import { parseUtc } from "../utils/dates";

// ─── Stale check ──────────────────────────────────────────────────────────────

const SYNC_THRESHOLD_SECONDS = 60;

function isStale(chars: CharacterInfo[], lastSync: SyncStatusResponse | null): boolean {
  if (!lastSync?.completed_at) return false;
  const syncTime = parseUtc(lastSync.completed_at).getTime() / 1000;
  return chars.some((c) => c.modified_at > syncTime + SYNC_THRESHOLD_SECONDS);
}

// ─── Auto-sync status line ────────────────────────────────────────────────────

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

// ─── Season overview ──────────────────────────────────────────────────────────

const CLASS_ICONS: Record<string, string> = {
  Amazon: "🏹", Sorceress: "🔥", Necromancer: "💀", Paladin: "🛡️",
  Barbarian: "⚔️", Druid: "🌿", Assassin: "🗡️", Warlock: "🔮",
};

const DIFF_LABEL = ["N", "NM", "Hell"];
const DIFF_COLOR = [
  "bg-slate-800 text-slate-400 border-slate-700",
  "bg-blue-950/60 text-blue-400 border-blue-900/60",
  "bg-red-950/60 text-red-400 border-red-900/60",
];

function fmtGold(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
  return n.toLocaleString();
}

function SeasonOverviewCard({ stats }: { stats: SeasonStatsResponse }) {
  const topChar = [...stats.characters_sc].sort((a, b) => b.level - a.level)[0] ?? null;

  return (
    <div className="card-d2 mb-6">
      {/* Header */}
      <div className="px-4 py-3 border-b border-d2bg-border flex items-center gap-3 flex-wrap">
        <h2 className="font-diablo text-d2gold text-sm tracking-widest">{stats.season_name}</h2>
        <span className="text-[10px] px-2 py-0.5 border bg-green-950/40 text-green-400 border-green-900/60 tracking-wide">
          Active
        </span>
        <span className="text-slate-500 text-xs ml-auto">Day {stats.days_elapsed}</span>
      </div>

      {/* Metrics row */}
      <div className="grid grid-cols-3 divide-x divide-d2bg-border border-b border-d2bg-border">
        {/* Highest Level */}
        <div className="px-4 py-4 text-center">
          <p className="text-slate-500 text-[10px] tracking-widest uppercase mb-1">Highest Level</p>
          {stats.highest_level_sc != null ? (
            <>
              <p className="text-d2gold font-diablo text-2xl leading-none">{stats.highest_level_sc}</p>
              {topChar && (
                <p className="text-slate-500 text-xs mt-1 truncate">{topChar.class_name}</p>
              )}
            </>
          ) : (
            <p className="text-slate-600 text-lg">—</p>
          )}
        </div>

        {/* Gold Vault */}
        <div className="px-4 py-4 text-center">
          <p className="text-slate-500 text-[10px] tracking-widest uppercase mb-1">Gold Vault</p>
          <p className="text-d2gold font-diablo text-2xl leading-none">
            {fmtGold(stats.total_gold_vault_sc)}
          </p>
          <p className="text-slate-500 text-xs mt-1">SC</p>
        </div>

        {/* Grail Progress */}
        <div className="px-4 py-4 text-center">
          <p className="text-slate-500 text-[10px] tracking-widest uppercase mb-1">Grail</p>
          <p className="text-d2gold font-diablo text-2xl leading-none">{stats.grail_progress_pct}%</p>
          <p className="text-slate-500 text-xs mt-1">
            {stats.grail_uniques_sc}U · {stats.grail_sets_sc}S
          </p>
        </div>
      </div>

      {/* Characters */}
      {stats.characters_sc.length > 0 && (
        <div className="px-4 py-3">
          <div className="flex flex-wrap gap-1.5">
            {[...stats.characters_sc]
              .sort((a, b) => b.level - a.level)
              .map((c) => (
                <div
                  key={c.name}
                  className="flex items-center gap-1.5 bg-d2bg-elevated border border-d2bg-border px-2.5 py-1 text-xs"
                >
                  <span className="leading-none opacity-80">{CLASS_ICONS[c.class_name] ?? "🎮"}</span>
                  <span className="text-slate-200 font-medium">{c.name}</span>
                  <span className="text-slate-500">·</span>
                  <span className="text-slate-400">{c.class_name}</span>
                  <span className="text-slate-500">·</span>
                  <span className="text-slate-300">Lv {c.level}</span>
                  {c.difficulty_active > 0 && (
                    <span className={`text-[9px] px-1 border ${DIFF_COLOR[c.difficulty_active]}`}>
                      {DIFF_LABEL[c.difficulty_active]}
                    </span>
                  )}
                  {c.ever_died && (
                    <span className="text-[9px] text-slate-600">†</span>
                  )}
                </div>
              ))}
          </div>
        </div>
      )}

      {stats.characters_sc.length === 0 && (
        <div className="px-4 py-3">
          <p className="text-slate-600 text-xs">No characters yet — start playing!</p>
        </div>
      )}
    </div>
  );
}

function NoSeasonCard() {
  return (
    <div className="card-d2 mb-6">
      <div className="px-4 py-6 text-center">
        <p className="text-slate-600 text-sm">
          No active season —{" "}
          <NavLink to="/seasons" className="text-d2gold hover:underline">
            set one up on the Seasons page
          </NavLink>
        </p>
      </div>
    </div>
  );
}

// ─── Dashboard ────────────────────────────────────────────────────────────────

type Direction = "pc_to_deck" | "deck_to_pc";

export default function Dashboard() {
  const { data: autoSyncStatus } = useAutoSyncStatus();
  const refetchMs = autoSyncStatus?.poll_interval ? autoSyncStatus.poll_interval * 1000 : undefined;

  const { data: preflight } = usePreflight(refetchMs);
  const { data: lastSync } = useLastSync(refetchMs);
  const { data: seasonStats, isLoading: statsLoading } = useActiveSeasonStats(refetchMs);

  // For stale check we need chars — use lastSync + preflight
  const startSync = useStartSync();
  const dismissAutoSync = useDismissAutoSync();
  const triggerAutoSync = useTriggerAutoSync();
  const [activeSyncId, setActiveSyncId] = useState<number | null>(null);
  const [pendingDirection, setPendingDirection] = useState<Direction | null>(null);

  const pcOnline = preflight?.pc_error === null;
  const deckOnline = preflight?.deck_error === null;
  const bothOnline = pcOnline && deckOnline;

  const offlineMessage = !preflight
    ? null
    : !pcOnline && !deckOnline
    ? "Both devices must be online to sync"
    : !pcOnline
    ? "PC is offline"
    : !deckOnline
    ? "Steam Deck is offline"
    : null;

  // Stale-save banner: if no season active, fall back to checking lastSync against an empty chars list
  const staleChars: CharacterInfo[] = [];
  const showStaleBanner = isStale(staleChars, lastSync ?? null);

  const handleSync = async (direction: Direction) => {
    setPendingDirection(null);
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

      {/* Stale save banner */}
      {showStaleBanner && lastSync?.completed_at && (
        <div className="bg-d2gold/8 border border-d2gold/30 px-4 py-3 text-d2gold text-sm mb-6 flex items-center gap-2">
          <span>⚠️</span>
          <span>Saves modified since last sync — choose a direction above</span>
        </div>
      )}

      {/* In-sync banner */}
      {!showStaleBanner && lastSync?.completed_at && (
        <div className="bg-green-950/25 border border-green-800/40 px-4 py-3 text-green-400 text-sm mb-6 flex items-center gap-2">
          <span>✓</span>
          <span>Save files are in sync</span>
        </div>
      )}

      {/* Season Overview */}
      {statsLoading ? (
        <div className="card-d2 mb-6 px-4 py-6 text-center text-slate-600 text-sm">
          Loading season…
        </div>
      ) : seasonStats ? (
        <SeasonOverviewCard stats={seasonStats} />
      ) : (
        <NoSeasonCard />
      )}

      {/* Sync buttons */}
      <div className="flex flex-col sm:flex-row gap-3 justify-center mb-4">
        <button
          onClick={() => setPendingDirection("pc_to_deck")}
          disabled={startSync.isPending || !bothOnline}
          className="btn-d2 w-full sm:w-auto"
        >
          PC → Steam Deck
        </button>
        <button
          onClick={() => setPendingDirection("deck_to_pc")}
          disabled={startSync.isPending || !bothOnline}
          className="btn-d2 w-full sm:w-auto"
        >
          Steam Deck → PC
        </button>
      </div>

      {/* Offline warning */}
      {offlineMessage && (
        <div className="bg-slate-900/60 border border-slate-700/50 px-4 py-2 text-slate-400 text-sm mb-4 text-center">
          {offlineMessage}
        </div>
      )}

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

      {pendingDirection !== null && (
        <ConfirmDialog
          title={pendingDirection === "pc_to_deck" ? "PC → Steam Deck" : "Steam Deck → PC"}
          message="A safety backup of the destination will be created before any files are overwritten. If anything goes wrong, you can restore from the Backups page."
          confirmLabel="Sync"
          onConfirm={() => handleSync(pendingDirection)}
          onCancel={() => setPendingDirection(null)}
        />
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
