import { useState } from "react";
import {
  useSeasons,
  useActiveSeason,
  useCreateSeason,
  useStartSeason,
  useEndSeason,
  useDeleteSeason,
  useClaimAchievement,
  useRewards,
  useAddMilestone,
  usePatchMilestone,
  useDeleteMilestone,
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
  if (type === "gold_vault") return "Gold Vault";
  return type;
}

function fmtGoldTarget(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${Math.round(n / 1_000)}K`;
  return n.toLocaleString();
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4">
      <div className="card-d2 p-6 max-w-md w-full space-y-4 animate-fadeIn">
        <h3 className="font-diablo text-d2gold text-sm tracking-widest">{title}</h3>
        <p className="text-slate-300 text-sm whitespace-pre-line">{message}</p>
        {error && <p className="text-red-400 text-sm bg-red-950/30 border border-red-800/40 px-3 py-2">{error}</p>}
        <div className="flex gap-3 justify-end">
          <button onClick={onCancel} disabled={loading} className="btn-d2-ghost text-sm">
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={loading}
            className={dangerous ? "btn-d2-danger text-sm" : "btn-d2 text-sm"}
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
    <div className={`card-d2 p-4 space-y-2 ${ms.is_expired ? "opacity-60" : ""}`}>
      <div className="flex items-start justify-between gap-4">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className={`text-sm font-medium ${ms.is_expired ? "text-slate-500" : "text-slate-200"}`}>
            {ms.name}
          </span>
          <span className="text-[10px] uppercase tracking-widest text-slate-500 border border-d2bg-border px-1.5 py-0.5">
            {milestoneTypeLabel(ms.milestone_type)}
            {ms.milestone_type === "level" && ms.level_target ? ` ${ms.level_target}` : ""}
            {ms.milestone_type === "gold_vault" && ms.numeric_target != null ? ` ≥ ${fmtGoldTarget(ms.numeric_target)}` : ""}
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
          {ms.milestone_type !== "gold_vault" && (
            <span className={`text-[10px] uppercase tracking-widest px-1.5 py-0.5 border ${
              ms.scope === "account"
                ? "text-d2gold/50 border-d2gold/20"
                : "text-slate-500 border-d2bg-border"
            }`}>
              {ms.scope === "account" ? "Account" : "Per Char"}
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
            className="btn-d2 text-xs shrink-0"
          >
            Claim Reward →
          </button>
        )}
      </div>

      {myAchs.length > 0 && (
        <div className="space-y-1 pt-1">
          {myAchs.map((a) => {
            const isSeasonWide = a.character_name === "(Season)";
            return (
              <div key={a.id} className="flex items-center gap-2 text-xs text-slate-400">
                <span className={a.claimed_at ? "text-green-400" : "text-slate-300"}>
                  {a.claimed_at ? "✓" : "○"}
                </span>
                {isSeasonWide ? (
                  <span className="text-slate-500 italic">Account milestone</span>
                ) : (
                  <>
                    <span>{a.character_name}</span>
                    <span className="text-slate-600">{a.character_class}</span>
                    <span className="text-slate-600">Lvl {a.character_level}</span>
                  </>
                )}
                <span className="text-slate-600">— {fmtDate(a.achieved_at)}</span>
                {a.claimed_at && (
                  <span className="text-green-500/70">Claimed {fmtDate(a.claimed_at)}</span>
                )}
              </div>
            );
          })}
        </div>
      )}

      {myAchs.length === 0 && (
        <p className="text-slate-600 text-xs">
          {ms.is_expired
            ? "Time window closed — milestone can no longer be earned."
            : ms.scope === "account"
              ? "Not yet achieved this season."
              : "No characters have achieved this yet."}
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

// ─── Edit Milestone Modal ─────────────────────────────────────────────────────

function EditMilestoneModal({
  ms,
  seasonId,
  onClose,
}: {
  ms: SeasonMilestone;
  seasonId: number;
  onClose: () => void;
}) {
  const patch = usePatchMilestone();
  const { data: rewards } = useRewards();

  const [name, setName] = useState(ms.name);
  const [milestoneType, setMilestoneType] = useState(ms.milestone_type);
  const [scope, setScope] = useState<"account" | "character">(ms.scope ?? "character");
  const [levelTarget, setLevelTarget] = useState(String(ms.level_target ?? ""));
  const [numericTarget, setNumericTarget] = useState(
    ms.numeric_target != null ? String(ms.numeric_target / 1_000_000) : ""
  );
  const [timeLimitDays, setTimeLimitDays] = useState(
    ms.time_limit_hours != null ? String(ms.time_limit_hours / 24) : ""
  );

  // "keep" = don't touch reward; "library" = pick from library; "clear" = remove it
  const [rewardMode, setRewardMode] = useState<"keep" | "library" | "clear">("keep");
  const [rewardName, setRewardName] = useState("");
  const [rewardLibraryId, setRewardLibraryId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSave = async () => {
    if (!name.trim()) { setError("Name is required"); return; }
    setError(null);

    const patchBody: Record<string, unknown> = {};

    if (name !== ms.name) patchBody.name = name;
    if (milestoneType !== ms.milestone_type) patchBody.milestone_type = milestoneType;
    const effectiveScope = milestoneType === "gold_vault" ? "account" : scope;
    if (effectiveScope !== ms.scope) patchBody.scope = effectiveScope;

    const newLevel = milestoneType === "level" ? (parseInt(levelTarget) || null) : null;
    if (newLevel !== ms.level_target) patchBody.level_target = newLevel;

    const newNumericTarget = milestoneType === "gold_vault"
      ? (parseFloat(numericTarget) * 1_000_000 || null)
      : null;
    if (newNumericTarget !== ms.numeric_target) patchBody.numeric_target = newNumericTarget;

    const newHours = timeLimitDays.trim() ? Math.round(parseFloat(timeLimitDays) * 24) : null;
    if (newHours !== ms.time_limit_hours) patchBody.time_limit_hours = newHours;

    if (rewardMode === "clear") {
      patchBody.reward_item_hex = null;
      patchBody.reward_item_name = null;
    } else if (rewardMode === "library" && rewardLibraryId) {
      try {
        const resp = await fetch(`/api/rewards/${rewardLibraryId}/bytes`);
        if (!resp.ok) throw new Error("Failed to load reward bytes from library");
        const data = await resp.json();
        patchBody.reward_item_hex = data.hex;
        patchBody.reward_item_name = rewardName.trim() || null;
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : "Failed to load reward item");
        return;
      }
    }

    if (Object.keys(patchBody).length === 0) { onClose(); return; }

    try {
      await patch.mutateAsync({ seasonId, milestoneId: ms.id, patch: patchBody as any });
      onClose();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Save failed");
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4">
      <div className="card-d2 w-full max-w-lg p-6 animate-fadeIn space-y-4 overflow-y-auto max-h-[90vh]">
        <h3 className="font-diablo text-d2gold text-sm tracking-widest">Edit Milestone</h3>

        <div className="space-y-1.5">
          <label className="text-[10px] uppercase tracking-widest text-slate-500">Name</label>
          <input value={name} onChange={(e) => setName(e.target.value)} className="input-d2" />
        </div>

        <div className="flex gap-2">
          <div className="flex-1 space-y-1.5">
            <label className="text-[10px] uppercase tracking-widest text-slate-500">Type</label>
            <select
              value={milestoneType}
              onChange={(e) => setMilestoneType(e.target.value as SeasonMilestone["milestone_type"])}
              className="w-full bg-d2bg border border-d2bg-border text-slate-200 text-sm px-2 py-1.5 focus:outline-none focus:border-d2gold/50 transition-colors"
            >
              <option value="level">Level</option>
              <option value="cleared_normal">Cleared Normal</option>
              <option value="cleared_nightmare">Cleared Nightmare</option>
              <option value="cleared_hell">Cleared Hell</option>
              <option value="gold_vault">Gold Vault</option>
            </select>
          </div>
          {milestoneType !== "gold_vault" && (
            <div className="space-y-1.5">
              <label className="text-[10px] uppercase tracking-widest text-slate-500">Scope</label>
              <div className="flex gap-0.5">
                {(["account", "character"] as const).map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => setScope(s)}
                    className={`text-[10px] uppercase tracking-widest px-2 py-1.5 border transition-colors ${
                      scope === s
                        ? "border-d2gold text-d2gold bg-d2gold/10"
                        : "border-d2bg-border text-slate-500 hover:border-slate-500"
                    }`}
                  >
                    {s === "account" ? "Account" : "Per Char"}
                  </button>
                ))}
              </div>
            </div>
          )}
          {milestoneType === "level" && (
            <div className="w-24 space-y-1.5">
              <label className="text-[10px] uppercase tracking-widest text-slate-500">Level</label>
              <input
                type="number" min={1} max={99}
                value={levelTarget}
                onChange={(e) => setLevelTarget(e.target.value)}
                className="w-full bg-d2bg border border-d2bg-border text-slate-200 text-sm px-2 py-1.5 focus:outline-none focus:border-d2gold/50 transition-colors"
              />
            </div>
          )}
          {milestoneType === "gold_vault" && (
            <div className="w-44 space-y-1.5">
              <label className="text-[10px] uppercase tracking-widest text-slate-500">Gold threshold (millions)</label>
              <div className="flex items-center gap-1">
                <input
                  type="number" min={0} step={0.1}
                  placeholder="e.g. 1.5"
                  value={numericTarget}
                  onChange={(e) => setNumericTarget(e.target.value)}
                  className="flex-1 bg-d2bg border border-d2bg-border text-slate-200 text-sm px-2 py-1.5 focus:outline-none focus:border-d2gold/50 transition-colors"
                />
                <span className="text-slate-500 text-xs shrink-0">M</span>
              </div>
              {numericTarget && parseFloat(numericTarget) > 0 && (
                <p className="text-[10px] text-slate-500">= {(parseFloat(numericTarget) * 1_000_000).toLocaleString()} gold</p>
              )}
            </div>
          )}
        </div>

        <div className="space-y-1.5">
          <label className="text-[10px] uppercase tracking-widest text-slate-500">⏱ Time Limit (days from season start)</label>
          <div className="flex items-center gap-2">
            <input
              type="number" min={1} max={180}
              placeholder="No limit"
              value={timeLimitDays}
              onChange={(e) => setTimeLimitDays(e.target.value)}
              className="w-28 bg-d2bg border border-d2bg-border text-slate-200 text-sm px-2 py-1.5 focus:outline-none focus:border-d2gold/50 transition-colors"
            />
            {timeLimitDays && (
              <button onClick={() => setTimeLimitDays("")} className="text-xs text-slate-600 hover:text-red-400 transition-colors">
                ✕ clear
              </button>
            )}
          </div>
        </div>

        {/* Reward section */}
        <div className="space-y-2">
          <label className="text-[10px] uppercase tracking-widest text-slate-500">🎁 Reward Item</label>

          {ms.has_reward && rewardMode === "keep" && (
            <div className="flex items-center gap-2 p-2 bg-d2bg-elevated border border-d2bg-border text-xs">
              <span className="text-d2gold/60">Current:</span>
              <span className="text-slate-300">{ms.reward_item_name ?? ms.reward_item_code ?? "item"}</span>
            </div>
          )}

          <div className="flex gap-2">
            {(["keep", "library", "clear"] as const).map((m) => (
              <button
                key={m}
                onClick={() => { setRewardMode(m); setRewardLibraryId(null); setRewardName(""); }}
                className={`text-xs px-3 py-1.5 border transition-colors ${
                  rewardMode === m
                    ? m === "clear" ? "border-red-700 text-red-400 bg-red-950/30"
                                    : "border-d2gold text-d2gold bg-d2gold/8"
                    : "border-d2bg-border text-slate-500 hover:border-slate-500"
                }`}
              >
                {m === "keep" ? (ms.has_reward ? "Keep existing" : "No reward") : m === "library" ? "Pick from library" : "Clear reward"}
              </button>
            ))}
          </div>

          {rewardMode === "library" && (
            <div className="space-y-2">
              {rewardLibraryId && rewardName ? (
                <div className="flex items-center gap-2 px-2 py-1.5 border border-d2gold/30 bg-d2gold/5">
                  <span className="text-d2gold/80 text-xs">📚</span>
                  <span className="text-d2gold text-sm font-medium flex-1">{rewardName}</span>
                  <button onClick={() => { setRewardLibraryId(null); setRewardName(""); }} className="text-[10px] text-slate-600 hover:text-red-400 transition-colors">
                    ✕ change
                  </button>
                </div>
              ) : (
                <div className="border border-d2bg-border bg-black/30 max-h-48 overflow-y-auto divide-y divide-d2bg-border/30">
                  {!rewards || rewards.length === 0 ? (
                    <p className="text-slate-600 text-xs px-3 py-2">No rewards in library yet. Add items in the Reward Library section first.</p>
                  ) : rewards.map((r) => (
                    <button
                      key={r.id}
                      onClick={() => { setRewardLibraryId(r.id); setRewardName(r.name); }}
                      className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-d2bg-elevated/40 transition-colors"
                    >
                      <span className="text-[9px] font-mono text-slate-500 border border-slate-700 px-1 shrink-0">
                        {(r.quality_name ?? "NRM").slice(0, 3).toUpperCase()}
                      </span>
                      <span className="text-sm text-slate-200 truncate">{r.name}</span>
                      {r.is_ethereal && <span className="text-[10px] text-sky-400 font-mono shrink-0">ETH</span>}
                      {r.notes && <span className="text-[10px] text-slate-600 truncate">{r.notes}</span>}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {error && <p className="text-red-400 text-sm bg-red-950/30 border border-red-800/40 px-3 py-2">{error}</p>}

        <div className="flex gap-2 justify-end">
          <button onClick={onClose} className="btn-d2-ghost text-sm">Cancel</button>
          <button onClick={handleSave} disabled={patch.isPending} className="btn-d2 text-sm">
            {patch.isPending ? "Saving…" : "Save Changes"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Active Season Card ────────────────────────────────────────────────────────

function ActiveSeasonCard({ season }: { season: SeasonDetail }) {
  const endSeason = useEndSeason();
  const addMilestone = useAddMilestone();
  const deleteMilestone = useDeleteMilestone();

  const [showEnd, setShowEnd] = useState(false);
  const [endError, setEndError] = useState<string | null>(null);
  const [editMode, setEditMode] = useState(false);
  const [editTarget, setEditTarget] = useState<SeasonMilestone | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<SeasonMilestone | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [showAddForm, setShowAddForm] = useState(false);
  const [newMilestone, setNewMilestone] = useState<MilestoneFormRow | null>(null);
  const [addError, setAddError] = useState<string | null>(null);

  const handleEnd = async () => {
    setEndError(null);
    try {
      await endSeason.mutateAsync(season.id);
      setShowEnd(false);
    } catch (e: unknown) {
      setEndError(e instanceof Error ? e.message : "Failed to end season");
    }
  };

  const handleDeleteMilestone = async () => {
    if (!deleteTarget) return;
    setDeleteError(null);
    try {
      await deleteMilestone.mutateAsync({ seasonId: season.id, milestoneId: deleteTarget.id });
      setDeleteTarget(null);
    } catch (e: unknown) {
      setDeleteError(e instanceof Error ? e.message : "Delete failed");
    }
  };

  const handleAddMilestone = async () => {
    if (!newMilestone) return;
    setAddError(null);
    try {
      let hex: string | null = null;
      if (newMilestone.reward_library_id) {
        const resp = await fetch(`/api/rewards/${newMilestone.reward_library_id}/bytes`);
        if (!resp.ok) throw new Error("Failed to load reward bytes from library");
        const data = await resp.json();
        hex = data.hex;
      }
      const days = newMilestone.time_limit_days.trim() ? parseFloat(newMilestone.time_limit_days) : null;
      await addMilestone.mutateAsync({
        seasonId: season.id,
        milestone: {
          name: newMilestone.name,
          milestone_type: newMilestone.milestone_type,
          scope: newMilestone.milestone_type === "gold_vault" ? "account" : newMilestone.scope,
          level_target: newMilestone.milestone_type === "level" ? (parseInt(newMilestone.level_target) || null) : null,
          numeric_target: newMilestone.milestone_type === "gold_vault" ? (parseFloat(newMilestone.numeric_target) * 1_000_000 || null) : null,
          sort_order: 999,
          reward_item_hex: hex,
          reward_item_name: newMilestone.reward_item_name.trim() || null,
          time_limit_hours: days !== null ? Math.round(days * 24) : null,
        },
      });
      setNewMilestone(null);
      setShowAddForm(false);
    } catch (e: unknown) {
      setAddError(e instanceof Error ? e.message : "Failed to add milestone");
    }
  };

  const isScheduledOver = season.scheduled_end_at
    ? new Date(season.scheduled_end_at) < new Date()
    : false;

  return (
    <div className="space-y-4">
      {isScheduledOver && (
        <div className="bg-amber-950/30 border border-amber-700/50 px-4 py-3 text-amber-300 text-sm flex items-center justify-between gap-4">
          <span>This season's time has elapsed. End it whenever you're ready to archive your results.</span>
        </div>
      )}

      <div className="card-d2">
        <div className="px-4 py-3 border-b border-d2bg-border flex items-start justify-between gap-4">
          <div className="space-y-1">
            <h2 className="font-diablo text-d2gold text-sm tracking-widest">{season.name}</h2>
            <div className="flex flex-wrap items-center gap-3 text-xs text-slate-500">
              <span>Started {fmtDate(season.started_at)}</span>
              {season.duration_weeks !== null && season.scheduled_end_at && (
                <>
                  <span className="text-slate-700">·</span>
                  <span className="text-slate-400">{fmtDurationWeeks(season.duration_weeks)} season</span>
                  <span className="text-slate-700">·</span>
                  {isScheduledOver ? (
                    <span className="text-amber-400/80">Time elapsed</span>
                  ) : (
                    <span className="text-amber-400/80">{fmtTimeRemaining(season.scheduled_end_at)}</span>
                  )}
                </>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <button
              onClick={() => { setEditMode((v) => !v); setShowAddForm(false); setNewMilestone(null); }}
              className={`text-xs px-3 py-1.5 border transition-colors ${
                editMode
                  ? "border-d2gold text-d2gold bg-d2gold/8"
                  : "border-d2bg-border text-slate-500 hover:border-slate-500"
              }`}
            >
              {editMode ? "Done Editing" : "Edit Milestones"}
            </button>
            <button
              onClick={() => setShowEnd(true)}
              disabled={endSeason.isPending || endSeason.isSuccess}
              className="btn-d2-danger text-xs"
            >
              End Season
            </button>
          </div>
        </div>

        {season.notes && (
          <div className="px-4 py-3 border-b border-d2bg-border">
            <p className="text-slate-400 text-sm italic">{season.notes}</p>
          </div>
        )}

        <div className="p-4 space-y-2">
          <p className="text-slate-600 text-[10px] uppercase tracking-wider mb-3">
            Milestones
            {editMode && <span className="text-amber-500/70 ml-2">— editing active</span>}
          </p>

          {season.milestones.length === 0 && !editMode && (
            <p className="text-slate-600 text-sm">No milestones configured.</p>
          )}

          {season.milestones.map((ms) => {
            const achCount = season.achievements.filter((a) => a.milestone_id === ms.id).length;
            return (
              <div key={ms.id}>
                <MilestoneRow ms={ms} achievements={season.achievements} canClaim={!editMode} />
                {editMode && (
                  <div className="flex gap-2 mt-1 ml-1">
                    <button
                      onClick={() => setEditTarget(ms)}
                      className="text-[11px] text-slate-600 hover:text-d2gold border border-slate-800 hover:border-d2gold px-2 py-0.5 transition-colors"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => { setDeleteTarget(ms); setDeleteError(null); }}
                      className="text-[11px] text-slate-600 hover:text-red-400 border border-slate-800 hover:border-red-800 px-2 py-0.5 transition-colors"
                    >
                      Delete{achCount > 0 && ` (${achCount} achievement${achCount !== 1 ? "s" : ""})`}
                    </button>
                  </div>
                )}
              </div>
            );
          })}

          {/* Add milestone form */}
          {editMode && (
            <div className="pt-2 border-t border-d2bg-border/50 mt-2">
              {!showAddForm ? (
                <button
                  onClick={() => {
                    setShowAddForm(true);
                    setNewMilestone({ id: Date.now(), name: "", milestone_type: "level", scope: "account", level_target: "50", numeric_target: "", time_limit_days: "", reward_item_name: "", reward_library_id: null });
                  }}
                  className="text-xs text-d2gold/70 hover:text-d2gold transition-colors"
                >
                  + Add Milestone
                </button>
              ) : (
                <div className="space-y-2">
                  {newMilestone && (
                    <MilestoneFormRowUI
                      row={newMilestone}
                      onChange={setNewMilestone}
                      onRemove={() => { setShowAddForm(false); setNewMilestone(null); setAddError(null); }}
                    />
                  )}
                  {addError && (
                    <p className="text-red-400 text-xs bg-red-950/30 border border-red-800/40 px-3 py-2">{addError}</p>
                  )}
                  <div className="flex gap-2">
                    <button onClick={handleAddMilestone} disabled={addMilestone.isPending || !newMilestone?.name.trim()} className="btn-d2 text-xs">
                      {addMilestone.isPending ? "Adding…" : "Add Milestone"}
                    </button>
                    <button onClick={() => { setShowAddForm(false); setNewMilestone(null); setAddError(null); }} className="btn-d2-ghost text-xs">
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
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

      {editTarget && (
        <EditMilestoneModal
          ms={editTarget}
          seasonId={season.id}
          onClose={() => setEditTarget(null)}
        />
      )}

      {deleteTarget && (
        <ConfirmDialog
          title="Delete Milestone"
          message={(() => {
            const achCount = season.achievements.filter((a) => a.milestone_id === deleteTarget.id).length;
            const claimedCount = season.achievements.filter((a) => a.milestone_id === deleteTarget.id && a.claimed_at).length;
            let msg = `Delete "${deleteTarget.name}"?`;
            if (achCount > 0) {
              msg += `\n\nThis will also delete ${achCount} achievement record${achCount !== 1 ? "s" : ""}.`;
              if (claimedCount > 0) {
                msg += ` ${claimedCount} of these have already been claimed — the reward items in the stash will NOT be removed.`;
              }
            }
            return msg;
          })()}
          confirmLabel="Delete"
          dangerous
          onConfirm={handleDeleteMilestone}
          onCancel={() => { setDeleteTarget(null); setDeleteError(null); }}
          loading={deleteMilestone.isPending}
          error={deleteError}
        />
      )}
    </div>
  );
}

// ─── Milestone Builder Row ─────────────────────────────────────────────────────

type MilestoneFormRow = {
  id: number;
  name: string;
  milestone_type: "level" | "cleared_normal" | "cleared_nightmare" | "cleared_hell" | "gold_vault";
  scope: "account" | "character";
  level_target: string;
  numeric_target: string;   // for gold_vault: gold threshold
  time_limit_days: string;
  reward_item_name: string;
  reward_library_id: number | null;
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
  const { data: rewards } = useRewards();
  const [showLibrary, setShowLibrary] = useState(false);

  return (
    <div className="card-d2 p-3 space-y-2">
      {/* Row 1: name + type + target + remove */}
      <div className="flex items-center gap-2">
        <input
          type="text"
          placeholder="Milestone name"
          value={row.name}
          onChange={(e) => onChange({ ...row, name: e.target.value })}
          className="flex-1 input-d2 text-xs py-1.5"
        />
        <select
          value={row.milestone_type}
          onChange={(e) => onChange({ ...row, milestone_type: e.target.value as MilestoneFormRow["milestone_type"] })}
          className="bg-d2bg border border-d2bg-border text-slate-200 text-sm px-2 py-1.5 focus:outline-none focus:border-d2gold/50 transition-colors"
        >
          <option value="level">Level</option>
          <option value="cleared_normal">Cleared Normal</option>
          <option value="cleared_nightmare">Cleared Nightmare</option>
          <option value="cleared_hell">Cleared Hell</option>
          <option value="gold_vault">Gold Vault</option>
        </select>
        {row.milestone_type !== "gold_vault" && (
          <div className="flex gap-0.5 shrink-0">
            {(["account", "character"] as const).map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => onChange({ ...row, scope: s })}
                className={`text-[10px] uppercase tracking-widest px-2 py-1.5 border transition-colors ${
                  row.scope === s
                    ? "border-d2gold text-d2gold bg-d2gold/10"
                    : "border-d2bg-border text-slate-500 hover:border-slate-500"
                }`}
              >
                {s === "account" ? "Account" : "Per Char"}
              </button>
            ))}
          </div>
        )}
        {row.milestone_type === "level" && (
          <input
            type="number"
            placeholder="Lvl"
            min={1}
            max={99}
            value={row.level_target}
            onChange={(e) => onChange({ ...row, level_target: e.target.value })}
            className="w-16 bg-d2bg border border-d2bg-border text-slate-200 text-sm px-2 py-1.5 focus:outline-none focus:border-d2gold/50 transition-colors"
          />
        )}
        {row.milestone_type === "gold_vault" && (
          <div className="space-y-0.5">
            <div className="flex items-center gap-1">
              <input
                type="number"
                placeholder="e.g. 1.5"
                min={0}
                step={0.1}
                value={row.numeric_target}
                onChange={(e) => onChange({ ...row, numeric_target: e.target.value })}
                className="w-24 bg-d2bg border border-d2bg-border text-slate-200 text-sm px-2 py-1.5 focus:outline-none focus:border-d2gold/50 transition-colors"
              />
              <span className="text-slate-500 text-xs shrink-0">M gold</span>
            </div>
            {row.numeric_target && parseFloat(row.numeric_target) > 0 && (
              <p className="text-[10px] text-slate-500">= {(parseFloat(row.numeric_target) * 1_000_000).toLocaleString()} gold</p>
            )}
          </div>
        )}
        <button onClick={onRemove} className="text-slate-600 hover:text-red-400 text-sm px-2 py-1.5 transition-colors">
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
          className="w-24 bg-d2bg border border-d2bg-border text-slate-200 text-sm px-2 py-1.5 focus:outline-none focus:border-d2gold/50 transition-colors"
        />
        <span className="text-xs text-slate-500">days from season start (blank = no limit)</span>
      </div>

      {/* Row 3: reward item */}
      <div className="space-y-1">
        <div className="flex items-center justify-between">
          <label className="text-[10px] uppercase tracking-widest text-slate-500">
            🎁 Reward Item (optional)
          </label>
          {!row.reward_library_id && (
            <button
              onClick={() => setShowLibrary((v) => !v)}
              className="text-[10px] text-d2gold/70 hover:text-d2gold transition-colors"
            >
              {showLibrary ? "▲ Hide" : "📚 Pick from library"}
            </button>
          )}
        </div>

        {row.reward_library_id && row.reward_item_name ? (
          <div className="flex items-center gap-2 px-2 py-1.5 border border-d2gold/30 bg-d2gold/5">
            <span className="text-d2gold/80 text-xs">📚</span>
            <span className="text-d2gold text-sm font-medium flex-1">{row.reward_item_name}</span>
            <button
              onClick={() => { onChange({ ...row, reward_item_name: "", reward_library_id: null }); setShowLibrary(false); }}
              className="text-[10px] text-slate-600 hover:text-red-400 transition-colors"
            >
              ✕ clear
            </button>
          </div>
        ) : showLibrary ? (
          <div className="border border-d2bg-border bg-black/30 max-h-48 overflow-y-auto divide-y divide-d2bg-border/30">
            {!rewards || rewards.length === 0 ? (
              <p className="text-slate-600 text-xs px-3 py-2">
                No rewards saved. Go to <span className="text-slate-400">Reward Library</span> to add items first.
              </p>
            ) : rewards.map((r) => (
              <button
                key={r.id}
                onClick={() => { onChange({ ...row, reward_item_name: r.name, reward_library_id: r.id }); setShowLibrary(false); }}
                className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-d2bg-elevated/40 transition-colors"
              >
                <span className="text-[9px] font-mono text-slate-500 border border-slate-700 px-1 shrink-0">
                  {(r.quality_name ?? "NRM").slice(0, 3).toUpperCase()}
                </span>
                <span className="text-sm text-slate-200 truncate">{r.name}</span>
                {r.is_ethereal && <span className="text-[10px] text-sky-400 font-mono shrink-0">ETH</span>}
                {r.notes && <span className="text-[10px] text-slate-600 truncate">{r.notes}</span>}
              </button>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}

// ─── Start Season Panel ───────────────────────────────────────────────────────

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
    <div className="card-d2 p-4 border-l-2 border-l-d2gold/40 space-y-4">
      <div>
        <p className="font-diablo text-d2gold text-xs tracking-widest mb-1">Ready to Start</p>
        <p className="text-slate-400 text-sm">
          Season "{seasonName}" is in setup mode. Starting will archive the latest local snapshot, then clear
          Characters, Grail, Item Vault, and Gold Vault data. Use Sync to Device afterwards
          to push the empty state to your machines.{durationNote}
        </p>
      </div>
      <div className="flex gap-3">
        <button
          onClick={() => { setShowConfirm(true); setStartError(null); }}
          className="btn-d2 text-sm"
        >
          Start Season →
        </button>
        {dismissButton}
      </div>
      {startError && (
        <p className="text-red-400 text-xs bg-red-950/30 border border-red-800/40 px-3 py-2">{startError}</p>
      )}
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
  const [durationWeeks, setDurationWeeks] = useState("");
  const [milestones, setMilestones] = useState<MilestoneFormRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<SeasonDetail | null>(null);

  const addMilestone = () => {
    setMilestones((prev) => [
      ...prev,
      { id: nextKey(), name: "", milestone_type: "level", scope: "account", level_target: "50", numeric_target: "", time_limit_days: "", reward_item_name: "", reward_library_id: null },
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
        const hex = m.reward_library_id ? resolvedHexes[m.reward_library_id] : null;
        return {
          name: m.name,
          milestone_type: m.milestone_type,
          scope: m.milestone_type === "gold_vault" ? "account" : m.scope,
          level_target: m.milestone_type === "level" ? parseInt(m.level_target) || null : null,
          numeric_target: m.milestone_type === "gold_vault" ? (parseFloat(m.numeric_target) * 1_000_000 || null) : null,
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
          <button onClick={() => setCreated(null)} className="btn-d2-ghost text-sm">
            Not yet
          </button>
        }
      />
    );
  }

  return (
    <div className="card-d2 p-4 space-y-4">
      <h3 className="font-diablo text-d2gold text-xs tracking-widest">Create New Season</h3>

      <div className="space-y-1.5">
        <label className="text-[10px] uppercase tracking-widest text-slate-500">Season Name</label>
        <input
          type="text"
          placeholder="Season 1: Ladder Reset"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="input-d2"
        />
      </div>

      <div className="space-y-1.5">
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
            className="w-28 bg-d2bg border border-d2bg-border text-slate-200 text-sm px-3 py-1.5 focus:outline-none focus:border-d2gold/50 transition-colors"
          />
          <span className="text-xs text-slate-500">
            {durationWeeks.trim() && !isNaN(parseInt(durationWeeks))
              ? `= ${fmtDurationWeeks(parseInt(durationWeeks))} · 1–26 allowed`
              : "1–26 weeks (leave blank for open-ended)"}
          </span>
        </div>
      </div>

      <div className="space-y-1.5">
        <label className="text-[10px] uppercase tracking-widest text-slate-500">Notes (optional)</label>
        <textarea
          placeholder="Season rules, goals, etc."
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={2}
          className="w-full bg-d2bg border border-d2bg-border text-slate-300 text-sm px-3 py-1.5 focus:outline-none focus:border-d2gold/50 resize-none transition-colors"
        />
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <label className="text-[10px] uppercase tracking-widest text-slate-500">Milestones</label>
          <button onClick={addMilestone} className="text-xs text-d2gold/70 hover:text-d2gold transition-colors">
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

      {error && (
        <p className="text-red-400 text-sm bg-red-950/30 border border-red-800/40 px-3 py-2">{error}</p>
      )}

      <button
        onClick={handleSave}
        disabled={createSeason.isPending || !name.trim()}
        className="btn-d2 text-sm"
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
    <div className="card-d2 overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-d2bg-elevated/40 transition-colors"
      >
        <div className="flex items-center gap-3">
          <span className="text-slate-600 text-xs w-4 transition-transform duration-200" style={{ display: "inline-block", transform: open ? "rotate(90deg)" : "none" }}>
            ▶
          </span>
          <span className="text-slate-200 text-sm">{item.name}</span>
          <span className={`text-[10px] uppercase tracking-widest px-1.5 py-0.5 border ${
            item.status === "active" ? "text-green-400 border-green-800/60 bg-green-950/40" :
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
                    className="btn-d2-danger text-sm"
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
    <div className="p-4 sm:p-6 max-w-3xl mx-auto animate-fadeIn space-y-8">
      <div>
        <h1 className="font-diablo text-d2gold text-2xl tracking-widest">Seasons</h1>
        <p className="text-slate-500 text-sm mt-1">Fresh-start mechanics with milestone rewards. SC only.</p>
      </div>

      {/* Active Season */}
      <section className="space-y-3">
        <p className="text-slate-600 text-[10px] uppercase tracking-wider">Active Season</p>
        {loadingActive ? (
          <div className="card-d2 px-4 py-6 text-center text-slate-600 text-sm">Loading…</div>
        ) : hasActive ? (
          <ActiveSeasonCard season={activeSeason} />
        ) : (
          <div className="card-d2 px-4 py-6 text-center">
            <p className="text-slate-500 text-sm">No active season.</p>
          </div>
        )}
      </section>

      {/* Create New Season (only when no active season) */}
      {!hasActive && (
        <section className="space-y-3">
          <p className="text-slate-600 text-[10px] uppercase tracking-wider">New Season</p>
          <CreateSeasonPanel />
        </section>
      )}

      {/* Setup seasons waiting to start */}
      {seasons?.filter((s) => s.status === "setup").length ? (
        <section className="space-y-3">
          <p className="text-slate-600 text-[10px] uppercase tracking-wider">Pending Start</p>
          {seasons.filter((s) => s.status === "setup").map((s) => (
            <PastSeason key={s.id} item={s} />
          ))}
        </section>
      ) : null}

      {/* Past Seasons */}
      <section className="space-y-3">
        <p className="text-slate-600 text-[10px] uppercase tracking-wider">Past Seasons</p>
        {loadingList ? (
          <div className="card-d2 px-4 py-6 text-center text-slate-600 text-sm">Loading…</div>
        ) : listError ? (
          <div className="bg-red-950/30 border border-red-800/50 px-4 py-3 text-red-400 text-sm">
            Failed to load seasons.
          </div>
        ) : pastSeasons.filter((s) => s.status === "completed").length === 0 ? (
          <div className="card-d2 px-4 py-6 text-center">
            <p className="text-slate-600 text-sm">No completed seasons yet.</p>
          </div>
        ) : (
          pastSeasons.filter((s) => s.status === "completed").map((s) => (
            <PastSeason key={s.id} item={s} />
          ))
        )}
      </section>
    </div>
  );
}
