import { useState } from "react";
import {
  useSeedsCurrentQuery,
  useSeedLibrary,
  useSaveSeed,
  useApplySeed,
  useUpdateSeed,
  useDeleteSeed,
  usePreflight,
} from "../api/hooks";
import type { SeedEntry, SavedSeedRecord } from "../api/types";
import { TagInput } from "../components/TagInput";
import { toast } from "sonner";

function fmt(iso: string) {
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// ─── Current Seeds Section ────────────────────────────────────────────────────

function CurrentSeedsSection({
  seeds,
  existingTags,
}: {
  seeds: SeedEntry[];
  existingTags: string[];
}) {
  const [expandedRow, setExpandedRow] = useState<string | null>(null);
  const [tags, setTags] = useState<string[]>([]);
  const [notes, setNotes] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const saveSeed = useSaveSeed();
  const { data: preflight } = usePreflight();
  const d2rRunning = preflight?.pc_running === true || preflight?.deck_running === true;

  function handleExpand(character: string) {
    setExpandedRow(character);
    setTags([]);
    setNotes("");
    setErr(null);
  }

  function handleSave() {
    if (!expandedRow) return;
    setErr(null);
    saveSeed.mutate(
      {
        character: expandedRow,
        label: tags.join(", "),
        notes: notes.trim() || undefined,
      },
      {
        onSuccess: () => {
          setExpandedRow(null);
          setTags([]);
          setNotes("");
        },
        onError: (e) => setErr(e.message),
      }
    );
  }

  return (
    <div className="card-d2">
      {seeds.map((seed) => (
        <div key={seed.character} className="px-4 py-3 border-b border-d2bg-border/50 last:border-0">
          <div className="flex items-center justify-between gap-3">
            <span className="text-sm text-slate-200">
              {seed.name}{" "}
              <span className="text-slate-500 text-xs ml-1">{seed.class_name}</span>
            </span>
            <div className="flex items-center gap-3">
              <span className="text-xs text-slate-500 font-mono">{seed.seed_hex}</span>
              {expandedRow !== seed.character && (
                <button
                  className="btn-d2 text-xs"
                  disabled={d2rRunning}
                  title={d2rRunning ? "D2R is running — close the game first" : undefined}
                  onClick={() => handleExpand(seed.character)}
                >
                  Save Seed
                </button>
              )}
            </div>
          </div>

          {expandedRow === seed.character && (
            <div className="mt-3 space-y-2 pt-3 border-t border-d2bg-border/50">
              <TagInput
                tags={tags}
                onChange={setTags}
                suggestions={existingTags}
                placeholder="Add tags: Pindleskin, Chaos Sanctuary, Holy Grail run..."
              />
              <input
                className="input-d2"
                placeholder="Notes (optional)"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
              />
              <div className="flex items-center gap-3">
                <button
                  className="btn-d2 text-sm"
                  disabled={tags.length === 0 || saveSeed.isPending || d2rRunning}
                  onClick={handleSave}
                >
                  {saveSeed.isPending ? "Saving..." : "Save ✓"}
                </button>
                <button
                  className="text-slate-500 text-xs hover:text-slate-300"
                  onClick={() => setExpandedRow(null)}
                >
                  Cancel
                </button>
              </div>
              {err && <p className="text-red-400 text-xs">{err}</p>}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// ─── Seed Library Row ─────────────────────────────────────────────────────────

function SeedLibraryRow({
  seed,
  characters,
  existingTags,
}: {
  seed: SavedSeedRecord;
  characters: SeedEntry[];
  existingTags: string[];
}) {
  const [editing, setEditing] = useState(false);
  const [target, setTarget] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [editTags, setEditTags] = useState<string[]>([]);
  const [editNotes, setEditNotes] = useState("");
  const applySeed = useApplySeed();
  const updateSeed = useUpdateSeed();
  const deleteSeed = useDeleteSeed();
  const { data: preflight } = usePreflight();
  const d2rRunning = preflight?.pc_running === true || preflight?.deck_running === true;

  const tags = seed.label.split(",").map((t) => t.trim()).filter(Boolean);

  function handleApply() {
    if (!target) return;
    setMsg(null);
    setErr(null);
    applySeed.mutate(
      { seedId: seed.id, character: target },
      {
        onSuccess: (data) => {
          setMsg("Applied to " + data.character + ". Sync to device when ready.");
          toast.success(
            "Applied '" + data.seed_name + "' to " + data.character + " (" + data.seed_hex + ")"
          );
          setTarget("");
        },
        onError: (e) => setErr(e.message),
      }
    );
  }

  function enterEditMode() {
    setEditing(true);
    setEditTags(tags);
    setEditNotes(seed.notes || "");
    setMsg(null);
    setErr(null);
  }

  function handleUpdate() {
    updateSeed.mutate(
      { id: seed.id, label: editTags.join(", "), notes: editNotes.trim() || undefined },
      {
        onSuccess: () => setEditing(false),
        onError: (e) => setErr(e.message),
      }
    );
  }

  return (
    <div className="px-4 py-3 border-b border-d2bg-border/50 last:border-0">
      {/* Main row */}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap gap-1 mb-1">
            {tags.map((tag) => (
              <span key={tag} className="chip-d2 text-d2gold/70 border-d2gold/30">
                {tag}
              </span>
            ))}
          </div>
          {seed.notes && <p className="text-slate-500 text-xs">{seed.notes}</p>}
          <p className="text-slate-600 text-xs mt-0.5">
            from {seed.source_character} · {fmt(seed.saved_at)}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className="text-xs text-slate-500 font-mono">{seed.seed_hex}</span>
          <button
            className="text-slate-600 text-xs hover:text-slate-400 px-1 transition-colors"
            onClick={enterEditMode}
          >
            edit
          </button>
          <button
            className="px-2 py-1 text-xs text-slate-600 hover:text-red-400 transition-colors"
            onClick={() => deleteSeed.mutate(seed.id)}
            aria-label="Delete seed"
          >
            ✕
          </button>
        </div>
      </div>

      {/* Apply controls */}
      {!editing && (
        <div className="flex flex-wrap gap-2 items-center mt-2">
          <span className="text-slate-500 text-xs">Apply to:</span>
          <select
            className="select-d2 w-auto"
            value={target}
            onChange={(e) => setTarget(e.target.value)}
          >
            <option value="">— Character —</option>
            {characters.map((c) => (
              <option key={c.character} value={c.character}>
                {c.name}
              </option>
            ))}
          </select>
          <button
            className="btn-d2 text-xs"
            disabled={!target || applySeed.isPending || d2rRunning}
            title={d2rRunning ? "D2R is running — close the game first" : undefined}
            onClick={handleApply}
          >
            {applySeed.isPending ? "Applying..." : "Apply →"}
          </button>
        </div>
      )}

      {/* Edit form */}
      {editing && (
        <div className="mt-3 space-y-2 pt-3 border-t border-d2bg-border/50">
          <TagInput
            tags={editTags}
            onChange={setEditTags}
            suggestions={existingTags}
            placeholder="Add tags..."
          />
          <input
            className="input-d2"
            placeholder="Notes (optional)"
            value={editNotes}
            onChange={(e) => setEditNotes(e.target.value)}
          />
          <div className="flex items-center gap-3">
            <button
              className="btn-d2 text-sm"
              disabled={editTags.length === 0 || updateSeed.isPending}
              onClick={handleUpdate}
            >
              {updateSeed.isPending ? "Saving..." : "Save ✓"}
            </button>
            <button
              className="text-slate-500 text-xs hover:text-slate-300"
              onClick={() => setEditing(false)}
            >
              Cancel
            </button>
          </div>
          {err && <p className="text-red-400 text-xs">{err}</p>}
        </div>
      )}

      {msg && <p className="text-emerald-400 text-xs mt-2">{msg}</p>}
      {!editing && err && <p className="text-red-400 text-xs mt-2">{err}</p>}
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function Seeds() {
  const { data: seedsData, isLoading: seedsLoading } = useSeedsCurrentQuery();
  const { data: library = [], isLoading: libraryLoading } = useSeedLibrary();
  const [activeTags, setActiveTags] = useState<Set<string>>(new Set());

  const existingTags = [
    ...new Set(
      library.flatMap((s) =>
        s.label
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean)
      )
    ),
  ];

  function toggleTag(tag: string) {
    setActiveTags((prev) => {
      const next = new Set(prev);
      if (next.has(tag)) next.delete(tag);
      else next.add(tag);
      return next;
    });
  }

  const filteredLibrary =
    activeTags.size === 0
      ? library
      : library.filter((s) =>
          s.label
            .split(",")
            .map((t) => t.trim())
            .filter(Boolean)
            .some((t) => activeTags.has(t))
        );

  return (
    <div className="p-4 sm:p-6 max-w-3xl mx-auto animate-fadeIn space-y-6">
      <div>
        <h1 className="font-diablo text-d2gold text-2xl tracking-widest mb-1">Map Seeds</h1>
        <p className="text-slate-500 text-sm">
          Save map seeds from your characters. Apply any saved seed to reproduce a known farming
          layout.
        </p>
      </div>

      {/* Current Seeds */}
      <div>
        <h2 className="text-slate-400 text-xs uppercase tracking-widest mb-2">Current Seeds</h2>
        {seedsLoading ? (
          <div className="card-d2 p-4">
            <p className="text-slate-600 text-sm">Scanning snapshot...</p>
          </div>
        ) : !seedsData || seedsData.seeds.length === 0 ? (
          <div className="card-d2 p-4">
            <p className="text-slate-500 text-sm">
              No snapshot available. Check In from a device first.
            </p>
          </div>
        ) : (
          <CurrentSeedsSection seeds={seedsData.seeds} existingTags={existingTags} />
        )}
      </div>

      {/* Seed Library */}
      <div>
        <h2 className="text-slate-400 text-xs uppercase tracking-widest mb-3">
          Seed Library
          {library.length > 0 && (
            <span className="text-slate-600 font-normal ml-1 normal-case">
              ({library.length})
            </span>
          )}
        </h2>

        {existingTags.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mb-3">
            {existingTags.map((tag) => (
              <button
                key={tag}
                className={`chip-d2 cursor-pointer transition-all ${
                  activeTags.has(tag)
                    ? "text-d2gold border-d2gold/60"
                    : "text-slate-500 border-slate-600 opacity-60 hover:opacity-90"
                }`}
                onClick={() => toggleTag(tag)}
              >
                {tag}
              </button>
            ))}
          </div>
        )}

        {libraryLoading && <p className="text-slate-600 text-sm">Loading...</p>}
        {!libraryLoading && library.length === 0 && (
          <p className="text-slate-600 text-sm">No seeds saved yet.</p>
        )}
        {!libraryLoading && library.length > 0 && filteredLibrary.length === 0 && (
          <p className="text-slate-600 text-sm">No seeds match the selected tags.</p>
        )}
        {filteredLibrary.length > 0 && (
          <div className="card-d2 overflow-hidden">
            {filteredLibrary.map((s) => (
              <SeedLibraryRow
                key={s.id}
                seed={s}
                characters={seedsData?.seeds ?? []}
                existingTags={existingTags}
              />
            ))}
          </div>
        )}
      </div>

      {/* How it works blurb */}
      <div className="card-d2 p-4 text-xs text-slate-600">
        <p className="mb-1 text-slate-500 font-medium">How it works</p>
        <p>
          D2R generates a unique map layout from your character's seed value. Saving a seed
          preserves a known-good farming layout. Apply it to any character to reproduce that layout
          — no re-rolling required.
        </p>
        <p className="mt-1">
          D2R must not be running when you apply. A safety backup is created automatically.
        </p>
      </div>
    </div>
  );
}
