import { useState } from "react";
import {
  useSeasons,
  useActiveSeason,
  useCreateSeason,
  useStartSeason,
  useEndSeason,
  useDeleteSeason,
  useClaimAchievement,
  useValidateRewardItem,
  useRewards,
} from "../api/hooks";
import type {
  SeasonDetail,
  SeasonListItem,
  SeasonMilestone,
  SeasonAchievement,
  MilestoneCreateInput,
} from "../api/types";

// ─── Helpers ──────────────────────────────────────────────────────────────────

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function fmtTimeLimitHours(hours: number): string {
  if (hours % (7 * 24) === 0) return `${hours / (7 * 24)} week${hours / (7 * 24) !== 1 ? "s" : ""}`;
  if (hours % 24 === 0) return `${hours / 24} day${hours / 24 !== 1 ? "s" : ""}`;
  return `${hours}h`;
}

function fmtDurationWeeks(weeks: number): string {
  if (weeks % 4 === 0) return `${weeks / 4} month${weeks / 4 !== 1 ? "s" : ""}`;
  return `${weeks} week${weeks !== 1 ? "s" : ""}`;
}

function fmtTimeRemaining(endIso: string): string {
  const ms = new Date(endIso).getTime() - Date.now();
  if (ms <= 0) return "Ended";
  const days = Math.floor(ms / (1000 * 60 * 60 * 24));
  const hours = Math.floor((ms % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
  if (days > 0) return `${days}d ${hours}h remaining`;
  return `${hours}h remaining`;
}

function milestoneTypeLabel(type: string): string {
  if (type === "cleared_normal") return "Cleared Normal";
  if (type === "cleared_nightmare") return "Cleared NM";
  if (type === "cleared_hell") return "Cleared Hell";
  if (type === "level") return "Level";
  return type;
}

// ─── Confirm Dialog ───────────────────────────────────────────────────────────

function ConfirmDialog({
  title,
  message,
  confirmLabel = "Confirm",
  dangerous = false,
  onConfirm,
  onCancel,
  loading = false,
  error,
}: {
  title: string;
  message: string;
  confirmLabel?: string;
  dangerous?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  loading?: boolean;
  error?: string | null;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
      <div className="bg-d2bg-elevated border border-d2bg-border p-6 max-w-md w-full mx-4 space-y-4">
        <h3 className="text-d2gold font-semibold text-base">{title}</h3>
        <p className="text-slate-300 text-sm whitespace-pre-line">{message}</p>
        {error && <p className="text-red-400 text-sm">{error}</p>}
        <div className="flex gap-3 justify-end">
          <button
            onClick={onCancel}
            disabled={loading}
            className="px-4 py-2 text-sm text-slate-400 hover:text-slate-200 border border-d2bg-border hover:border-slate-500 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={loading}
            className={`px-4 py-2 text-sm font-medium transition-colors ${
              dangerous
                ? "bg-red-900/40 text-red-300 border border-red-800 hover:bg-red-800/50"
                : "bg-d2gold/20 text-d2gold border border-d2gold/40 hover:bg-d2gold/30"
            } disabled:opacity-50`}
          >
            {loading ? "Working…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Milestone Row (achievement + claim) ──────────────────────────────────────

function MilestoneRow({
  ms,
  achievements,
  canClaim,
}: {
  ms: SeasonMilestone;
  achievements: SeasonAchievement[];
  canClaim: boolean;
}) {
  const claimMutation = useClaimAchievement();
  const [claimAch, setClaimAch] = useState<SeasonAchievement | null>(null);
  const [claimError, setClaimError] = useState<string | null>(null);

  const myAchs = achievements.filter((a) => a.milestone_id === ms.id);
  const unclaimedWithReward = myAchs.filter((a) => !a.claimed_at && ms.has_reward);

  const handleClaim = async (ach: SeasonAchievement) => {
    setClaimError(null);
    try {
      await claimMutation.mutateAsync(ach.id);
      setClaimAch(null);
    } catch (e: unknown) {
      setClaimError(e instanceof Error ? e.message : "Claim failed");
    }
  };

  return (
    <div className={`border bg-d2bg/40 p-4 space-y-2 ${ms.is_expired ? "border-slate-800 opacity-60" : "border-d2bg-border"}`}>
      <div className="flex items-start justify-between gap-4">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className={`text-sm font-medium ${ms.is_expired ? "text-slate-500" : "text-slate-200"}`}>
            {ms.name}
          </span>
          <span className="text-[10px] uppercase tracking-widest text-slate-500 border border-d2bg-border px-1.5 py-0.5">
            {milestoneTypeLabel(ms.milestone_type)}
            {ms.level_target ? ` ${ms.level_target}` : ""}
          </span>
          {ms.time_limit_hours !== null && (
            <span className={`text-[10px] uppercase tracking-widest px-1.5 py-0.5 border ${
              ms.is_expired
                ? "text-red-500/60 border-red-900"
                : "text-amber-400/80 border-amber-900/50"
            }`}>
              {ms.is_expired ? "Expired" : `⏱ ${fmtTimeLimitHours(ms.time_limit_hours)}`}
            </span>
          )}
          {ms.reward_item_name && (
            <span className="text-[10px] uppercase tracking-widest text-d2gold/70 border border-d2gold/30 px-1.5 py-0.5">
              🎁 {ms.reward_item_name}
            </span>
          )}
        </div>
        {canClaim && unclaimedWithReward.length > 0 && (
          <button
            onClick={() => setClaimAch(unclaimedWithReward[0])}
            className="shrink-0 px-3 py-1.5 text-xs font-medium bg-d2gold/20 text-d2gold border border-d2gold/40 hover:bg-d2gold/30 transition-colors"
          >
            Claim Reward →
          </button>
        )}
      </div>

      {myAchs.length > 0 && (
        <div className="space-y-1 pt-1">
          {myAchs.map((a) => (
            <div key={a.id} className="flex items-center gap-2 text-xs text-slate-400">
              <span className={a.claimed_at ? "text-green-400" : "text-slate-300"}>
                {a.claimed_at ? "✓" : "○"}
              </span>
              <span>{a.character_name}</span>
              <span className="text-slate-600">{a.character_class}</span>
              <span className="text-slate-600">Lvl {a.character_level}</span>
              <span className="text-slate-600">— {fmtDate(a.achieved_at)}</span>
              {a.claimed_at && (
                <span className="text-green-500/70">Claimed {fmtDate(a.claimed_at)}</span>
              )}
            </div>
          ))}
        </div>
      )}

      {myAchs.length === 0 && (
        <p className="text-slate-600 text-xs">
          {ms.is_expired ? "Time window closed — milestone can no longer be earned." : "No characters have achieved this yet."}
        </p>
      )}

      {claimAch && (
        <ConfirmDialog
          title="Claim Reward"
          message={`This will write "${ms.reward_item_name ?? ms.reward_item_code ?? "item"}" to Tab 5 of your SC stash on the first available machine. Make sure D2R is not running.`}
          confirmLabel="Claim"
          onConfirm={() => handleClaim(claimAch)}
          onCancel={() => { setClaimAch(null); setClaimError(null); }}
          loading={claimMutation.isPending}
          error={claimError}
        />
      )}
    </div>
  );
}

// ─── Active Season Card ────────────────────────────────────────────────────────

function ActiveSeasonCard({ season }: { season: SeasonDetail }) {
  const endSeason = useEndSeason();
  const [showEnd, setShowEnd] = useState(false);
  const [endError, setEndError] = useState<string | null>(null);

  const handleEnd = async () => {
    setEndError(null);
    try {
      await endSeason.mutateAsync(season.id);
      setShowEnd(false);
    } catch (e: unknown) {
      setEndError(e instanceof Error ? e.message : "Failed to end season");
    }
  };

  const isScheduledOver = season.scheduled_end_at
    ? new Date(season.scheduled_end_at) < new Date()
    : false;

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <h2 className="text-d2gold font-semibold text-lg">{season.name}</h2>
          <div className="flex flex-wrap items-center gap-3 text-xs text-slate-500">
            <span>Started {fmtDate(season.started_at)}</span>
            {season.duration_weeks !== null && season.scheduled_end_at && (
              <>
                <span className="text-slate-700">·</span>
                <span className={isScheduledOver ? "text-red-400" : "text-slate-400"}>
                  {fmtDurationWeeks(season.duration_weeks)} season
                </span>
                <span className="text-slate-700">·</span>
                {isScheduledOver ? (
                  <span className="text-red-400 font-medium">Season time elapsed — end it when ready</span>
                ) : (
                  <span className="text-amber-400/80">{fmtTimeRemaining(season.scheduled_end_at)}</span>
                )}
              </>
            )}
          </div>
        </div>
        <button
          onClick={() => setShowEnd(true)}
          disabled={endSeason.isPending || endSeason.isSuccess}
          className="shrink-0 px-3 py-1.5 text-xs text-slate-400 border border-slate-700 hover:border-red-700 hover:text-red-400 transition-colors disabled:opacity-40 disabled:cursor-not-allowed disabled:pointer-events-none"
        >
          End Season
        </button>
      </div>

      {season.notes && (
        <p className="text-slate-400 text-sm italic">{season.notes}</p>
      )}

      <div className="space-y-2">
        <h3 className="text-slate-400 text-xs uppercase tracking-widest">Milestones</h3>
        {season.milestones.length === 0 ? (
          <p className="text-slate-600 text-sm">No milestones configured.</p>
        ) : (
          season.milestones.map((ms) => (
            <MilestoneRow
              key={ms.id}
              ms={ms}
              achievements={season.achievements}
              canClaim={true}
            />
          ))
        )}
      </div>

      {showEnd && (
        <ConfirmDialog
          title="End Season"
          message={`Are you sure you want to end "${season.name}"? This marks the season as completed but does NOT wipe save files.`}
          confirmLabel="End Season"
          dangerous
          onConfirm={handleEnd}
          onCancel={() => { setShowEnd(false); setEndError(null); }}
          loading={endSeason.isPending}
          error={endError}
        />
      )}
    </div>
  );
}

// ─── Milestone Builder Row ─────────────────────────────────────────────────────

type MilestoneFormRow = {
  id: number;
  name: string;
  milestone_type: "level" | "cleared_normal" | "cleared_nightmare" | "cleared_hell";
  level_target: string;
  time_limit_days: string;
  reward_item_hex: string;
  reward_item_name: string;
  reward_library_id: number | null;  // set when picked from library
  validated: boolean;
  validating: boolean;
  validateError: string | null;
};

function MilestoneFormRowUI({
  row,
  onChange,
  onRemove,
}: {
  row: MilestoneFormRow;
  onChange: (updated: MilestoneFormRow) => void;
  onRemove: () => void;
}) {
  const validateItem = useValidateRewardItem();
  const { data: rewards } = useRewards();
  const [showLibrary, setShowLibrary] = useState(false);

  const handleValidate = async () => {
    if (!row.reward_item_hex.trim()) return;
    onChange({ ...row, validating: true, validateError: null, validated: false });
    try {
      const result = await validateItem.mutateAsync(row.reward_item_hex);
      onChange({
        ...row,
        validating: false,
        validated: true,
        validateError: null,
        reward_item_name: result.item_name ?? row.reward_item_name,
      });
    } catch (e: unknown) {
      onChange({
        ...row,
        validating: false,
        validated: false,
        validateError: e instanceof Error ? e.message : "Validation failed",
      });
    }
  };

  return (
    <div className="border border-d2bg-border bg-d2bg/30 p-3 space-y-2">
      {/* Row 1: name + type + level + remove */}
      <div className="flex items-center gap-2">
        <input
          type="text"
          placeholder="Milestone name"
          value={row.name}
          onChange={(e) => onChange({ ...row, name: e.target.value })}
          className="flex-1 bg-d2bg border border-d2bg-border text-slate-200 text-sm px-2 py-1.5 focus:outline-none focus:border-d2gold/50"
        />
        <select
          value={row.milestone_type}
          onChange={(e) => onChange({ ...row, milestone_type: e.target.value as MilestoneFormRow["milestone_type"] })}
          className="bg-d2bg border border-d2bg-border text-slate-200 text-sm px-2 py-1.5 focus:outline-none focus:border-d2gold/50"
        >
          <option value="level">Level</option>
          <option value="cleared_normal">Cleared Normal</option>
          <option value="cleared_nightmare">Cleared Nightmare</option>
          <option value="cleared_hell">Cleared Hell</option>
        </select>
        {row.milestone_type === "level" && (
          <input
            type="number"
            placeholder="Lvl"
            min={1}
            max={99}
            value={row.level_target}
            onChange={(e) => onChange({ ...row, level_target: e.target.value })}
            className="w-16 bg-d2bg border border-d2bg-border text-slate-200 text-sm px-2 py-1.5 focus:outline-none focus:border-d2gold/50"
          />
        )}
        <button
          onClick={onRemove}
          className="text-slate-600 hover:text-red-400 text-sm px-2 py-1.5"
        >
          ✕
        </button>
      </div>

      {/* Row 2: time limit */}
      <div className="flex items-center gap-2">
        <label className="text-[10px] uppercase tracking-widest text-slate-500 shrink-0">
          ⏱ Time Limit
        </label>
        <input
          type="number"
          placeholder="No limit"
          min={1}
          max={180}
          value={row.time_limit_days}
          onChange={(e) => onChange({ ...row, time_limit_days: e.target.value })}
          className="w-24 bg-d2bg border border-d2bg-border text-slate-200 text-sm px-2 py-1.5 focus:outline-none focus:border-d2gold/50"
        />
        <span className="text-xs text-slate-500">days from season start (blank = no limit)</span>
      </div>

      {/* Row 3: reward item */}
      <div className="space-y-1">
        <div className="flex items-center justify-between">
          <label className="text-[10px] uppercase tracking-widest text-slate-500">
            🎁 Reward Item (optional)
          </label>
          <button
            onClick={() => setShowLibrary((v) => !v)}
            className="text-[10px] text-d2gold/70 hover:text-d2gold transition-colors"
          >
            {showLibrary ? "▲ Hide library" : "📚 Pick from library"}
          </button>
        </div>

        {/* Library picker */}
        {showLibrary && (
          <div className="border border-d2bg-border bg-black/30 max-h-48 overflow-y-auto divide-y divide-d2bg-border/30">
            {!rewards || rewards.length === 0 ? (
              <p className="text-slate-600 text-xs px-3 py-2">
                No rewards saved. Go to <span className="text-slate-400">Reward Library</span> to add items first.
              </p>
            ) : (
              rewards.map((r) => (
                <button
                  key={r.id}
                  onClick={() => {
                    // We only have the display data here; hex is fetched on save
                    // Store the reward_library_id and name; hex will be resolved server-side
                    onChange({
                      ...row,
                      reward_item_name: r.name,
                      reward_item_hex: `[library:${r.id}]`,  // placeholder — router resolves this
                      reward_library_id: r.id,
                      validated: true,
                      validateError: null,
                    });
                    setShowLibrary(false);
                  }}
                  className={`w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-d2bg-elevated/40 transition-colors ${
                    row.reward_library_id === r.id ? "bg-d2gold/5 border-l-2 border-d2gold" : ""
                  }`}
                >
                  <span className="text-[9px] font-mono text-slate-500 border border-slate-700 px-1 shrink-0">
                    {(r.quality_name ?? "NRM").slice(0, 3).toUpperCase()}
                  </span>
                  <span className="text-sm text-slate-200 truncate">{r.name}</span>
                  {r.is_ethereal && <span className="text-[10px] text-sky-400 font-mono shrink-0">ETH</span>}
                  {r.notes && <span className="text-[10px] text-slate-600 truncate">{r.notes}</span>}
                </button>
              ))
            )}
          </div>
        )}

        {/* Manual hex paste (only show if not using library) */}
        {!row.reward_library_id && (
          <div className="flex gap-2">
            <textarea
              placeholder="or paste hex bytes: 10 0f 00 00 4a 4d ..."
              value={row.reward_item_hex}
              onChange={(e) => onChange({ ...row, reward_item_hex: e.target.value, validated: false, reward_library_id: null })}
              rows={2}
              className="flex-1 bg-d2bg border border-d2bg-border text-slate-300 text-xs font-mono px-2 py-1.5 focus:outline-none focus:border-d2gold/50 resize-none"
            />
            <button
              onClick={handleValidate}
              disabled={row.validating || !row.reward_item_hex.trim()}
              className="px-3 py-1 text-xs border border-d2bg-border text-slate-400 hover:text-slate-200 hover:border-slate-500 transition-colors disabled:opacity-40"
            >
              {row.validating ? "…" : "Validate"}
            </button>
          </div>
        )}

        {/* Selected reward display */}
        {row.reward_library_id && row.reward_item_name && (
          <div className="flex items-center gap-2 px-2 py-1.5 border border-d2gold/30 bg-d2gold/5">
            <span className="text-d2gold/80 text-xs">📚</span>
            <span className="text-d2gold text-sm font-medium flex-1">{row.reward_item_name}</span>
            <button
              onClick={() => onChange({ ...row, reward_item_hex: "", reward_item_name: "", reward_library_id: null, validated: false })}
              className="text-[10px] text-slate-600 hover:text-red-400 transition-colors"
            >
              ✕ clear
            </button>
          </div>
        )}

        {row.validated && !row.reward_library_id && row.reward_item_name && (
          <p className="text-xs text-green-400">✓ {row.reward_item_name}</p>
        )}
        {row.validateError && (
          <p className="text-xs text-red-400">{row.validateError}</p>
        )}
      </div>
    </div>
  );
}

// ─── Start Season Panel (shared) ─────────────────────────────────────────────

const START_SEASON_WARNING = `WARNING: This will:\n• Archive the latest local snapshot\n• Clear Characters, Grail, Item Vault, and Gold Vault data\n\nYour devices are NOT touched — use Sync to Device after starting to push the empty state. This cannot be undone (the archive is kept as a backup).`;

function StartSeasonPanel({
  seasonId,
  seasonName,
  durationWeeks,
  dismissButton,
}: {
  seasonId: number;
  seasonName: string;
  durationWeeks: number | null;
  dismissButton: React.ReactNode;
}) {
  const startSeason = useStartSeason();
  const [showConfirm, setShowConfirm] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  const durationNote = durationWeeks
    ? ` It will run for ${fmtDurationWeeks(durationWeeks)}.`
    : "";

  const handleStart = async () => {
    setStartError(null);
    try {
      await startSeason.mutateAsync(seasonId);
      setShowConfirm(false);
    } catch (e: unknown) {
      setStartError(e instanceof Error ? e.message : "Failed to start season");
    }
  };

  return (
    <div className="space-y-4 border border-d2gold/30 bg-d2gold/5 p-4">
      <div>
        <p className="text-d2gold font-medium">Season "{seasonName}" created in setup mode.</p>
        <p className="text-slate-400 text-sm mt-1">
          Ready to start? Starting will archive the latest local snapshot, then clear
          Characters, Grail, Item Vault, and Gold Vault data. Use Sync to Device afterwards
          to push the empty state to your machines.{durationNote}
        </p>
      </div>
      <div className="flex gap-3">
        <button
          onClick={() => { setShowConfirm(true); setStartError(null); }}
          className="px-4 py-2 text-sm font-medium bg-d2gold/20 text-d2gold border border-d2gold/40 hover:bg-d2gold/30 transition-colors"
        >
          Start Season →
        </button>
        {dismissButton}
      </div>
      {startError && <p className="text-red-400 text-xs">{startError}</p>}
      {showConfirm && (
        <ConfirmDialog
          title="Start Season"
          message={START_SEASON_WARNING}
          confirmLabel="Start Season"
          dangerous
          onConfirm={handleStart}
          onCancel={() => { setShowConfirm(false); setStartError(null); }}
          loading={startSeason.isPending}
        />
      )}
    </div>
  );
}

// ─── Create Season Panel ──────────────────────────────────────────────────────

let _msKey = 0;
function nextKey() { return ++_msKey; }

function CreateSeasonPanel() {
  const createSeason = useCreateSeason();
  const [name, setName] = useState("");
  const [notes, setNotes] = useState("");
  const [durationWeeks, setDurationWeeks] = useState("");  // "" = no limit
  const [milestones, setMilestones] = useState<MilestoneFormRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<SeasonDetail | null>(null);

  const addMilestone = () => {
    setMilestones((prev) => [
      ...prev,
      { id: nextKey(), name: "", milestone_type: "level", level_target: "50", time_limit_days: "", reward_item_hex: "", reward_item_name: "", reward_library_id: null, validated: false, validating: false, validateError: null },
    ]);
  };

  const updateMs = (id: number, updated: MilestoneFormRow) => {
    setMilestones((prev) => prev.map((m) => (m.id === id ? updated : m)));
  };

  const removeMs = (id: number) => {
    setMilestones((prev) => prev.filter((m) => m.id !== id));
  };

  const handleSave = async () => {
    if (!name.trim()) { setError("Season name is required"); return; }
    const parsedWeeks = durationWeeks.trim() ? parseInt(durationWeeks) : null;
    if (parsedWeeks !== null && (isNaN(parsedWeeks) || parsedWeeks < 1 || parsedWeeks > 26)) {
      setError("Duration must be 1–26 weeks (or leave blank for no time limit)");
      return;
    }
    setError(null);
    try {
      // Resolve library rewards — fetch hex bytes for any milestone using a library reward
      const resolvedHexes: Record<number, string> = {};
      for (const m of milestones) {
        if (m.reward_library_id && !resolvedHexes[m.reward_library_id]) {
          const resp = await fetch(`/api/rewards/${m.reward_library_id}/bytes`);
          if (!resp.ok) throw new Error(`Failed to load reward bytes for "${m.reward_item_name}"`);
          const data = await resp.json();
          resolvedHexes[m.reward_library_id] = data.hex;
        }
      }

      const msInputs: MilestoneCreateInput[] = milestones.map((m, i) => {
        const days = m.time_limit_days.trim() ? parseFloat(m.time_limit_days) : null;
        const hex = m.reward_library_id
          ? resolvedHexes[m.reward_library_id]
          : m.reward_item_hex.trim() || null;
        return {
          name: m.name,
          milestone_type: m.milestone_type,
          level_target: m.milestone_type === "level" ? parseInt(m.level_target) || null : null,
          sort_order: i,
          reward_item_hex: hex || null,
          reward_item_name: m.reward_item_name.trim() || null,
          time_limit_hours: days !== null ? Math.round(days * 24) : null,
        };
      });
      const result = await createSeason.mutateAsync({
        name: name.trim(),
        notes: notes.trim() || null,
        duration_weeks: parsedWeeks,
        milestones: msInputs,
      });
      setCreated(result);
      setName("");
      setNotes("");
      setDurationWeeks("");
      setMilestones([]);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to create season");
    }
  };

  if (created) {
    return (
      <StartSeasonPanel
        seasonId={created.id}
        seasonName={created.name}
        durationWeeks={created.duration_weeks}
        dismissButton={
          <button
            onClick={() => setCreated(null)}
            className="px-4 py-2 text-sm text-slate-400 border border-d2bg-border hover:border-slate-500 transition-colors"
          >
            Not yet
          </button>
        }
      />
    );
  }

  return (
    <div className="space-y-4 border border-d2bg-border p-4">
      <h3 className="text-slate-300 text-sm font-medium">Create New Season</h3>

      <div className="space-y-2">
        <label className="text-[10px] uppercase tracking-widest text-slate-500">Season Name</label>
        <input
          type="text"
          placeholder="Season 1: Ladder Reset"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="w-full bg-d2bg border border-d2bg-border text-slate-200 text-sm px-3 py-2 focus:outline-none focus:border-d2gold/50"
        />
      </div>

      {/* Duration */}
      <div className="space-y-2">
        <label className="text-[10px] uppercase tracking-widest text-slate-500">
          Season Duration (weeks, optional)
        </label>
        <div className="flex items-center gap-2">
          <input
            type="number"
            placeholder="No limit"
            min={1}
            max={26}
            value={durationWeeks}
            onChange={(e) => setDurationWeeks(e.target.value)}
            className="w-28 bg-d2bg border border-d2bg-border text-slate-200 text-sm px-3 py-2 focus:outline-none focus:border-d2gold/50"
          />
          <span className="text-xs text-slate-500">
            {durationWeeks.trim() && !isNaN(parseInt(durationWeeks))
              ? `= ${fmtDurationWeeks(parseInt(durationWeeks))} · 1–26 allowed`
              : "1–26 weeks (leave blank for open-ended)"}
          </span>
        </div>
      </div>

      <div className="space-y-2">
        <label className="text-[10px] uppercase tracking-widest text-slate-500">Notes (optional)</label>
        <textarea
          placeholder="Season rules, goals, etc."
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={2}
          className="w-full bg-d2bg border border-d2bg-border text-slate-300 text-sm px-3 py-2 focus:outline-none focus:border-d2gold/50 resize-none"
        />
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <label className="text-[10px] uppercase tracking-widest text-slate-500">Milestones</label>
          <button
            onClick={addMilestone}
            className="text-xs text-d2gold/70 hover:text-d2gold transition-colors"
          >
            + Add Milestone
          </button>
        </div>
        {milestones.map((m) => (
          <MilestoneFormRowUI
            key={m.id}
            row={m}
            onChange={(updated) => updateMs(m.id, updated)}
            onRemove={() => removeMs(m.id)}
          />
        ))}
        {milestones.length === 0 && (
          <p className="text-slate-600 text-xs">No milestones yet. Add time-limited milestones like "Clear Normal in 2 days" or open-ended ones like "Reach Level 90".</p>
        )}
      </div>

      {error && <p className="text-red-400 text-sm">{error}</p>}

      <button
        onClick={handleSave}
        disabled={createSeason.isPending || !name.trim()}
        className="px-4 py-2 text-sm font-medium bg-d2gold/20 text-d2gold border border-d2gold/40 hover:bg-d2gold/30 transition-colors disabled:opacity-50"
      >
        {createSeason.isPending ? "Saving…" : "Save Season"}
      </button>
    </div>
  );
}

// ─── Past Seasons ─────────────────────────────────────────────────────────────

function PastSeason({ item }: { item: SeasonListItem }) {
  const [open, setOpen] = useState(false);
  const deleteSeason = useDeleteSeason();
  const [confirmDelete, setConfirmDelete] = useState(false);

  const handleDelete = async () => {
    await deleteSeason.mutateAsync(item.id);
    setConfirmDelete(false);
  };

  return (
    <div className="border border-d2bg-border">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-d2bg-elevated/40 transition-colors"
      >
        <div className="flex items-center gap-3">
          <span className="text-slate-200 text-sm">{item.name}</span>
          <span className={`text-[10px] uppercase tracking-widest px-1.5 py-0.5 border ${
            item.status === "active" ? "text-green-400 border-green-800" :
            item.status === "setup" ? "text-slate-400 border-d2bg-border" :
            "text-slate-500 border-d2bg-border"
          }`}>
            {item.status}
          </span>
          {item.duration_weeks !== null && (
            <span className="text-[10px] text-slate-600">{fmtDurationWeeks(item.duration_weeks)}</span>
          )}
        </div>
        <div className="flex items-center gap-4 text-xs text-slate-500">
          <span>{item.achievement_count} achievements</span>
          <span>{fmtDate(item.started_at)} – {fmtDate(item.ended_at ?? item.scheduled_end_at)}</span>
          <span>{open ? "▲" : "▼"}</span>
        </div>
      </button>

      {open && (
        <div className="border-t border-d2bg-border">
          {item.status === "setup" ? (
            <div className="p-4">
              <StartSeasonPanel
                seasonId={item.id}
                seasonName={item.name}
                durationWeeks={item.duration_weeks}
                dismissButton={
                  <button
                    onClick={() => setConfirmDelete(true)}
                    className="px-4 py-2 text-sm text-red-400 border border-red-900/50 hover:border-red-700 hover:bg-red-950/30 transition-colors"
                  >
                    Delete Season
                  </button>
                }
              />
            </div>
          ) : (
            <div className="px-4 pb-4 pt-3 flex justify-end">
              <button
                onClick={() => setConfirmDelete(true)}
                className="text-xs text-slate-600 hover:text-red-400 transition-colors"
              >
                Delete record
              </button>
            </div>
          )}
          {confirmDelete && (
            <div className="px-4 pb-4">
              <ConfirmDialog
                title="Delete Season"
                message={`Delete "${item.name}"? This removes the season record and milestones. Archive snapshots are kept.`}
                confirmLabel="Delete"
                dangerous
                onConfirm={handleDelete}
                onCancel={() => setConfirmDelete(false)}
                loading={deleteSeason.isPending}
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function Seasons() {
  const { data: seasons, isLoading: loadingList, error: listError } = useSeasons();
  const { data: activeSeason, isLoading: loadingActive } = useActiveSeason();

  const pastSeasons = seasons?.filter((s) => s.status !== "active") ?? [];
  const hasActive = !!activeSeason;

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-8">
      <div>
        <h1 className="text-d2gold font-diablo text-xl tracking-widest">Seasons</h1>
        <p className="text-slate-500 text-xs mt-1">Fresh-start mechanics with milestone rewards. SC only.</p>
      </div>

      {/* Active Season */}
      <section className="space-y-3">
        <h2 className="text-slate-400 text-xs uppercase tracking-widest border-b border-d2bg-border pb-2">
          Active Season
        </h2>
        {loadingActive ? (
          <p className="text-slate-600 text-sm">Loading…</p>
        ) : hasActive ? (
          <ActiveSeasonCard season={activeSeason} />
        ) : (
          <p className="text-slate-500 text-sm">No active season.</p>
        )}
      </section>

      {/* Create New Season (only when no active season) */}
      {!hasActive && (
        <section className="space-y-3">
          <h2 className="text-slate-400 text-xs uppercase tracking-widest border-b border-d2bg-border pb-2">
            New Season
          </h2>
          <CreateSeasonPanel />
        </section>
      )}

      {/* Setup seasons waiting to start */}
      {seasons?.filter((s) => s.status === "setup").length ? (
        <section className="space-y-3">
          <h2 className="text-slate-400 text-xs uppercase tracking-widest border-b border-d2bg-border pb-2">
            Pending Start
          </h2>
          {seasons.filter((s) => s.status === "setup").map((s) => (
            <PastSeason key={s.id} item={s} />
          ))}
        </section>
      ) : null}

      {/* Past Seasons */}
      <section className="space-y-3">
        <h2 className="text-slate-400 text-xs uppercase tracking-widest border-b border-d2bg-border pb-2">
          Past Seasons
        </h2>
        {loadingList ? (
          <p className="text-slate-600 text-sm">Loading…</p>
        ) : listError ? (
          <p className="text-red-400 text-sm">Failed to load seasons.</p>
        ) : pastSeasons.filter((s) => s.status === "completed").length === 0 ? (
          <p className="text-slate-600 text-sm">No completed seasons yet.</p>
        ) : (
          pastSeasons.filter((s) => s.status === "completed").map((s) => (
            <PastSeason key={s.id} item={s} />
          ))
        )}
      </section>
    </div>
  );
}
