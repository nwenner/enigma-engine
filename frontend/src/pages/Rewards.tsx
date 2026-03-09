import { useState, useRef } from "react";
import {
  useRewards,
  useValidateReward,
  useCreateReward,
  useUpdateReward,
  useDeleteReward,
  useExtractFromD2I,
  type ExtractedD2IItem,
} from "../api/hooks";
import type { RewardOut, ValidateRewardResponse } from "../api/types";

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

// ─── Validate + preview panel ─────────────────────────────────────────────────

function ValidatePanel({ onSave }: { onSave: (hex: string, parsed: ValidateRewardResponse) => void }) {
  const validate = useValidateReward();
  const [hex, setHex] = useState("");
  const [result, setResult] = useState<ValidateRewardResponse | null>(null);

  const handleValidate = async () => {
    if (!hex.trim()) return;
    setResult(null);
    try {
      const r = await validate.mutateAsync(hex.trim());
      setResult(r);
    } catch {
      setResult(null);
    }
  };

  const qColor = qualityColor(result?.quality_name ?? null);

  return (
    <div className="border border-d2bg-border p-4 space-y-3">
      <h3 className="text-slate-300 text-sm font-medium">Paste Item Hex</h3>
      <p className="text-slate-600 text-xs">
        Copy bytes from the <span className="text-slate-400">hex</span> button on any stash item, or from Hero Editor.
        Paste them here to validate before saving.
      </p>

      <textarea
        placeholder="10 0f 00 00 4a 4d ..."
        value={hex}
        onChange={(e) => { setHex(e.target.value); setResult(null); }}
        rows={3}
        className="w-full bg-d2bg border border-d2bg-border text-slate-300 text-xs font-mono px-3 py-2 focus:outline-none focus:border-d2gold/50 resize-none"
      />

      <div className="flex items-center gap-3">
        <button
          onClick={handleValidate}
          disabled={validate.isPending || !hex.trim()}
          className="px-4 py-2 text-sm border border-d2bg-border text-slate-400 hover:text-slate-200 hover:border-slate-500 transition-colors disabled:opacity-40"
        >
          {validate.isPending ? "Validating…" : "Validate"}
        </button>
        {result && !result.valid && (
          <p className="text-red-400 text-xs">{result.error ?? "Parse failed — check the hex bytes"}</p>
        )}
      </div>

      {result?.valid && (
        <div className={`border px-4 py-3 space-y-2 ${qColor}`}>
          <div className="flex items-center gap-3">
            <span className={`text-[10px] font-mono px-1.5 py-0.5 border ${qColor}`}>
              {qualityBadge(result.quality_name)}
            </span>
            <span className="font-semibold text-sm">
              {result.item_name ?? result.item_code ?? "Unknown item"}
            </span>
            {result.is_ethereal && (
              <span className="text-[10px] text-sky-400 font-mono">ETH</span>
            )}
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-0.5 text-xs text-slate-500">
            {result.item_code && <span>Type: <span className="font-mono text-slate-400">{result.item_code}</span></span>}
            {result.item_level != null && <span>ilvl: {result.item_level}</span>}
            <span>{result.byte_len} bytes</span>
          </div>
          <button
            onClick={() => onSave(hex.trim(), result)}
            className="mt-1 px-4 py-1.5 text-sm font-medium bg-d2gold/20 text-d2gold border border-d2gold/40 hover:bg-d2gold/30 transition-colors"
          >
            Save to Library →
          </button>
        </div>
      )}
    </div>
  );
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
  const [error, setError] = useState<string | null>(null);

  const handleSave = async () => {
    if (!name.trim()) { setError("Name is required"); return; }
    setError(null);
    try {
      await createReward.mutateAsync({ name: name.trim(), hex, notes: notes.trim() || null });
      onClose();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Save failed");
    }
  };

  const qColor = qualityColor(parsed.quality_name ?? null);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
      <div className="bg-d2bg-elevated border border-d2bg-border p-6 max-w-md w-full mx-4 space-y-4">
        <h3 className="text-d2gold font-semibold text-base">Save to Reward Library</h3>

        {/* Item preview */}
        <div className={`border px-3 py-2 flex items-center gap-2 ${qColor}`}>
          <span className={`text-[10px] font-mono px-1.5 py-0.5 border ${qColor}`}>
            {qualityBadge(parsed.quality_name ?? null)}
          </span>
          <span className="text-sm font-semibold">{parsed.item_name ?? parsed.item_code ?? "Unknown"}</span>
          {parsed.is_ethereal && <span className="text-[10px] text-sky-400 font-mono ml-1">ETH</span>}
        </div>

        <div className="space-y-1">
          <label className="text-[10px] uppercase tracking-widest text-slate-500">Label</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Harlequin Crest, Enigma (Archon Plate)…"
            className="w-full bg-d2bg border border-d2bg-border text-slate-200 text-sm px-3 py-2 focus:outline-none focus:border-d2gold/50"
            autoFocus
          />
        </div>

        <div className="space-y-1">
          <label className="text-[10px] uppercase tracking-widest text-slate-500">Notes (optional)</label>
          <input
            type="text"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="e.g. 40% MF, 15 all res…"
            className="w-full bg-d2bg border border-d2bg-border text-slate-300 text-sm px-3 py-2 focus:outline-none focus:border-d2gold/50"
          />
        </div>

        {error && <p className="text-red-400 text-sm">{error}</p>}

        <div className="flex gap-3 justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-slate-400 border border-d2bg-border hover:border-slate-500 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={createReward.isPending || !name.trim()}
            className="px-4 py-2 text-sm font-medium bg-d2gold/20 text-d2gold border border-d2gold/40 hover:bg-d2gold/30 transition-colors disabled:opacity-50"
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
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [copyState, setCopyState] = useState<"idle" | "loading" | "copied">("idle");

  const qColor = qualityColor(reward.quality_name);

  const handleSaveEdit = async () => {
    if (!editName.trim()) return;
    await updateReward.mutateAsync({ id: reward.id, name: editName.trim(), notes: editNotes.trim() || null });
    setEditing(false);
  };

  const handleDelete = async () => {
    await deleteReward.mutateAsync(reward.id);
  };

  const handleCopyHex = async () => {
    setCopyState("loading");
    try {
      const resp = await fetch(`/api/rewards/${reward.id}/bytes`);
      const data = await resp.json();
      await navigator.clipboard.writeText(data.hex);
      setCopyState("copied");
      setTimeout(() => setCopyState("idle"), 2000);
    } catch {
      setCopyState("idle");
    }
  };

  if (editing) {
    return (
      <div className={`px-4 py-3 border-b border-d2bg-border/30 space-y-2`}>
        <input
          type="text"
          value={editName}
          onChange={(e) => setEditName(e.target.value)}
          className="w-full bg-d2bg border border-d2bg-border text-slate-200 text-sm px-2 py-1.5 focus:outline-none focus:border-d2gold/50"
          autoFocus
        />
        <input
          type="text"
          value={editNotes}
          onChange={(e) => setEditNotes(e.target.value)}
          placeholder="Notes (optional)"
          className="w-full bg-d2bg border border-d2bg-border text-slate-400 text-xs px-2 py-1.5 focus:outline-none focus:border-d2gold/50"
        />
        <div className="flex gap-2">
          <button
            onClick={handleSaveEdit}
            disabled={updateReward.isPending}
            className="px-3 py-1 text-xs text-d2gold border border-d2gold/40 hover:bg-d2gold/10 transition-colors"
          >
            Save
          </button>
          <button
            onClick={() => { setEditing(false); setEditName(reward.name); setEditNotes(reward.notes ?? ""); }}
            className="px-3 py-1 text-xs text-slate-500 border border-d2bg-border hover:border-slate-500 transition-colors"
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
        {/* Quality badge */}
        <span className={`text-[9px] font-mono px-1.5 py-0.5 border shrink-0 leading-4 ${qColor}`}>
          {qualityBadge(reward.quality_name)}
        </span>

        {/* Names */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className={`text-sm font-semibold ${qColor.split(" ")[0]}`}>{reward.name}</span>
            {reward.is_ethereal && (
              <span className="text-[10px] text-sky-400 font-mono">ETH</span>
            )}
          </div>
          <div className="flex items-center gap-3 mt-0.5">
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

        {/* Byte count */}
        <span className="text-slate-700 text-[10px] shrink-0 tabular-nums">{reward.byte_len}b</span>

        {/* Actions */}
        <div className="flex items-center gap-1.5 shrink-0">
          <button
            onClick={handleCopyHex}
            title="Copy hex bytes to clipboard"
            className={`text-[10px] font-mono px-1.5 py-0.5 border transition-colors ${
              copyState === "copied"
                ? "text-green-400 border-green-700"
                : "text-slate-600 border-slate-800 hover:text-d2gold hover:border-d2gold/50"
            }`}
          >
            {copyState === "loading" ? "…" : copyState === "copied" ? "✓hex" : "hex"}
          </button>
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

// ─── .d2i single-item extractor ───────────────────────────────────────────────

function ExtractPanel({ onSaveItem }: { onSaveItem: (item: ExtractedD2IItem) => void }) {
  const extract = useExtractFromD2I();
  const fileRef = useRef<HTMLInputElement>(null);
  const [result, setResult] = useState<ExtractedD2IItem | null>(null);

  const handleFile = async (file: File) => {
    setResult(null);
    try {
      const res = await extract.mutateAsync(file);
      setResult(res);
    } catch {
      setResult(null);
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

  const qColor = qualityColor(result?.quality_name ?? null);

  return (
    <div className="border border-d2bg-border p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-slate-300 text-sm font-medium">Import from Hero Editor (.d2i)</h3>
        {result && (
          <button onClick={() => setResult(null)} className="text-xs text-slate-600 hover:text-slate-400 transition-colors">
            ✕ clear
          </button>
        )}
      </div>
      <p className="text-slate-600 text-xs">
        In Hero Editor: right-click an item → <span className="text-slate-400">Export Item</span> → save as .d2i.
        Upload it here to add it to the reward library.
      </p>

      {/* Drop zone — shown when no result yet */}
      {!result && (
        <div
          onDrop={handleDrop}
          onDragOver={(e) => e.preventDefault()}
          onClick={() => fileRef.current?.click()}
          className={`border-2 border-dashed border-d2bg-border hover:border-d2gold/40 px-6 py-8 text-center cursor-pointer transition-colors ${
            extract.isPending ? "opacity-50 pointer-events-none" : ""
          }`}
        >
          <p className="text-slate-500 text-sm">
            {extract.isPending ? "Parsing…" : "Drop .d2i file here or click to browse"}
          </p>
          <p className="text-slate-700 text-xs mt-1">.d2i only</p>
        </div>
      )}
      <input ref={fileRef} type="file" accept=".d2i" className="hidden" onChange={handlePick} />

      {extract.error && (
        <p className="text-red-400 text-xs">{extract.error.message}</p>
      )}

      {/* Parsed item preview */}
      {result && (
        <div className="space-y-2">
          {!result.valid ? (
            <div className="border border-red-800 bg-red-950/20 px-4 py-3 space-y-1">
              <p className="text-red-400 text-sm">Could not parse item</p>
              <p className="text-red-600 text-xs font-mono">{result.error}</p>
              <p className="text-slate-600 text-xs">Make sure it&apos;s a valid Hero Editor .d2i export.</p>
            </div>
          ) : (
            <div className={`border px-4 py-3 space-y-2 ${qColor}`}>
              <div className="flex items-center gap-3">
                <span className={`text-[10px] font-mono px-1.5 py-0.5 border ${qColor}`}>
                  {qualityBadge(result.quality_name)}
                </span>
                <span className="font-semibold text-sm">
                  {result.item_name ?? result.item_code ?? "Unknown item"}
                </span>
                {result.is_ethereal && <span className="text-[10px] text-sky-400 font-mono">ETH</span>}
              </div>
              <div className="flex flex-wrap gap-x-4 gap-y-0.5 text-xs text-slate-500">
                {result.item_code && <span>Type: <span className="font-mono text-slate-400">{result.item_code}</span></span>}
                {result.item_level != null && <span>ilvl: {result.item_level}</span>}
                <span className="font-mono">{result.filename}</span>
                <span>{result.byte_len} bytes</span>
              </div>
              <div className="flex gap-3 pt-1">
                <button
                  onClick={() => onSaveItem(result)}
                  className="px-4 py-1.5 text-sm font-medium bg-d2gold/20 text-d2gold border border-d2gold/40 hover:bg-d2gold/30 transition-colors"
                >
                  Save to Library →
                </button>
                <button
                  onClick={() => fileRef.current?.click()}
                  className="text-xs text-slate-500 hover:text-slate-300 transition-colors self-center"
                >
                  Load another →
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function Rewards() {
  const { data: rewards, isLoading } = useRewards();
  const [saveTarget, setSaveTarget] = useState<{ hex: string; parsed: ValidateRewardResponse } | null>(null);

  const handleSaveExtracted = (item: ExtractedD2IItem) => {
    setSaveTarget({ hex: item.hex, parsed: item });
  };

  const grouped = rewards?.reduce<Record<string, RewardOut[]>>((acc, r) => {
    const key = r.quality_name ?? "other";
    acc[key] = [...(acc[key] ?? []), r];
    return acc;
  }, {}) ?? {};

  const ORDER = ["unique", "set", "rare", "crafted", "magic", "tempered", "superior", "normal", "inferior", "other"];
  const sortedGroups = ORDER.filter((k) => grouped[k]);

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-8">
      <div>
        <h1 className="text-d2gold font-diablo text-xl tracking-widest">Reward Library</h1>
        <p className="text-slate-500 text-xs mt-1">
          Curate items to use as season milestone rewards. Paste hex bytes from the stash viewer or Hero Editor.
        </p>
      </div>

      {/* Import from Hero Editor */}
      <ExtractPanel onSaveItem={handleSaveExtracted} />

      {/* Add new reward via hex paste */}
      <ValidatePanel onSave={(hex, parsed) => setSaveTarget({ hex, parsed })} />

      {/* Library */}
      <section className="space-y-3">
        <h2 className="text-slate-400 text-xs uppercase tracking-widest border-b border-d2bg-border pb-2">
          Saved Rewards ({rewards?.length ?? 0})
        </h2>

        {isLoading ? (
          <p className="text-slate-600 text-sm">Loading…</p>
        ) : !rewards || rewards.length === 0 ? (
          <p className="text-slate-600 text-sm">No rewards saved yet. Validate and save an item above.</p>
        ) : (
          <div className="border border-d2bg-border divide-y divide-transparent">
            {sortedGroups.map((quality) => (
              <div key={quality}>
                <div className="px-4 py-1.5 bg-black/20 border-b border-d2bg-border/50">
                  <span className={`text-[10px] uppercase tracking-widest font-medium ${qualityColor(quality).split(" ")[0]}`}>
                    {quality}
                  </span>
                  <span className="text-slate-700 text-[10px] ml-2">({grouped[quality].length})</span>
                </div>
                {grouped[quality].map((r) => (
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
