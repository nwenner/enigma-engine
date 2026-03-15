import { useState } from "react";
import {
  useWarlocks,
  useDemonList,
  useDemonTags,
  useSaveDemon,
  useDeleteDemon,
  useRestoreDemon,
} from "../api/hooks";
import type { DemonRecord, WarlockInfo } from "../api/types";
import { TagInput } from "../components/TagInput";

function fmt(iso: string) {
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}


// ─── Register panel ───────────────────────────────────────────────────────────

function RegisterPanel({
  warlocks,
  existingTags,
}: {
  warlocks: WarlockInfo[];
  existingTags: string[];
}) {
  const withDemon = warlocks.filter((w) => w.has_demon);
  const [character, setCharacter] = useState("");
  const [tags, setTags] = useState<string[]>([]);
  const [notes, setNotes] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const saveDemon = useSaveDemon();

  function handleRegister() {
    if (!character || tags.length === 0) return;
    setMsg(null);
    setErr(null);
    const label = tags.join(", ");
    saveDemon.mutate(
      { character, label, notes: notes.trim() || undefined },
      {
        onSuccess: () => {
          setMsg(`Registered: ${label}`);
          setTags([]);
          setNotes("");
          setCharacter("");
        },
        onError: (e) => setErr(e.message),
      }
    );
  }

  if (warlocks.length === 0) {
    return (
      <div className="card-d2 p-4">
        <p className="text-slate-500 text-sm">
          No Warlocks found in the latest snapshot. Check In from a device first.
        </p>
      </div>
    );
  }

  if (withDemon.length === 0) {
    return (
      <div className="card-d2 p-4">
        <p className="text-slate-500 text-sm">
          No Warlocks with a bound demon in the latest snapshot.
        </p>
        <p className="text-slate-600 text-xs mt-1">
          Bind a demon in-game, Check In, then return here to register it.
        </p>
      </div>
    );
  }

  return (
    <div className="card-d2 p-4">
      <p className="text-slate-400 text-xs mb-3">
        Select a Warlock with a bound demon to register it for the season:
      </p>
      <div className="space-y-2">
        <select
          className="select-d2"
          value={character}
          onChange={(e) => setCharacter(e.target.value)}
        >
          <option value="">— Choose Warlock —</option>
          {withDemon.map((w) => (
            <option key={w.filename} value={w.name}>
              {w.name}
            </option>
          ))}
        </select>
        <TagInput
          tags={tags}
          onChange={setTags}
          suggestions={existingTags}
          placeholder="Add tags: Fanaticism Aura, Level 85, Hephasto…"
        />
        <input
          className="input-d2"
          placeholder="Notes (optional)"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />
        <button
          className="btn-d2 text-sm"
          disabled={!character || tags.length === 0 || saveDemon.isPending}
          onClick={handleRegister}
        >
          {saveDemon.isPending ? "Registering…" : "Register Demon"}
        </button>
        {msg && <p className="text-emerald-400 text-xs">{msg}</p>}
        {err && <p className="text-red-400 text-xs">{err}</p>}
      </div>
    </div>
  );
}

// ─── Demon card ───────────────────────────────────────────────────────────────

