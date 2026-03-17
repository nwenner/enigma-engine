import { useState } from "react";
import { NavLink } from "react-router-dom";
import {
  usePreflight,
  useActiveSeasonStats,
  useCheckIn,
  usePushToDevice,
  useSyncCompare,
  useAutoSyncStatus,
  useDismissAutoSync,
  useResolveConflict,
  useSyncSummary,
} from "../api/hooks";
import SyncStatusModal from "../components/SyncStatusModal";
import ConfirmDialog from "../components/ConfirmDialog";
import type { SeasonStatsResponse, SyncCompareResponse, SyncSummaryResponse, PreflightResponse } from "../api/types";
import { fmtRelative } from "../utils/dates";

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

function GoldCoins({ count, glow }: { count: number; glow?: boolean }) {
  if (count === 0) return null;
  return (
    <span className="inline-flex items-center gap-0.5">
      {Array.from({ length: count }).map((_, i) => (
        <span
          key={i}
          className="inline-block rounded-full shrink-0"
          style={{
            width: 11,
            height: 11,
            background: glow
              ? "radial-gradient(circle at 35% 35%, #ffe97a, #f5c518 45%, #c8901a)"
              : "radial-gradient(circle at 35% 35%, #f7e07a, #e8b820 45%, #b87e12)",
            boxShadow: glow
              ? "0 0 6px rgba(245,197,24,0.7), 0 1px 3px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,200,0.4)"
              : "0 1px 3px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,200,0.35)",
          }}
        />
      ))}
    </span>
  );
}

