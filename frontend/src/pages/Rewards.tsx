import { useState, useRef } from "react";
import {
  useRewards,
  useCreateReward,
  useUpdateReward,
  useDeleteReward,
  useExtractFromStash,
  type StashTabItem,
} from "../api/hooks";
import type { RewardOut, ValidateRewardResponse } from "../api/types";

// ─── Constants ────────────────────────────────────────────────────────────────

export const REWARD_CATEGORIES = [
  "Rune",
  "Runeword",
  "Material",
  "Unique",
  "Set Item",
  "Key",
  "Charm",
  "Worldstone Shard",
  "Uber Ancient Summon",
] as const;

function autoCategory(qualityName: string | null): string | null {
  if (qualityName === "unique") return "Unique";
  if (qualityName === "set") return "Set Item";
  return null;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

const QUALITY_COLORS: Record<string, string> = {
  unique:   "text-d2gold border-d2gold/50 bg-d2gold/5",
  set:      "text-green-400 border-green-600/50 bg-green-900/10",
  rare:     "text-yellow-300 border-yellow-600/50 bg-yellow-900/10",
  magic:    "text-blue-300 border-blue-600/50 bg-blue-900/10",
  crafted:  "text-orange-400 border-orange-600/50 bg-orange-900/10",
  tempered: "text-purple-300 border-purple-600/50 bg-purple-900/10",
  superior: "text-slate-300 border-slate-500/50",
  normal:   "text-slate-400 border-slate-600/50",
  inferior: "text-slate-500 border-slate-700/50",
};

function qualityColor(name: string | null): string {
  return QUALITY_COLORS[name ?? ""] ?? "text-slate-400 border-slate-700/50";
}

function qualityBadge(name: string | null): string {
  if (!name) return "NRM";
  return name.slice(0, 3).toUpperCase();
}

// ─── Save dialog ──────────────────────────────────────────────────────────────

function SaveDialog({
  hex,
  parsed,
  onClose,
}: {
  hex: string;
  parsed: ValidateRewardResponse;
  onClose: () => void;
}) {
  const createReward = useCreateReward();
  const [name, setName] = useState(parsed.item_name ?? "");
  const [notes, setNotes] = useState("");
  const [category, setCategory] = useState<string>(autoCategory(parsed.quality_name ?? null) ?? "");
  const [error, setError] = useState<string | null>(null);

  const handleSave = async () => {
    if (!name.trim()) { setError("Name is required"); return; }
    setError(null);
    try {
      await createReward.mutateAsync({ name: name.trim(), hex, notes: notes.trim() || null, category: category || null });
      onClose();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Save failed");
    }
  };

  const qColor = qualityColor(parsed.quality_name ?? null);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4">
      <div className="card-d2 p-6 max-w-md w-full space-y-4 animate-fadeIn">
        <h3 className="font-diablo text-d2gold text-sm tracking-widest">Save to Reward Library</h3>

        <div className={`border px-3 py-2 flex items-center gap-2 ${qColor}`}>
          <span className={`text-[10px] font-mono px-1.5 py-0.5 border ${qColor}`}>
            {qualityBadge(parsed.quality_name ?? null)}
          </span>
          <span className="text-sm font-semibold">{parsed.item_name ?? parsed.item_code ?? "Unknown"}</span>
          {parsed.is_ethereal && <span className="text-[10px] text-sky-400 font-mono ml-1">ETH</span>}
        </div>

        <div className="space-y-1.5">
          <label className="text-[10px] uppercase tracking-widest text-slate-500">Label</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Harlequin Crest, Enigma (Archon Plate)…"
            className="input-d2"
            autoFocus
          />
        </div>

        <div className="space-y-1.5">
          <label className="text-[10px] uppercase tracking-widest text-slate-500">Category</label>
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="input-d2 text-sm"
          >
            <option value="">— Uncategorized —</option>
            {REWARD_CATEGORIES.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </div>

        <div className="space-y-1.5">
          <label className="text-[10px] uppercase tracking-widest text-slate-500">Notes (optional)</label>
          <input
            type="text"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="e.g. 40% MF, 15 all res…"
            className="input-d2"
          />
        </div>

        {error && (
          <p className="text-red-400 text-sm bg-red-950/30 border border-red-800/40 px-3 py-2">{error}</p>
        )}

        <div className="flex gap-3 justify-end">
          <button onClick={onClose} className="btn-d2-ghost text-sm">Cancel</button>
          <button
            onClick={handleSave}
            disabled={createReward.isPending || !name.trim()}
            className="btn-d2 text-sm"
          >
            {createReward.isPending ? "Saving…" : "Save Reward"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Reward row ───────────────────────────────────────────────────────────────

function RewardRow({ reward }: { reward: RewardOut }) {
  const updateReward = useUpdateReward();
  const deleteReward = useDeleteReward();
  const [editing, setEditing] = useState(false);
  const [editName, setEditName] = useState(reward.name);
  const [editNotes, setEditNotes] = useState(reward.notes ?? "");
  const [editCategory, setEditCategory] = useState(reward.category ?? "");
  const [confirmDelete, setConfirmDelete] = useState(false);

  const qColor = qualityColor(reward.quality_name);

  const handleSaveEdit = async () => {
    if (!editName.trim()) return;
    await updateReward.mutateAsync({
      id: reward.id,
      name: editName.trim(),
      notes: editNotes.trim() || null,
      category: editCategory || null,
    });
    setEditing(false);
  };

  const handleDelete = async () => {
    await deleteReward.mutateAsync(reward.id);
  };

  if (editing) {
    return (
      <div className="px-4 py-3 border-b border-d2bg-border/30 space-y-2">
        <input
          type="text"
          value={editName}
          onChange={(e) => setEditName(e.target.value)}
          className="input-d2 text-sm"
          autoFocus
        />
        <select
          value={editCategory}
          onChange={(e) => setEditCategory(e.target.value)}
          className="input-d2 text-xs"
        >
          <option value="">— Uncategorized —</option>
          {REWARD_CATEGORIES.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
        <input
          type="text"
          value={editNotes}
          onChange={(e) => setEditNotes(e.target.value)}
          placeholder="Notes (optional)"
          className="input-d2 text-xs"
        />
        <div className="flex gap-2">
          <button onClick={handleSaveEdit} disabled={updateReward.isPending} className="btn-d2 text-xs px-3 py-1.5">
            Save
          </button>
          <button
            onClick={() => { setEditing(false); setEditName(reward.name); setEditNotes(reward.notes ?? ""); setEditCategory(reward.category ?? ""); }}
            className="btn-d2-ghost text-xs px-3 py-1.5"
          >
            Cancel
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="px-4 py-3 border-b border-d2bg-border/30 hover:bg-d2bg-elevated/20 transition-colors">
      <div className="flex items-center gap-3">
        <span className={`text-[9px] font-mono px-1.5 py-0.5 border shrink-0 leading-4 ${qColor}`}>
          {qualityBadge(reward.quality_name)}
        </span>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className={`text-sm font-semibold ${qColor.split(" ")[0]}`}>{reward.name}</span>
            {reward.is_ethereal && (
              <span className="text-[10px] text-sky-400 font-mono">ETH</span>
            )}
          </div>
          <div className="flex items-center gap-3 mt-0.5">
            {reward.category && (
              <span className="text-[9px] font-mono px-1 py-0.5 border border-slate-700/60 text-slate-500 shrink-0">{reward.category}</span>
            )}
            {reward.item_name && reward.item_name !== reward.name && (
              <span className="text-slate-500 text-xs">{reward.item_name}</span>
            )}
            {reward.item_code && (
              <span className="text-slate-700 text-[10px] font-mono">{reward.item_code}</span>
            )}
            {reward.item_level != null && (
              <span className="text-slate-700 text-[10px]">ilvl {reward.item_level}</span>
            )}
            {reward.notes && (
              <span className="text-slate-500 text-xs italic">{reward.notes}</span>
            )}
          </div>
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          <button
            onClick={() => setEditing(true)}
            className="text-[11px] text-slate-600 hover:text-slate-300 border border-slate-800 hover:border-slate-600 px-2 py-0.5 transition-colors"
          >
            Edit
          </button>
          {confirmDelete ? (
            <>
              <button
                onClick={handleDelete}
                disabled={deleteReward.isPending}
                className="text-[11px] text-red-400 border border-red-800 hover:bg-red-900/20 px-2 py-0.5 transition-colors"
              >
                Confirm
              </button>
              <button
                onClick={() => setConfirmDelete(false)}
                className="text-[11px] text-slate-600 border border-slate-800 px-2 py-0.5 transition-colors"
              >
                ✕
              </button>
            </>
          ) : (
            <button
              onClick={() => setConfirmDelete(true)}
              className="text-[11px] text-slate-700 hover:text-red-400 border border-slate-800 hover:border-red-800 px-2 py-0.5 transition-colors"
            >
              Del
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Shared stash extractor ───────────────────────────────────────────────────

function StashTabRow({
  tab,
  onSave,
}: {
  tab: StashTabItem;
  onSave: (tab: StashTabItem) => void;
}) {
  const qColor = qualityColor(tab.quality_name ?? null);
  return (
    <div className={`border px-4 py-3 space-y-2 ${qColor}`}>
      <div className="flex items-center gap-3">
        <span className="text-slate-600 text-[10px] font-mono shrink-0">Tab {tab.tab_index + 1}</span>
        <span className={`text-[10px] font-mono px-1.5 py-0.5 border ${qColor}`}>
          {qualityBadge(tab.quality_name)}
        </span>
        <span className="font-semibold text-sm flex-1">
          {tab.item_name ?? tab.item_code ?? "Unknown item"}
        </span>
        {tab.is_ethereal && <span className="text-[10px] text-sky-400 font-mono">ETH</span>}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-0.5 text-xs text-slate-500">
        {tab.item_code && <span>Type: <span className="font-mono text-slate-400">{tab.item_code}</span></span>}
        {tab.item_level != null && <span>ilvl: {tab.item_level}</span>}
        <span>{tab.byte_len} bytes</span>
        {tab.jm_item_count > 1 && (
          <span className="text-amber-500">{tab.jm_item_count} items in tab</span>
        )}
        {!tab.valid && <span className="text-red-400">{tab.error ?? "Parse error"}</span>}
      </div>
      <button onClick={() => onSave(tab)} className="btn-d2 text-sm">
        Save to Library →
      </button>
    </div>
  );
}

function ExtractPanel({ onSaveItem }: { onSaveItem: (hex: string, tab: StashTabItem) => void }) {
  const extract = useExtractFromStash();
  const fileRef = useRef<HTMLInputElement>(null);
  const [tabs, setTabs] = useState<StashTabItem[] | null>(null);
  const [filename, setFilename] = useState<string | null>(null);

  const handleFile = async (file: File) => {
    setTabs(null);
    setFilename(null);
    try {
      const res = await extract.mutateAsync(file);
      setTabs(res.tabs);
      setFilename(res.filename);
    } catch {
      setTabs(null);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  };

  const handlePick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
    e.target.value = "";
  };

  return (
    <div className="card-d2 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="font-diablo text-d2gold text-xs tracking-widest">Import from Shared Stash (.d2i)</h3>
        {tabs && (
          <button
            onClick={() => { setTabs(null); setFilename(null); }}
            className="text-xs text-slate-600 hover:text-slate-400 transition-colors"
          >
            ✕ clear
          </button>
        )}
      </div>
      <p className="text-slate-500 text-xs">
        In Hero Editor: place your reward items in a <span className="text-slate-400">shared stash</span>,
        save the stash, and upload the <span className="text-slate-400">ModernSharedStash*.d2i</span> file here.
        Each tab with an item becomes a separate reward entry.
      </p>

      {!tabs && (
        <div
          onDrop={handleDrop}
          onDragOver={(e) => e.preventDefault()}
          onClick={() => fileRef.current?.click()}
          className={`border-2 border-dashed border-d2bg-border hover:border-d2gold/40 px-6 py-8 text-center cursor-pointer transition-colors ${
            extract.isPending ? "opacity-50 pointer-events-none" : ""
          }`}
        >
          <p className="text-slate-500 text-sm">
            {extract.isPending ? "Parsing…" : "Drop .d2i stash file here or click to browse"}
          </p>
          <p className="text-slate-700 text-xs mt-1">ModernSharedStash*.d2i</p>
        </div>
      )}
      <input ref={fileRef} type="file" accept=".d2i" className="hidden" onChange={handlePick} />

      {extract.error && (
        <p className="text-red-400 text-xs bg-red-950/30 border border-red-800/40 px-3 py-2">
          {extract.error.message}
        </p>
      )}

      {tabs && (
        <div className="space-y-2">
          <p className="text-slate-600 text-[10px] font-mono">{filename} — {tabs.length} tab(s) with items</p>
          {tabs.map((tab) => (
            <StashTabRow
              key={tab.tab_index}
              tab={tab}
              onSave={(t) => onSaveItem(t.hex, t)}
            />
          ))}
          <button
            onClick={() => fileRef.current?.click()}
            className="btn-d2-ghost text-sm w-full"
          >
            Load another stash →
          </button>
        </div>
      )}
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function Rewards() {
  const { data: rewards, isLoading } = useRewards();
  const [saveTarget, setSaveTarget] = useState<{ hex: string; parsed: ValidateRewardResponse } | null>(null);
  const [activeFilters, setActiveFilters] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState("");

  const handleSaveExtracted = (hex: string, item: StashTabItem) => {
    setSaveTarget({ hex, parsed: item as unknown as ValidateRewardResponse });
  };

  const searchLower = search.trim().toLowerCase();
  const filteredRewards = searchLower
    ? (rewards ?? []).filter((r) => r.name.toLowerCase().includes(searchLower))
    : rewards ?? [];

  const grouped = filteredRewards.reduce<Record<string, RewardOut[]>>((acc, r) => {
    const key = r.category ?? "Uncategorized";
    acc[key] = [...(acc[key] ?? []), r];
    return acc;
  }, {});

  const ORDER = [...REWARD_CATEGORIES, "Uncategorized"];
  const availableCategories = ORDER.filter((k) => grouped[k]);
  const visibleGroups = activeFilters.size > 0 ? availableCategories.filter((k) => activeFilters.has(k)) : availableCategories;

  return (
    <div className="p-4 sm:p-6 max-w-3xl mx-auto animate-fadeIn space-y-6">
      <div>
        <h1 className="font-diablo text-d2gold text-2xl tracking-widest">Reward Library</h1>
        <p className="text-slate-500 text-sm mt-1">
          Curate items to use as season milestone rewards. Import from a shared stash file below.
        </p>
      </div>

      <ExtractPanel onSaveItem={(hex, tab) => handleSaveExtracted(hex, tab)} />

      {/* Library */}
      <section className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <p className="text-slate-600 text-[10px] uppercase tracking-wider shrink-0">
            Saved Rewards ({filteredRewards.length}{search ? ` / ${rewards?.length ?? 0}` : ""})
          </p>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by label…"
            className="input-d2 text-xs max-w-48"
          />
        </div>

        <div className="flex items-center justify-end gap-3">
          {availableCategories.length > 1 && (
            <div className="flex flex-wrap gap-1.5 justify-end">
              {activeFilters.size > 0 && (
                <button
                  onClick={() => setActiveFilters(new Set())}
                  className="text-[10px] px-2 py-0.5 border transition-colors text-slate-500 border-slate-700 hover:text-slate-300 hover:border-slate-500"
                >
                  Clear
                </button>
              )}
              {availableCategories.map((cat) => (
                <button
                  key={cat}
                  onClick={() => setActiveFilters((prev) => {
                    const next = new Set(prev);
                    next.has(cat) ? next.delete(cat) : next.add(cat);
                    return next;
                  })}
                  className={`text-[10px] px-2 py-0.5 border transition-colors ${
                    activeFilters.has(cat)
                      ? "text-d2gold border-d2gold/50 bg-d2gold/10"
                      : "text-slate-500 border-slate-700 hover:text-slate-300 hover:border-slate-500"
                  }`}
                >
                  {cat} <span className="text-slate-700">({grouped[cat].length})</span>
                </button>
              ))}
            </div>
          )}
        </div>

        {isLoading ? (
          <div className="card-d2 px-4 py-6 text-center text-slate-600 text-sm">Loading…</div>
        ) : !rewards || rewards.length === 0 ? (
          <div className="card-d2 px-4 py-6 text-center">
            <p className="text-slate-600 text-sm">No rewards saved yet. Import a stash file above.</p>
          </div>
        ) : (
          <div className="card-d2">
            {visibleGroups.map((cat) => (
              <div key={cat}>
                <div className="px-4 py-2 bg-black/20 border-b border-d2bg-border/50 flex items-center gap-2">
                  <span className="text-[10px] uppercase tracking-widest font-medium text-d2gold">
                    {cat}
                  </span>
                  <span className="text-slate-700 text-[10px]">({grouped[cat].length})</span>
                </div>
                {grouped[cat].map((r) => (
                  <RewardRow key={r.id} reward={r} />
                ))}
              </div>
            ))}
          </div>
        )}
      </section>

      {saveTarget && (
        <SaveDialog
          hex={saveTarget.hex}
          parsed={saveTarget.parsed}
          onClose={() => setSaveTarget(null)}
        />
      )}
    </div>
  );
}