function DemonCard({
  demon,
  warlocks,
}: {
  demon: DemonRecord;
  warlocks: WarlockInfo[];
}) {
  const deleteDemon = useDeleteDemon();
  const injectDemon = useRestoreDemon();
  const [target, setTarget] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  function handleInject() {
    if (!target) return;
    setMsg(null);
    setErr(null);
    injectDemon.mutate(
      { id: demon.id, character: target },
      {
        onSuccess: () =>
          setMsg(`Injected into ${target}. Sync to device when ready.`),
        onError: (e) => setErr(e.message),
      }
    );
  }

  return (
    <div className="card-d2 p-4">
      {/* Header row */}
      <div className="flex items-start justify-between gap-4 mb-3">
        <div className="min-w-0">
          <div className="flex flex-wrap gap-1 mb-1">
            <span className="text-d2gold text-sm">👹</span>
            {demon.label.split(",").map((t) => t.trim()).filter(Boolean).map((tag) => (
              <span
                key={tag}
                className="chip-d2 text-d2gold/70 border-d2gold/30"
              >
                {tag}
              </span>
            ))}
          </div>
          {demon.notes && (
            <p className="text-slate-500 text-xs mt-0.5 truncate">
              {demon.notes}
            </p>
          )}
          <p className="text-slate-600 text-xs mt-1">{fmt(demon.saved_at)}</p>
        </div>
        <button
          className="px-2 py-1 text-xs text-slate-600 hover:text-red-400 transition-colors shrink-0"
          onClick={() => deleteDemon.mutate(demon.id)}
          title="Delete"
        >
          ✕
        </button>
      </div>

      {/* Inject row */}
      {warlocks.length > 0 ? (
        <div className="flex flex-wrap gap-2 items-center">
          <span className="text-slate-500 text-xs">Inject into:</span>
          <select
            className="select-d2 w-auto"
            value={target}
            onChange={(e) => setTarget(e.target.value)}
          >
            <option value="">— Warlock —</option>
            {warlocks.map((w) => (
              <option key={w.filename} value={w.name}>
                {w.name}
              </option>
            ))}
          </select>
          <button
            className="btn-d2 text-xs"
            disabled={!target || injectDemon.isPending}
            onClick={handleInject}
          >
            {injectDemon.isPending ? "Injecting…" : "Inject →"}
          </button>
        </div>
      ) : (
        <p className="text-slate-600 text-xs">
          No Warlocks in latest snapshot — Check In to inject.
        </p>
      )}

      {msg && <p className="text-emerald-400 text-xs mt-2">{msg}</p>}
      {err && <p className="text-red-400 text-xs mt-2">{err}</p>}
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function Demon() {
  const { data: warlocks = [], isLoading: warlocksLoading } = useWarlocks();
  const { data: demons = [], isLoading: demonsLoading } = useDemonList();
  const { data: existingTags = [] } = useDemonTags();

  return (
    <div className="p-4 sm:p-6 max-w-3xl mx-auto animate-fadeIn space-y-6">
      <div>
        <h1 className="font-diablo text-d2gold text-2xl tracking-widest mb-1">Demon Registry</h1>
        <p className="text-slate-500 text-sm">
          Register a bound demon for the season. Any Warlock can have it injected
          into their save file — handy after a death.
        </p>
      </div>

      {/* Register section */}
      <div>
        <h2 className="text-slate-400 text-xs uppercase tracking-widest mb-2">Register</h2>
        {warlocksLoading ? (
          <div className="card-d2 p-4">
            <p className="text-slate-600 text-sm">Scanning snapshot…</p>
          </div>
        ) : (
          <RegisterPanel warlocks={warlocks} existingTags={existingTags} />
        )}
      </div>

      {/* Registered demons */}
      <div>
        <h2 className="text-slate-400 text-xs uppercase tracking-widest mb-3">
          Registered Demons
          {demons.length > 0 && (
            <span className="text-slate-600 font-normal ml-1 normal-case">
              ({demons.length})
            </span>
          )}
        </h2>

        {demonsLoading && (
          <p className="text-slate-600 text-sm">Loading…</p>
        )}

        {!demonsLoading && demons.length === 0 && (
          <p className="text-slate-600 text-sm">
            No demons registered yet.
          </p>
        )}

        <div className="space-y-3">
          {demons.map((d) => (
            <DemonCard key={d.id} demon={d} warlocks={warlocks} />
          ))}
        </div>
      </div>

      <div className="card-d2 p-4 text-xs text-slate-600">
        <p className="mb-1 text-slate-500 font-medium">How it works</p>
        <p>
          D2R stores the bound demon in a hidden section of the .d2s save file.
          Registering snapshots those bytes. Injecting splices them into any
          Warlock's save — no re-farming required.
        </p>
        <p className="mt-1">
          D2R must not be running when you inject. A safety backup is created automatically.
        </p>
      </div>
    </div>
  );
}