function goldVaultTier(gold: number): { coinCount: number; label: string; color: string; glow: boolean } {
  if (gold === 0)            return { coinCount: 0, label: "Empty",              color: "text-slate-600",  glow: false };
  if (gold < 1_000_000)      return { coinCount: 1, label: "Small Reserve",      color: "text-d2gold/70",  glow: false };
  if (gold < 10_000_000)     return { coinCount: 2, label: "Growing Treasury",   color: "text-d2gold/85",  glow: false };
  if (gold < 50_000_000)     return { coinCount: 3, label: "Major Treasury",     color: "text-d2gold",     glow: false };
  if (gold < 200_000_000)    return { coinCount: 4, label: "Treasure Hoard",     color: "text-d2gold",     glow: false };
  return                            { coinCount: 5, label: "Legendary Hoard",    color: "text-amber-300",  glow: true  };
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
          {(() => {
            const gt = goldVaultTier(stats.total_gold_vault_sc);
            return (
              <>
                <div className="flex justify-center mb-1">
                  <GoldCoins count={gt.coinCount} glow={gt.glow} />
                </div>
                <p className={`font-diablo text-2xl leading-none tabular-nums ${gt.color}`}>
                  {fmtGold(stats.total_gold_vault_sc)}
                </p>
                <p className="text-slate-600 text-[10px] tracking-wide mt-1">{gt.label}</p>
              </>
            );
          })()}
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

// ─── Sync State Panel ─────────────────────────────────────────────────────────

function ageColor(iso: string | null): string {
  if (!iso) return "text-slate-600";
  const h = (Date.now() - new Date(iso.endsWith("Z") ? iso : iso + "Z").getTime()) / 3_600_000;
  if (h < 2) return "text-green-400";
  if (h < 12) return "text-amber-400";
  return "text-red-400/80";
}

function relAge(iso: string | null): string {
  if (!iso) return "never";
  return fmtRelative(iso);
}

interface DeviceCardProps {
  machine: "pc" | "deck";
  summary: SyncSummaryResponse;
  preflight: PreflightResponse | undefined;
  hasActiveSeason: boolean;
  anyPending: boolean;
  comparing: string | null;
  autoSyncWatching: boolean;
  onCheckIn: (m: "pc" | "deck") => void;
  onPush: (m: "pc" | "deck") => void;
}

function DeviceCard({
  machine, summary, preflight, hasActiveSeason, anyPending, comparing, autoSyncWatching, onCheckIn, onPush,
}: DeviceCardProps) {
  const label = machine === "pc" ? "Windows PC" : "Steam Deck";
  const online = machine === "pc" ? preflight?.pc_error === null : preflight?.deck_error === null;
  const d2rRunning = preflight?.pc_running === true || preflight?.deck_running === true;
  const machineData = summary[machine];
  const checkinDir = `checkin_${machine}`;
  const pushDir = `push_${machine}`;

  return (
    <div className="p-4 flex flex-col gap-3">
      {/* Header */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <span className="font-diablo text-xs tracking-widest text-slate-300">{label}</span>
          {autoSyncWatching && (
            <span
              className="text-[9px] px-1 py-px border border-amber-700/60 bg-amber-950/40 text-amber-400 tracking-wide leading-none"
              title="Auto-sync is watching this machine"
            >
              AUTO
            </span>
          )}
        </div>
        {preflight ? (
          <span className={`flex items-center gap-1.5 text-[10px] ${online ? "text-green-400" : "text-slate-600"}`}>
            <span className={`w-1.5 h-1.5 rounded-full ${online ? "bg-green-400" : "bg-slate-700"}`} />
            {online ? "Online" : "Offline"}
          </span>
        ) : (
          <span className="w-1.5 h-1.5 rounded-full bg-slate-700 animate-pulse" />
        )}
      </div>

      {/* Timestamps */}
      <div className="space-y-2">
        <div>
          <p className="text-[9px] uppercase tracking-widest text-slate-600 mb-0.5">Last Check In</p>
          <p className={`text-xs font-medium tabular-nums ${ageColor(machineData.last_checkin_at)}`}>
            {relAge(machineData.last_checkin_at)}
          </p>
        </div>
        <div>
          <p className="text-[9px] uppercase tracking-widest text-slate-600 mb-0.5">Last Synced To</p>
          <p className={`text-xs font-medium tabular-nums ${ageColor(machineData.last_push_at)}`}>
            {relAge(machineData.last_push_at)}
          </p>
        </div>
      </div>

      {/* Action buttons */}
      <div className="flex flex-col gap-1.5 mt-auto pt-1">
        <button
          onClick={() => onCheckIn(machine)}
          disabled={anyPending || comparing !== null || !online || !hasActiveSeason}
          className="btn-d2 text-xs py-1.5 w-full"
        >
          {comparing === checkinDir ? "Checking…" : "↓ Check In"}
        </button>
        <button
          onClick={() => onPush(machine)}
          disabled={anyPending || comparing !== null || !online || d2rRunning === true}
          className="btn-d2-ghost text-xs py-1.5 w-full"
        >
          {comparing === pushDir ? "Checking…" : "↑ Sync To"}
        </button>
      </div>
    </div>
  );
}

interface SyncStatePanelProps {
  summary: SyncSummaryResponse | undefined;
  preflight: PreflightResponse | undefined;
  hasActiveSeason: boolean;
  anyPending: boolean;
  comparing: string | null;
  autoSyncEnabled: boolean;
  autoSyncPc: boolean;
  autoSyncDeck: boolean;
  onCheckIn: (m: "pc" | "deck") => void;
  onPush: (m: "pc" | "deck") => void;
}

function SyncStatePanel({
  summary, preflight, hasActiveSeason, anyPending, comparing,
  autoSyncEnabled, autoSyncPc, autoSyncDeck,
  onCheckIn, onPush,
}: SyncStatePanelProps) {
  const vault = summary?.vault;
  const machineLabel = vault?.source_machine === "pc" ? "PC" : vault?.source_machine === "deck" ? "Deck" : null;

  const VaultInfo = () => (
    <div className="flex flex-col items-center justify-center gap-1 py-4 px-3 text-center">
      <p className="text-[9px] uppercase tracking-widest text-slate-600 mb-1">Vault Snapshot</p>
      <span className="font-diablo text-d2gold text-sm tracking-widest">◈ VAULT</span>
      {vault?.snapshot_at ? (
        <>
          <p className={`text-xs font-medium mt-1 ${ageColor(vault.snapshot_at)}`}>
            {relAge(vault.snapshot_at)}
          </p>
          {machineLabel && (
            <p className="text-[10px] text-slate-600">from {machineLabel} · {vault.file_count} file{vault.file_count !== 1 ? "s" : ""}</p>
          )}
        </>
      ) : (
        <p className="text-[10px] text-slate-600 mt-1">No snapshot yet</p>
      )}
    </div>
  );

  if (!summary) {
    return (
      <div className="card-d2 mb-6 px-4 py-6 text-center text-slate-600 text-xs">
        Loading sync status…
      </div>
    );
  }

  const deviceProps = { summary, preflight, hasActiveSeason, anyPending, comparing, onCheckIn, onPush };

  return (
    <div className="card-d2 mb-6 overflow-hidden">
      {/* ── Auto-sync active banner ── */}
      {autoSyncEnabled && (
        <div className="flex items-center gap-2 px-4 py-2 bg-amber-950/30 border-b border-amber-800/40 flex-wrap">
          <span className="text-amber-400 text-[10px]">⚡</span>
          <span className="text-amber-300/90 text-[10px] font-medium tracking-wide">Auto-Sync Active</span>
          <div className="flex items-center gap-1.5 ml-1">
            {autoSyncPc && (
              <span className="text-[9px] px-1.5 py-px border border-amber-700/50 text-amber-500/80 tracking-wide">PC</span>
            )}
            {autoSyncDeck && (
              <span className="text-[9px] px-1.5 py-px border border-amber-700/50 text-amber-500/80 tracking-wide">DECK</span>
            )}
          </div>
          <span className="text-amber-600/70 text-[10px] ml-auto hidden sm:block">
            Manual syncs may conflict with background activity
          </span>
        </div>
      )}

      {/* ── Mobile layout (< md): vault banner + 2-col device grid ── */}
      <div className="md:hidden">
        <div className="border-b border-d2bg-border">
          <VaultInfo />
        </div>
        <div className="grid grid-cols-2 divide-x divide-d2bg-border">
          <DeviceCard machine="pc" autoSyncWatching={autoSyncEnabled && autoSyncPc} {...deviceProps} />
          <DeviceCard machine="deck" autoSyncWatching={autoSyncEnabled && autoSyncDeck} {...deviceProps} />
        </div>
      </div>

      {/* ── Desktop layout (md+): 3-col pipeline ── */}
      <div className="hidden md:grid md:grid-cols-[1fr_auto_1fr] divide-x divide-d2bg-border">
        <DeviceCard machine="pc" autoSyncWatching={autoSyncEnabled && autoSyncPc} {...deviceProps} />

        {/* Center vault column */}
        <div className="w-40 flex flex-col">
          <VaultInfo />
          {/* Connection indicators */}
          <div className="flex-1 flex flex-col items-center justify-center gap-2 pb-4 text-[9px] text-slate-700 tracking-widest">
            <span>← Check In</span>
            <div className="w-px h-6 bg-d2bg-border" />
            <span>Sync To →</span>
          </div>
        </div>

        <DeviceCard machine="deck" autoSyncWatching={autoSyncEnabled && autoSyncDeck} {...deviceProps} />
      </div>
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
  const { data: syncSummary } = useSyncSummary();
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

      {/* Sync State Panel */}
      <SyncStatePanel
        summary={syncSummary}
        preflight={preflight}
        hasActiveSeason={hasActiveSeason}
        anyPending={anyPending}
        comparing={comparing}
        autoSyncEnabled={autosync?.enabled ?? false}
        autoSyncPc={autosync?.pc_enabled ?? false}
        autoSyncDeck={autosync?.deck_enabled ?? false}
        onCheckIn={handleCheckIn}
        onPush={handlePush}
      />

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
