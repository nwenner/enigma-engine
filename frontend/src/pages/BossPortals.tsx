import { useState } from "react";
import {
  useBossPortals,
  useSummonBossSet,
  useEarnBossSummonCode,
  useResetBossSummonProgress,
  usePreflight,
} from "../api/hooks";
import type { BossPortalStatus, BossPortalRequiredItem } from "../api/types";

function fmt(iso: string) {
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// ─── Code badge ───────────────────────────────────────────────────────────────

function CodeBadge({ item, earned }: { item: BossPortalRequiredItem; earned: boolean }) {
  return (
    <span
      className={`chip-d2 ${earned ? "text-emerald-400/80 border-emerald-900/60" : "text-slate-500 border-d2bg-border"}`}
      title={item.code}
    >
      {earned ? "✓" : "✗"} {item.label}
    </span>
  );
}

// ─── Boss set card ────────────────────────────────────────────────────────────

function BossSetCard({ set }: { set: BossPortalStatus }) {
  const [hardcore, setHardcore] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [showEarn, setShowEarn] = useState(false);
  const [earnCode, setEarnCode] = useState(set.required_item_codes[0] ?? "");
  const [showReset, setShowReset] = useState(false);

  const summon = useSummonBossSet();
  const earn = useEarnBossSummonCode();
  const reset = useResetBossSummonProgress();
  const { data: preflight } = usePreflight();
  const d2rRunning = preflight?.pc_running === true || preflight?.deck_running === true;

  const allEarned = set.required_item_codes.every((c) => set.earned_codes.includes(c));
  const canSummon = set.unlocked && set.missing_rewards.length === 0;

  function handleSummon() {
    setMsg(null);
    setErr(null);
    summon.mutate(
      { setId: set.id, hardcore },
      {
        onSuccess: (data) => setMsg(`Done! Items inserted into tab 5. Sync to device when ready. (Summon #${data.summon_count})`),
        onError: (e) => setErr(e.message),
      }
    );
  }

  function handleEarn() {
    if (!earnCode) return;
    setMsg(null);
    setErr(null);
    earn.mutate(
      { setId: set.id, code: earnCode },
      {
        onSuccess: (data) => {
          setMsg(`Marked '${earnCode}' as earned.${data.unlocked ? " Set UNLOCKED!" : ""}`);
          setShowEarn(false);
        },
        onError: (e) => setErr(e.message),
      }
    );
  }

  function handleReset() {
    setMsg(null);
    setErr(null);
    reset.mutate(set.id, {
      onSuccess: () => {
        setMsg("Progress reset.");
        setShowReset(false);
      },
      onError: (e) => setErr(e.message),
    });
  }

  return (
    <div className={`card-d2 p-4 sm:p-5 ${set.unlocked ? "border-d2gold/40" : ""}`}>
      {/* Header */}
      <div className="flex items-start justify-between gap-4 mb-3">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <h3 className={`text-sm font-semibold ${set.unlocked ? "text-d2gold" : "text-slate-300"}`}>
              {set.name}
            </h3>
            {set.unlocked ? (
              <span className="text-xs bg-emerald-900/40 border border-emerald-600/40 text-emerald-400 px-2 py-0.5 rounded">
                UNLOCKED
              </span>
            ) : (
              <span className="text-xs bg-d2bg-elevated border border-d2border text-slate-600 px-2 py-0.5 rounded">
                LOCKED
              </span>
            )}
          </div>
          <p className="text-slate-500 text-xs">{set.description}</p>
        </div>

        {/* Reset button (admin) */}
        {set.summon_count > 0 || set.earned_codes.length > 0 ? (
          <button
            className="text-slate-700 hover:text-red-500 text-xs transition-colors shrink-0"
            onClick={() => setShowReset(!showReset)}
            title="Reset progress"
          >
            ↺
          </button>
        ) : null}
      </div>

      {/* Required items */}
      <div className="flex flex-wrap gap-1.5 mb-4">
        {set.required_items.map((item) => (
          <CodeBadge key={item.code} item={item} earned={set.earned_codes.includes(item.code)} />
        ))}
      </div>

      {/* Progress bar */}
      {!set.unlocked && (
        <div className="mb-4">
          <div className="h-1 bg-d2bg-elevated rounded overflow-hidden">
            <div
              className="h-full bg-d2gold/50 transition-all"
              style={{
                width: `${(set.earned_codes.length / set.required_item_codes.length) * 100}%`,
              }}
            />
          </div>
          <p className="text-slate-600 text-xs mt-1">
            {set.earned_codes.length}/{set.required_item_codes.length} items farmed this season
          </p>
        </div>
      )}

      {/* Missing rewards warning */}
      {set.missing_rewards.length > 0 && (
        <div className="mb-3 px-3 py-2 bg-amber-900/20 border border-amber-600/30 rounded text-xs text-amber-400">
          Missing from rewards library: {set.missing_rewards.join(", ")} — upload these items before summoning.
        </div>
      )}

      {/* Summon controls */}
      {set.unlocked && (
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-2 text-xs text-slate-400 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={hardcore}
                onChange={(e) => setHardcore(e.target.checked)}
                className="accent-d2gold"
              />
              Hardcore stash
            </label>
            <button
              className="btn-d2 text-sm"
              disabled={!canSummon || summon.isPending || d2rRunning}
              title={d2rRunning ? "D2R is running — close the game first" : undefined}
              onClick={handleSummon}
            >
              {summon.isPending ? "Summoning…" : "Summon →"}
            </button>
          </div>
          {set.summon_count > 0 && (
            <p className="text-slate-600 text-xs">
              Summoned {set.summon_count}× · last {set.last_summoned_at ? fmt(set.last_summoned_at) : "—"}
            </p>
          )}
        </div>
      )}

      {/* Manual earn fallback */}
      {!set.unlocked && (
        <div className="mt-2">
          {showEarn ? (
            <div className="flex flex-wrap gap-2 items-center">
              <select
                className="select-d2 w-auto"
                value={earnCode}
                onChange={(e) => setEarnCode(e.target.value)}
              >
                {set.required_items
                  .filter((i) => !set.earned_codes.includes(i.code))
                  .map((i) => (
                    <option key={i.code} value={i.code}>{i.label}</option>
                  ))}
              </select>
              <button
                className="btn-d2 text-xs disabled:opacity-40"
                onClick={handleEarn}
                disabled={earn.isPending}
              >
                {earn.isPending ? "Marking…" : "Mark Earned"}
              </button>
              <button
                className="btn-d2-ghost text-xs"
                onClick={() => setShowEarn(false)}
              >
                cancel
              </button>
            </div>
          ) : !allEarned ? (
            <button
              className="text-slate-600 text-xs hover:text-slate-400 transition-colors"
              onClick={() => setShowEarn(true)}
            >
              Mark code as earned manually →
            </button>
          ) : null}
        </div>
      )}

      {/* Reset confirm */}
      {showReset && (
        <div className="mt-3 flex items-center gap-3">
          <span className="text-slate-500 text-xs">Reset all progress for this set?</span>
          <button
            className="btn-d2-danger text-xs"
            onClick={handleReset}
            disabled={reset.isPending}
          >
            {reset.isPending ? "Resetting…" : "Confirm Reset"}
          </button>
          <button
            className="btn-d2-ghost text-xs"
            onClick={() => setShowReset(false)}
          >
            cancel
          </button>
        </div>
      )}

      {msg && <p className="text-emerald-400 text-xs mt-2">{msg}</p>}
      {err && <p className="text-red-400 text-xs mt-2">{err}</p>}
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function BossPortals() {
  const { data: sets = [], isLoading, error } = useBossPortals();
  const reset = useResetBossSummonProgress();
  const [resettingAll, setResettingAll] = useState(false);
  const [resetAllMsg, setResetAllMsg] = useState<string | null>(null);

  const hasAnyProgress = sets.some(
    (s) => s.earned_codes.length > 0 || s.summon_count > 0
  );

  async function handleResetAll() {
    setResettingAll(true);
    setResetAllMsg(null);
    try {
      await Promise.all(sets.map((s) => reset.mutateAsync(s.id)));
      setResetAllMsg("All progress reset.");
    } catch (e) {
      setResetAllMsg(`Error: ${(e as Error).message}`);
    } finally {
      setResettingAll(false);
    }
  }

  return (
    <div className="p-4 sm:p-6 max-w-3xl mx-auto animate-fadeIn space-y-6">
      <div className="flex items-start justify-between gap-4">
        <h1 className="font-diablo text-d2gold text-2xl tracking-widest">Boss Portals</h1>
        {hasAnyProgress && (
          <button
            className="text-xs text-slate-600 hover:text-red-400 transition-colors disabled:opacity-40 shrink-0 mt-1"
            onClick={handleResetAll}
            disabled={resettingAll}
            title="Reset all boss portal progress (for testing)"
          >
            {resettingAll ? "Resetting…" : "↺ Reset All"}
          </button>
        )}
      </div>
      <p className="text-slate-500 text-sm mb-6">
        Farm each summon set at least once to unlock infinite repeatable retrieval.
        Items are placed in portal tab 5 — sync to device when ready.
      </p>
      {resetAllMsg && (
        <p className="text-slate-400 text-xs mb-4">{resetAllMsg}</p>
      )}

      {isLoading && <p className="text-slate-600 text-sm">Loading…</p>}
      {error && <p className="text-red-400 text-sm">Failed to load: {(error as Error).message}</p>}

      <div className="space-y-4">
        {sets
          .slice()
          .sort((a, b) => a.sort_order - b.sort_order)
          .map((set) => (
            <BossSetCard key={set.id} set={set} />
          ))}
      </div>

      <div className="card-d2 p-4 text-xs text-slate-600">
        <p className="mb-1 text-slate-500 font-medium">How it works</p>
        <p>
          Check In from a device with the required items in portal tab 5 to auto-detect them.
          Once all items for a set are earned, you can summon (inject to tab 5) as many times as you like
          for the rest of the season — no re-farming required.
          Progress resets when a new season starts.
        </p>
        <p className="mt-1">
          If auto-detection misses an item, use "Mark Earned" to record it manually.
        </p>
      </div>
    </div>
  );
}
