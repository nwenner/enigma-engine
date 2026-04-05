import { useState, useRef } from "react";
import {
  useRuneCatalog,
  useTab5Runes,
  useBuyRune,
  useTradeRune,
  useSeedRuneLibrary,
  useDeleteRuneFromLibrary,
  useVaultGold,
} from "../api/hooks";
import type { RuneCatalogEntry, Tab5RuneEntry } from "../api/types";

// ─── Helpers ──────────────────────────────────────────────────────────────────

function fmtGold(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(n % 1_000_000 === 0 ? 0 : 1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
  return n.toLocaleString();
}

const TIER_LABEL: Record<string, string> = { low: "Low", mid: "Mid", high: "High" };
const TIER_COLOR: Record<string, string> = {
  low: "text-slate-300",
  mid: "text-blue-300",
  high: "text-d2gold",
};
const TIER_COST_LABEL: Record<string, string> = { low: "500K", mid: "2.5M", high: "12M" };

// ─── Buy Modal ────────────────────────────────────────────────────────────────

interface BuyRuneModalProps {
  entry: RuneCatalogEntry;
  vaultGold: number;
  mode: string;
  onClose: () => void;
}

function BuyRuneModal({ entry, vaultGold, mode, onClose }: BuyRuneModalProps) {
  const buyRune = useBuyRune();
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const canAfford = vaultGold >= entry.gold_cost;

  const handleBuy = async () => {
    try {
      await buyRune.mutateAsync({ item_code: entry.item_code, mode });
      setSuccessMsg(`${entry.rune_name} added to Tab 5!`);
      setTimeout(onClose, 2000);
    } catch {
      // error shown below
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4">
      <div className="bg-d2bg-elevated border border-d2bg-border rounded-lg p-6 w-full max-w-sm space-y-4">
        <h2 className="font-diablo text-d2gold text-lg">Buy Rune</h2>

        <div className="space-y-1">
          <p className={`font-semibold text-base ${TIER_COLOR[entry.tier]}`}>{entry.rune_name}</p>
          <p className="text-slate-500 text-sm capitalize">{TIER_LABEL[entry.tier]} Tier</p>
        </div>

        <div className="bg-d2bg-surface border border-d2bg-border rounded p-3 space-y-1 text-sm">
          <div className="flex justify-between">
            <span className="text-slate-400">Cost</span>
            <span className="text-d2gold font-semibold">{fmtGold(entry.gold_cost)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-400">Your vault gold</span>
            <span className={canAfford ? "text-slate-200" : "text-red-400"}>
              {fmtGold(vaultGold)}
            </span>
          </div>
        </div>

        {!canAfford && (
          <p className="text-red-400 text-xs bg-red-950/30 border border-red-800/40 px-3 py-2 rounded">
            Insufficient vault gold. Need {fmtGold(entry.gold_cost - vaultGold)} more.
          </p>
        )}

        {buyRune.error && (
          <p className="text-red-400 text-xs bg-red-950/30 border border-red-800/40 px-3 py-2 rounded">
            {buyRune.error.message}
          </p>
        )}

        {successMsg && (
          <p className="text-green-400 text-xs bg-green-950/30 border border-green-800/40 px-3 py-2 rounded">
            {successMsg}
          </p>
        )}

        <div className="flex gap-2 justify-end pt-1">
          <button
            onClick={onClose}
            disabled={buyRune.isPending}
            className="btn-d2-ghost text-sm px-4 py-1.5"
          >
            Cancel
          </button>
          <button
            onClick={handleBuy}
            disabled={!canAfford || buyRune.isPending || !!successMsg}
            className="btn-d2 text-sm px-4 py-1.5 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {buyRune.isPending ? "Buying..." : `Buy for ${fmtGold(entry.gold_cost)}`}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Trade Modal ──────────────────────────────────────────────────────────────

interface TradeRuneModalProps {
  sourceRune: Tab5RuneEntry;
  catalog: RuneCatalogEntry[];
  mode: string;
  onClose: () => void;
}

function TradeRuneModal({ sourceRune, catalog, mode, onClose }: TradeRuneModalProps) {
  const tradeRune = useTradeRune();
  const [targetCode, setTargetCode] = useState<string>("");
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const targets = catalog.filter(
    (e) => e.tier === sourceRune.tier && e.item_code !== sourceRune.item_code
  );

  const selectedTarget = targets.find((e) => e.item_code === targetCode);

  const handleTrade = async () => {
    if (!targetCode) return;
    try {
      const result = await tradeRune.mutateAsync({
        tab5_item_index: sourceRune.item_index,
        target_code: targetCode,
        mode,
      });
      setSuccessMsg(`Traded ${result.source_rune} for ${result.target_rune}!`);
      setTimeout(onClose, 2000);
    } catch {
      // error shown below
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4">
      <div className="bg-d2bg-elevated border border-d2bg-border rounded-lg p-6 w-full max-w-sm space-y-4">
        <h2 className="font-diablo text-d2gold text-lg">Trade Rune</h2>

        <div className="bg-d2bg-surface border border-d2bg-border rounded p-3 text-sm">
          <p className="text-slate-400 mb-1">Give</p>
          <p className={`font-semibold ${TIER_COLOR[sourceRune.tier]}`}>{sourceRune.rune_name}</p>
        </div>

        <div>
          <label className="text-slate-400 text-xs uppercase tracking-wide block mb-1.5">
            Get ({TIER_LABEL[sourceRune.tier]} Tier)
          </label>
          <select
            value={targetCode}
            onChange={(e) => setTargetCode(e.target.value)}
            className="w-full bg-d2bg-surface border border-d2bg-border rounded px-3 py-2 text-sm text-slate-200 focus:border-d2gold/60 focus:outline-none"
          >
            <option value="">Select a rune...</option>
            {targets.map((e) => (
              <option key={e.item_code} value={e.item_code} disabled={!e.seeded}>
                {e.rune_name}{!e.seeded ? " (not available)" : ""}
              </option>
            ))}
          </select>
        </div>

        {selectedTarget && !selectedTarget.seeded && (
          <p className="text-slate-500 text-xs bg-d2bg-surface border border-d2bg-border px-3 py-2 rounded">
            That rune is not currently available in the library.
          </p>
        )}

        {tradeRune.error && (
          <p className="text-red-400 text-xs bg-red-950/30 border border-red-800/40 px-3 py-2 rounded">
            {tradeRune.error.message}
          </p>
        )}

        {successMsg && (
          <p className="text-green-400 text-xs bg-green-950/30 border border-green-800/40 px-3 py-2 rounded">
            {successMsg}
          </p>
        )}

        <div className="flex gap-2 justify-end pt-1">
          <button
            onClick={onClose}
            disabled={tradeRune.isPending}
            className="btn-d2-ghost text-sm px-4 py-1.5"
          >
            Cancel
          </button>
          <button
            onClick={handleTrade}
            disabled={
              !targetCode ||
              !(selectedTarget?.seeded) ||
              tradeRune.isPending ||
              !!successMsg
            }
            className="btn-d2 text-sm px-4 py-1.5 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {tradeRune.isPending ? "Trading..." : "Confirm Trade"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Tab 5 Inbox ─────────────────────────────────────────────────────────────

interface Tab5InboxSectionProps {
  tab5Runes: Tab5RuneEntry[] | undefined;
  catalog: RuneCatalogEntry[] | undefined;
  mode: string;
}

function Tab5InboxSection({ tab5Runes, catalog, mode }: Tab5InboxSectionProps) {
  const [tradeTarget, setTradeTarget] = useState<Tab5RuneEntry | null>(null);

  const allEntries = catalog ?? [];

  return (
    <div className="card-d2">
      <div className="px-4 py-3 border-b border-d2bg-border">
        <h2 className="font-diablo text-d2gold text-sm tracking-wide">Tab 5 Inbox</h2>
        <p className="text-slate-500 text-xs mt-0.5">
          Runes placed on tab 5 in-game after a Check In
        </p>
      </div>
      <div className="px-4 py-3">
        {!tab5Runes || tab5Runes.length === 0 ? (
          <p className="text-slate-500 text-sm italic">
            No runes on tab 5. Place a rune on tab 5 in-game and Check In to trade.
          </p>
        ) : (
          <div className="space-y-2">
            {tab5Runes.map((rune) => (
              <div
                key={rune.item_index}
                className="flex items-center justify-between bg-d2bg-surface border border-d2bg-border rounded px-3 py-2"
              >
                <div>
                  <span className={`font-semibold text-sm ${TIER_COLOR[rune.tier]}`}>
                    {rune.rune_name}
                  </span>
                  <span className="text-slate-600 text-xs ml-2">
                    {TIER_LABEL[rune.tier]} Tier
                  </span>
                </div>
                <button
                  onClick={() => setTradeTarget(rune)}
                  className="text-[11px] text-slate-500 hover:text-d2gold border border-slate-800 hover:border-d2gold px-2 py-0.5 transition-colors"
                >
                  Trade In
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {tradeTarget && (
        <TradeRuneModal
          sourceRune={tradeTarget}
          catalog={allEntries}
          mode={mode}
          onClose={() => setTradeTarget(null)}
        />
      )}
    </div>
  );
}

// ─── Rune Catalog ─────────────────────────────────────────────────────────────

interface RuneCatalogSectionProps {
  catalog: { low: RuneCatalogEntry[]; mid: RuneCatalogEntry[]; high: RuneCatalogEntry[] } | undefined;
  tab5Runes: Tab5RuneEntry[] | undefined;
  vaultGold: number;
  mode: string;
}

function RuneCatalogSection({ catalog, tab5Runes, vaultGold, mode }: RuneCatalogSectionProps) {
  const [openTiers, setOpenTiers] = useState<Record<string, boolean>>({
    low: true,
    mid: true,
    high: true,
  });
  const [buyTarget, setBuyTarget] = useState<RuneCatalogEntry | null>(null);

  const toggleTier = (tier: string) =>
    setOpenTiers((prev) => ({ ...prev, [tier]: !prev[tier] }));

  const tab5TierSet = new Set(tab5Runes?.map((r) => r.tier) ?? []);

  const renderTier = (tier: "low" | "mid" | "high", entries: RuneCatalogEntry[]) => {
    const seededCount = entries.filter((e) => e.seeded).length;
    const isOpen = openTiers[tier];

    return (
      <div key={tier} className="border border-d2bg-border rounded">
        <button
          className="w-full flex items-center justify-between px-4 py-3 hover:bg-d2bg-elevated/40 transition-colors"
          onClick={() => toggleTier(tier)}
        >
          <div className="flex items-center gap-3">
            <span className={`font-semibold text-sm ${TIER_COLOR[tier]}`}>
              {TIER_LABEL[tier]} Runes
            </span>
            <span className="text-slate-600 text-xs">
              {seededCount}/{entries.length} available
            </span>
            <span className="text-d2gold text-xs font-mono bg-d2bg-surface border border-d2bg-border px-1.5 py-0.5 rounded">
              {TIER_COST_LABEL[tier]}
            </span>
          </div>
          <span className="text-slate-600 text-xs">{isOpen ? "▲" : "▼"}</span>
        </button>

        {isOpen && (
          <div className="border-t border-d2bg-border divide-y divide-d2bg-border/50">
            {entries.map((entry) => {
              const canAfford = vaultGold >= entry.gold_cost;
              const hasTradeOption = tab5TierSet.has(entry.tier);

              return (
                <div
                  key={entry.item_code}
                  className="flex items-center justify-between px-4 py-2.5 hover:bg-d2bg-elevated/20"
                >
                  <div className="flex items-center gap-2.5">
                    <span
                      className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                        entry.seeded ? "bg-green-400" : "bg-slate-700"
                      }`}
                    />
                    <span className={`text-sm ${TIER_COLOR[entry.tier]}`}>{entry.rune_name}</span>
                    <span className="text-slate-600 text-[11px] font-mono">{entry.item_code}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    {hasTradeOption && (
                      <span className="text-[10px] text-slate-600 border border-slate-800 px-1.5 py-0.5 rounded">
                        or trade
                      </span>
                    )}
                    <button
                      onClick={() => setBuyTarget(entry)}
                      disabled={!entry.seeded || !canAfford}
                      title={
                        !entry.seeded
                          ? "Not seeded in library"
                          : !canAfford
                          ? `Need ${fmtGold(entry.gold_cost - vaultGold)} more gold`
                          : undefined
                      }
                      className="text-[11px] text-slate-500 hover:text-d2gold border border-slate-800 hover:border-d2gold px-2 py-0.5 transition-colors disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:text-slate-500 disabled:hover:border-slate-800"
                    >
                      Buy — {fmtGold(entry.gold_cost)}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    );
  };

  if (!catalog) {
    return (
      <div className="card-d2">
        <div className="px-4 py-3 border-b border-d2bg-border">
          <h2 className="font-diablo text-d2gold text-sm tracking-wide">Rune Catalog</h2>
        </div>
        <div className="px-4 py-3">
          <p className="text-slate-500 text-sm italic">Loading catalog...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="card-d2">
      <div className="px-4 py-3 border-b border-d2bg-border flex items-center justify-between">
        <div>
          <h2 className="font-diablo text-d2gold text-sm tracking-wide">Rune Catalog</h2>
          <p className="text-slate-500 text-xs mt-0.5">
            Vault gold: <span className="text-slate-300">{fmtGold(vaultGold)}</span>
          </p>
        </div>
      </div>
      <div className="px-4 py-3 space-y-2">
        {renderTier("low", catalog.low)}
        {renderTier("mid", catalog.mid)}
        {renderTier("high", catalog.high)}
      </div>

      {buyTarget && (
        <BuyRuneModal
          entry={buyTarget}
          vaultGold={vaultGold}
          mode={mode}
          onClose={() => setBuyTarget(null)}
        />
      )}
    </div>
  );
}

// ─── Seed Library ─────────────────────────────────────────────────────────────

function SeedLibrarySection() {
  const [open, setOpen] = useState(false);
  const [hardcore, setHardcore] = useState(false);
  const [seedFile, setSeedFile] = useState<File | null>(null);
  const [seedResult, setSeedResult] = useState<{ seeded: number } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const seedMutation = useSeedRuneLibrary();
  const deleteRune = useDeleteRuneFromLibrary();
  const { data: catalog } = useRuneCatalog();

  const handleSeed = async () => {
    if (!seedFile) return;
    setSeedResult(null);
    try {
      const result = await seedMutation.mutateAsync({ file: seedFile, hardcore });
      setSeedResult(result);
      setSeedFile(null);
      if (fileRef.current) fileRef.current.value = "";
    } catch {
      // error shown below
    }
  };

  const allEntries = catalog
    ? [...catalog.low, ...catalog.mid, ...catalog.high]
    : [];
  const seededEntries = allEntries.filter((e) => e.seeded);

  return (
    <div className="card-d2">
      <button
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-d2bg-elevated/30 transition-colors"
        onClick={() => setOpen((v) => !v)}
      >
        <div>
          <h2 className="font-diablo text-d2gold text-sm tracking-wide text-left">
            Seed Rune Library (Admin)
          </h2>
          {catalog && (
            <p className="text-slate-500 text-xs mt-0.5 text-left">
              {seededEntries.length} / {allEntries.length} runes seeded
            </p>
          )}
        </div>
        <span className="text-slate-600 text-xs">{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="border-t border-d2bg-border px-4 py-4 space-y-4">
          {/* Upload */}
          <div className="space-y-3">
            <p className="text-slate-400 text-xs">
              Upload a <span className="font-mono text-slate-300">.d2i</span> stash file containing
              runes. Each rune found will be registered in the library.
            </p>
            <div className="flex items-center gap-3 flex-wrap">
              <input
                ref={fileRef}
                type="file"
                accept=".d2i"
                onChange={(e) => {
                  setSeedFile(e.target.files?.[0] ?? null);
                  setSeedResult(null);
                }}
                className="text-xs text-slate-400 file:mr-2 file:py-1 file:px-3 file:border file:border-d2bg-border file:bg-d2bg-surface file:text-slate-300 file:text-xs file:cursor-pointer hover:file:border-d2gold/50 transition-colors"
              />
              <label className="flex items-center gap-2 text-xs text-slate-400 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={hardcore}
                  onChange={(e) => setHardcore(e.target.checked)}
                  className="accent-d2gold"
                />
                Hardcore
              </label>
              <button
                onClick={handleSeed}
                disabled={!seedFile || seedMutation.isPending}
                className="btn-d2 text-xs px-3 py-1.5 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {seedMutation.isPending ? "Seeding..." : "Seed"}
              </button>
            </div>

            {seedMutation.error && (
              <p className="text-red-400 text-xs bg-red-950/30 border border-red-800/40 px-3 py-2 rounded">
                {seedMutation.error.message}
              </p>
            )}

            {seedResult && (
              <p className="text-green-400 text-xs bg-green-950/30 border border-green-800/40 px-3 py-2 rounded">
                Seeded {seedResult.seeded} rune{seedResult.seeded !== 1 ? "s" : ""}
              </p>
            )}
          </div>

          {/* Per-tier seeded counts */}
          {catalog && (
            <div className="space-y-2">
              <p className="text-slate-500 text-xs uppercase tracking-widest">Library Status</p>
              <div className="grid grid-cols-3 gap-2">
                {(["low", "mid", "high"] as const).map((tier) => {
                  const entries = catalog[tier];
                  const seeded = entries.filter((e) => e.seeded).length;
                  return (
                    <div
                      key={tier}
                      className="bg-d2bg-surface border border-d2bg-border rounded p-2.5 text-center"
                    >
                      <p className={`font-semibold text-sm ${TIER_COLOR[tier]}`}>
                        {TIER_LABEL[tier]}
                      </p>
                      <p className="text-slate-400 text-xs mt-0.5">
                        {seeded}/{entries.length}
                      </p>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Seeded rune list with delete */}
          {seededEntries.length > 0 && (
            <div className="space-y-1.5">
              <p className="text-slate-500 text-xs uppercase tracking-widest">Seeded Runes</p>
              <div className="space-y-1 max-h-48 overflow-y-auto pr-1">
                {seededEntries.map((entry) => (
                  <div
                    key={entry.item_code}
                    className="flex items-center justify-between bg-d2bg-surface border border-d2bg-border rounded px-3 py-1.5"
                  >
                    <div className="flex items-center gap-2">
                      <span className={`text-xs font-semibold ${TIER_COLOR[entry.tier]}`}>
                        {entry.rune_name}
                      </span>
                      <span className="text-slate-600 text-[10px] font-mono">{entry.item_code}</span>
                    </div>
                    <button
                      onClick={() => deleteRune.mutate(entry.item_code)}
                      disabled={deleteRune.isPending}
                      className="text-[10px] text-slate-600 hover:text-red-400 border border-slate-800 hover:border-red-800/60 px-1.5 py-0.5 transition-colors disabled:opacity-40"
                    >
                      Remove
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function Store() {
  const mode = "sc";
  const { data: catalog } = useRuneCatalog();
  const { data: tab5Runes } = useTab5Runes(mode);
  const { data: vaultGold } = useVaultGold(mode);

  return (
    <div className="max-w-2xl mx-auto px-4 space-y-4 py-6 pb-8">
      <div className="flex items-baseline gap-3">
        <h1 className="font-diablo text-d2gold text-2xl tracking-wide">Rune Store</h1>
        <span className="text-slate-600 text-xs uppercase tracking-widest">SC</span>
      </div>

      <Tab5InboxSection tab5Runes={tab5Runes} catalog={catalog ? [...catalog.low, ...catalog.mid, ...catalog.high] : undefined} mode={mode} />
      <RuneCatalogSection catalog={catalog} tab5Runes={tab5Runes} vaultGold={vaultGold?.amount ?? 0} mode={mode} />
      <SeedLibrarySection />
    </div>
  );
}
