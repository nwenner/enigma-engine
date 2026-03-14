import { useState } from "react";
import { NavLink } from "react-router-dom";
import {
  usePreflight,
  useActiveSeasonStats,
  useCheckIn,
  usePushToDevice,
  useSyncCompare,
  useBackups,
  useAutoSyncStatus,
  useDismissAutoSync,
  useResolveConflict,
} from "../api/hooks";
import SyncStatusModal from "../components/SyncStatusModal";
import ConfirmDialog from "../components/ConfirmDialog";
import type { SeasonStatsResponse, SyncCompareResponse } from "../api/types";
import { fmtUtc } from "../utils/dates";

// ─── Helpers ──────────────────────────────────────────────────────────────────

function fmtTimeRemaining(endIso: string): string {
  const ms = new Date(endIso).getTime() - Date.now();
  if (ms <= 0) return "Ended";
  const days = Math.floor(ms / (1000 * 60 * 60 * 24));
  const hours = Math.floor((ms % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
  if (days > 0) return `${days}d ${hours}h remaining`;
  return `${hours}h remaining`;
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
      <div className="px-4 py-3 border-b border-d2bg-border flex items-center gap-3 flex-wrap">
        <h2 className="font-diablo text-d2gold text-sm tracking-widest">{stats.season_name}</h2>
        <span className="text-[10px] px-2 py-0.5 border bg-green-950/40 text-green-400 border-green-900/60 tracking-wide">
          Active
        </span>
        <span className="text-slate-500 text-xs ml-auto">Day {stats.days_elapsed}</span>
        {stats.scheduled_end_at && (
          <span className="text-amber-400/80 text-xs">{fmtTimeRemaining(stats.scheduled_end_at)}</span>
        )}
      </div>

      <div className="grid grid-cols-3 divide-x divide-d2bg-border border-b border-d2bg-border">
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

        <div className="px-4 py-4 text-center">
          <p className="text-slate-500 text-[10px] tracking-widest uppercase mb-1">Gold Vault</p>
          <p className="text-d2gold font-diablo text-2xl leading-none">
            {fmtGold(stats.total_gold_vault_sc)}
          </p>
          <p className="text-slate-500 text-xs mt-1">SC</p>
        </div>

        <div className="px-4 py-4 text-center">
          <p className="text-slate-500 text-[10px] tracking-widest uppercase mb-1">Grail</p>
          <p className="text-d2gold font-diablo text-2xl leading-none">{stats.grail_progress_pct}%</p>
          <p className="text-slate-500 text-xs mt-1">
            {stats.grail_uniques_sc}U · {stats.grail_sets_sc}S
          </p>
        </div>
      </div>

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

// ─── Latest Snapshot ──────────────────────────────────────────────────────────

function LatestSnapshotCard() {
  const { data: backups, isLoading } = useBackups();
  const latestSnapshot = (backups ?? []).find(
    (s) => s.label === "manual" || s.label === "game_close"
  );

  return (
    <div className="card-d2 p-4 border-l-2 border-l-d2gold/40 mb-6">
      <p className="text-slate-600 text-[10px] uppercase tracking-wider mb-3">Latest Snapshot</p>
      {isLoading ? (
        <div className="text-slate-600 text-sm">Loading…</div>
      ) : latestSnapshot ? (
        <div className="flex items-center gap-3 flex-wrap">
          <span className={`text-[10px] px-2 py-0.5 border tracking-wide ${
            latestSnapshot.source_machine === "pc"
              ? "bg-violet-950/40 text-violet-400 border-violet-900/60"
              : "bg-cyan-950/40 text-cyan-400 border-cyan-900/60"
          }`}>
            {latestSnapshot.source_machine === "pc" ? "PC" : "Steam Deck"}
          </span>
          <span className="text-slate-200 text-sm font-medium">{fmtUtc(latestSnapshot.created_at)}</span>
          <span className="text-slate-500 text-xs">
            {latestSnapshot.file_count} file{latestSnapshot.file_count !== 1 ? "s" : ""}
          </span>
          {(latestSnapshot.characters ?? []).length > 0 && (
            <span className="text-slate-500 text-xs">
              · {latestSnapshot.characters!.length} character{latestSnapshot.characters!.length !== 1 ? "s" : ""}
            </span>
          )}
        </div>
      ) : (
        <p className="text-slate-600 text-sm">No snapshot yet — Check In from a device to create one</p>
      )}
    </div>
  );
}

// ─── Warning dialog helpers ───────────────────────────────────────────────────

function buildCheckInBlocker(compare: SyncCompareResponse, machine: string): string | null {
  if (!compare.pushed_since_season_start) {
    const label = machine === "pc" ? "PC" : "Steam Deck";
    return `Sync to ${label} first — the new season hasn't been pushed to this device yet. Checking in now would import pre-season saves.`;
  }
  return null;
}

function buildCheckInWarning(compare: SyncCompareResponse, machine: string): string | null {
  if (!compare.has_app_data || compare.device_older.length === 0) return null;
  const label = machine === "pc" ? "PC" : "Steam Deck";
  const files = compare.device_older.map((f) => f.filename).join(", ");
  return `${label} save files are older than the app's last snapshot: ${files}.\n\nChecking in will overwrite the app's newer data. Continue?`;
}

function buildPushWarning(compare: SyncCompareResponse, machine: string): string | null {
  if (!compare.has_app_data) return null;
  const label = machine === "pc" ? "PC" : "Steam Deck";
  const warnings: string[] = [];
  if (compare.device_newer.length > 0) {
    const files = compare.device_newer.map((f) => f.filename).join(", ");
    warnings.push(`${label} has newer saves than the app's snapshot: ${files}`);
  }
  if (compare.device_only.length > 0) {
    const files = compare.device_only.map((f) => f.filename).join(", ");
    warnings.push(`${label} has unseen characters (${files}) that will be deleted by the full mirror`);
  }
  if (warnings.length === 0) return null;
  return warnings.join("\n\n") + "\n\nSyncing will overwrite these files. Continue?";
}

// ─── Dashboard ────────────────────────────────────────────────────────────────

type ComparingKey = "checkin_pc" | "checkin_deck" | "push_pc" | "push_deck";

export default function Dashboard() {
  const { data: seasonStats, isLoading: statsLoading } = useActiveSeasonStats();
  const { data: preflight } = usePreflight();
  const { data: autosync } = useAutoSyncStatus();
  const dismissAutoSync = useDismissAutoSync();
  const resolveConflict = useResolveConflict();

  const checkIn = useCheckIn();
  const pushToDevice = usePushToDevice();
  const syncCompare = useSyncCompare();

  const [activeSyncId, setActiveSyncId] = useState<number | null>(null);
  const [comparing, setComparing] = useState<ComparingKey | null>(null);
  const [blockError, setBlockError] = useState<string | null>(null);

  // Warning dialog state (check-in or push with concerning compare result)
  const [warningDialog, setWarningDialog] = useState<{
    message: string;
    onConfirm: () => void;
  } | null>(null);

  // Push confirm dialog (overwrite device saves — always shown before push)
  const [pushConfirm, setPushConfirm] = useState<{ machine: "pc" | "deck" } | null>(null);

  const pcOnline = preflight?.pc_error === null;
  const deckOnline = preflight?.deck_error === null;

  const d2rWarning =
    preflight && !preflight.safe_to_sync && (preflight.pc_running || preflight.deck_running);

  // ── Check In flow ─────────────────────────────────────────────────────────

  const handleCheckIn = async (machine: "pc" | "deck") => {
    setBlockError(null);
    setComparing(`checkin_${machine}` as ComparingKey);
    let compare: SyncCompareResponse | null = null;
    try {
      compare = await syncCompare.mutateAsync(machine);
    } catch {
      // compare failed — proceed without guard
    }
    setComparing(null);

    if (compare) {
      const blocker = buildCheckInBlocker(compare, machine);
      if (blocker) {
        setBlockError(blocker);
        return;
      }

      const warning = buildCheckInWarning(compare, machine);
      if (warning) {
        setWarningDialog({
          message: warning,
          onConfirm: () => {
            setWarningDialog(null);
            doCheckIn(machine);
          },
        });
        return;
      }
    }

    doCheckIn(machine);
  };

  const doCheckIn = async (machine: "pc" | "deck") => {
    try {
      const result = await checkIn.mutateAsync(machine);
      setActiveSyncId(result.id);
    } catch {
      // error shown via checkIn.error
    }
  };

  // ── Push flow ─────────────────────────────────────────────────────────────

  const handlePush = async (machine: "pc" | "deck") => {
    setComparing(`push_${machine}` as ComparingKey);
    let compare: SyncCompareResponse | null = null;
    try {
      compare = await syncCompare.mutateAsync(machine);
    } catch {
      // proceed
    }
    setComparing(null);

    const warning = compare ? buildPushWarning(compare, machine) : null;
    if (warning) {
      setWarningDialog({
        message: warning,
        onConfirm: () => {
          setWarningDialog(null);
          setPushConfirm({ machine });
        },
      });
      return;
    }

    setPushConfirm({ machine });
  };

  const doPush = async (machine: "pc" | "deck") => {
    setPushConfirm(null);
    try {
      const result = await pushToDevice.mutateAsync(machine);
      setActiveSyncId(result.id);
    } catch {
      // error shown via pushToDevice.error
    }
  };

  const anyPending = checkIn.isPending || pushToDevice.isPending;
  const anyError = checkIn.error || pushToDevice.error || syncCompare.error;
  const hasActiveSeason = !statsLoading && !!seasonStats;

  return (
    <div className="p-4 sm:p-6 max-w-4xl mx-auto animate-fadeIn">
      {/* Header */}
      <div className="mb-7">
        <h1 className="font-diablo text-d2gold text-2xl tracking-widest">Dashboard</h1>
        <p className="text-slate-500 text-sm mt-1">Manage your save files</p>
      </div>

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

      {/* Season expired banner */}
      {seasonStats?.scheduled_end_at && new Date(seasonStats.scheduled_end_at) < new Date() && (
        <div className="bg-amber-950/30 border border-amber-700/50 px-4 py-3 text-amber-300 text-sm mb-2 flex items-center justify-between gap-4">
          <span>This season's time has elapsed.</span>
          <NavLink to="/seasons" className="text-amber-400 hover:underline text-xs shrink-0">
            End Season →
          </NavLink>
        </div>
      )}

      {/* Auto-sync conflict banner */}
      {autosync?.state?.status === "conflict" && (
        <div className="bg-red-900/40 border border-red-500 rounded-lg p-4 flex items-center justify-between gap-4 mb-4">
          <div>
            <span className="text-red-400 font-semibold">⚠️ Sync Conflict</span>
            <p className="text-sm text-slate-300 mt-1">
              Both PC and Steam Deck have unseen saves. Pick which to keep.
            </p>
          </div>
          <div className="flex gap-2 shrink-0">
            <button
              onClick={() => resolveConflict.mutate("pc")}
              disabled={resolveConflict.isPending}
              className="btn-d2 text-xs"
            >
              Keep PC Saves
            </button>
            <button
              onClick={() => resolveConflict.mutate("deck")}
              disabled={resolveConflict.isPending}
              className="btn-d2 text-xs"
            >
              Keep Deck Saves
            </button>
            <button
              onClick={() => dismissAutoSync.mutate()}
              disabled={dismissAutoSync.isPending}
              className="text-xs text-slate-500 hover:text-slate-300 px-2 transition-colors"
            >
              Dismiss
            </button>
          </div>
        </div>
      )}

      {/* Latest Snapshot */}
      <LatestSnapshotCard />

      {/* D2R running warning */}
      {d2rWarning && (
        <div className="bg-red-950/30 border border-red-800/50 px-4 py-3 text-red-400 text-sm mb-4 text-center">
          ⚠️ D2R is running on a device — close the game before syncing
        </div>
      )}

      {/* Error */}
      {blockError && (
        <div className="bg-red-950/30 border border-red-800/50 p-3 text-red-400 text-sm mb-4">
          {blockError}
        </div>
      )}
      {anyError && (
        <div className="bg-red-950/30 border border-red-800/50 p-3 text-red-400 text-sm mb-4">
          {(anyError as Error).message}
        </div>
      )}

      <div className="grid sm:grid-cols-2 gap-4">
        {/* Check In section */}
        <div className="card-d2 p-4">
          <h3 className="font-diablo text-d2gold text-xs tracking-widest mb-1">Seasonal Check In</h3>
          <p className="text-slate-500 text-xs mb-4">Pull saves from a device to update the app.</p>
          <div className="flex flex-col gap-2">
            <button
              onClick={() => handleCheckIn("pc")}
              disabled={anyPending || comparing !== null || !pcOnline || !hasActiveSeason}
              className="btn-d2 text-sm"
            >
              {comparing === "checkin_pc" ? "Checking…" : "📥 Check In from PC"}
            </button>
            <button
              onClick={() => handleCheckIn("deck")}
              disabled={anyPending || comparing !== null || !deckOnline || !hasActiveSeason}
              className="btn-d2 text-sm"
            >
              {comparing === "checkin_deck" ? "Checking…" : "📥 Check In from Deck"}
            </button>
          </div>
          {!hasActiveSeason && !statsLoading && (
            <p className="text-slate-600 text-xs mt-2">No active season — start one on the Seasons page</p>
          )}
          {hasActiveSeason && !pcOnline && preflight && (
            <p className="text-slate-600 text-xs mt-2">PC offline</p>
          )}
          {hasActiveSeason && !deckOnline && preflight && (
            <p className="text-slate-600 text-xs mt-1">Steam Deck offline</p>
          )}
        </div>

        {/* Sync to Device section */}
        <div className="card-d2 p-4">
          <h3 className="font-diablo text-d2gold text-xs tracking-widest mb-1">Sync to Device</h3>
          <p className="text-slate-500 text-xs mb-4">Push the latest app snapshot to a device.</p>
          <div className="flex flex-col gap-2">
            <button
              onClick={() => handlePush("pc")}
              disabled={anyPending || comparing !== null || !pcOnline || d2rWarning === true}
              className="btn-d2 text-sm"
            >
              {comparing === "push_pc" ? "Checking…" : "📤 Sync to PC"}
            </button>
            <button
              onClick={() => handlePush("deck")}
              disabled={anyPending || comparing !== null || !deckOnline || d2rWarning === true}
              className="btn-d2 text-sm"
            >
              {comparing === "push_deck" ? "Checking…" : "📤 Sync to Deck"}
            </button>
          </div>
          {!pcOnline && preflight && (
            <p className="text-slate-600 text-xs mt-2">PC offline</p>
          )}
          {!deckOnline && preflight && (
            <p className="text-slate-600 text-xs mt-1">Steam Deck offline</p>
          )}
        </div>
      </div>

      {/* Warning dialog (stale/conflict detected by compare) */}
      {warningDialog && (
        <ConfirmDialog
          title="Warning"
          message={warningDialog.message}
          confirmLabel="Continue"
          onConfirm={warningDialog.onConfirm}
          onCancel={() => setWarningDialog(null)}
        />
      )}

      {/* Push confirm dialog */}
      {pushConfirm && (
        <ConfirmDialog
          title={`Sync to ${pushConfirm.machine === "pc" ? "PC" : "Steam Deck"}`}
          message="This will delete all save files on the device and replace them with the app's latest snapshot. A backup is recommended before proceeding."
          confirmLabel="Sync"
          onConfirm={() => doPush(pushConfirm.machine)}
          onCancel={() => setPushConfirm(null)}
        />
      )}

      {/* Sync status modal */}
      {activeSyncId !== null && (
        <SyncStatusModal
          syncId={activeSyncId}
          onClose={() => setActiveSyncId(null)}
        />
      )}
    </div>
  );
}
