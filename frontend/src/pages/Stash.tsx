import { useState } from "react";
import {
  useStash,
  useVaultItems,
  useDepositGold,
  useWithdrawGold,
  useStoreItem,
  useRetrieveVaultItem,
  usePreflight,
} from "../api/hooks";
import type { StashItem, VaultItemResponse } from "../api/types";

type Mode = "sc" | "hc";
type Machine = "pc" | "deck";

const MAX_STASH_GOLD = 12_500_000;

// ─── Quality styling ──────────────────────────────────────────────────────────

function qualityColor(quality: number): string {
  switch (quality) {
    case 7: return "text-d2gold border-d2gold/60";
    case 5: return "text-green-400 border-green-600/60";
    case 4: return "text-yellow-300 border-yellow-600/60";
    case 3: return "text-blue-300 border-blue-600/60";
    case 6: return "text-orange-400 border-orange-600/60";
    default: return "text-slate-300 border-slate-600/60";
  }
}

function qualityBadge(quality: number, quality_name: string): string {
  switch (quality) {
    case 7: return "Unique";
    case 5: return "Set";
    case 4: return "Rare";
    case 3: return "Magic";
    case 6: return "Crafted";
    case 2: return "Superior";
    case 1: return "Inferior";
    default: return quality_name.charAt(0).toUpperCase() + quality_name.slice(1);
  }
}

function GoldBar({ current, max }: { current: number; max: number }) {
  const pct = Math.min(100, (current / max) * 100);
  const isNearCap = pct > 80;
  return (
    <div className="flex-1 h-1.5 bg-d2bg-elevated rounded-none overflow-hidden">
      <div
        className={`h-full transition-all duration-300 ${isNearCap ? "bg-amber-400/80" : "bg-d2gold/60"}`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

// ─── Display name helpers ─────────────────────────────────────────────────────

/** Primary display name for an item. For unknown items, returns null (caller shows quality label). */
function itemName(name: string | null): string | null {
  return name || null;
}

/** Property text color based on quality — mirrors D2's in-game color coding. */
function propColor(quality: number): string {
  switch (quality) {
    case 7: return "text-d2gold/90";
    case 5: return "text-green-400";
    case 4: return "text-yellow-300";
    case 3: return "text-blue-300";
    case 6: return "text-orange-300";
    default: return "text-slate-300";
  }
}

// ─── Store item modal ─────────────────────────────────────────────────────────

function StoreModal({
  item,
  tab,
  mode,
  machine,
  onClose,
}: {
  item: StashItem;
  tab: number;
  mode: Mode;
  machine: Machine;
  onClose: () => void;
}) {
  const store = useStoreItem();
  const displayName = item.name ?? qualityBadge(item.quality, item.quality_name);

  const handleStore = async () => {
    try {
      await store.mutateAsync({ machine, mode, tab, item_index: item.page_item_index });
      onClose();
    } catch {
      // error shown below
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4">
      <div className="bg-d2bg-elevated border border-d2bg-border w-full max-w-sm p-6 animate-fadeIn">
        <h3 className="font-diablo text-d2gold text-sm tracking-widest mb-1">Store Item</h3>
        <p className="text-slate-400 text-xs mb-1">
          <span className={`font-semibold ${qualityColor(item.quality).split(" ")[0]}`}>
            {displayName}
          </span>
          {item.base_item && (
            <span className="text-slate-500 ml-1">({item.base_item})</span>
          )}
        </p>
        <p className="text-slate-500 text-xs mb-5">
          This item will be removed from stash tab {tab + 1} and stored in your vault. You can retrieve it to tab 5 later.
        </p>

        {store.error && (
          <p className="text-red-400 text-xs mb-3 bg-red-950/30 border border-red-800/40 px-3 py-2">
            {store.error.message}
          </p>
        )}

        <div className="flex gap-2 justify-end">
          <button onClick={onClose} className="btn-d2-ghost text-xs px-4 py-2">
            Cancel
          </button>
          <button
            onClick={handleStore}
            disabled={store.isPending}
            className="btn-d2 text-xs px-4 py-2"
          >
            {store.isPending ? "Storing…" : "Store Item"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Retrieve vault modal ─────────────────────────────────────────────────────

function RetrieveVaultModal({
  item,
  mode,
  onClose,
}: {
  item: VaultItemResponse;
  mode: Mode;
  onClose: () => void;
}) {
  const retrieve = useRetrieveVaultItem();
  const [machine, setMachine] = useState<Machine>("pc");
  const displayName = item.name ?? qualityBadge(item.quality, item.quality_name) + " Item";

  const handleRetrieve = async () => {
    try {
      await retrieve.mutateAsync({ itemId: item.id, machine, mode });
      onClose();
    } catch {
      // error shown below
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4">
      <div className="bg-d2bg-elevated border border-d2bg-border w-full max-w-sm p-6 animate-fadeIn">
        <h3 className="font-diablo text-d2gold text-sm tracking-widest mb-1">Retrieve Item</h3>
        <p className="text-slate-400 text-xs mb-4">
          <span className={`font-semibold ${qualityColor(item.quality).split(" ")[0]}`}>
            {displayName}
          </span>{" "}
          will be written to stash tab 5.
        </p>

        <div className="flex gap-2 mb-5">
          {(["pc", "deck"] as const).map((m) => (
            <button
              key={m}
              onClick={() => setMachine(m)}
              className={`flex-1 text-xs py-2 border transition-colors ${
                machine === m
                  ? "border-d2gold text-d2gold bg-d2gold/8"
                  : "border-d2bg-border text-slate-500 hover:border-slate-500"
              }`}
            >
              {m === "pc" ? "Windows PC" : "Steam Deck"}
            </button>
          ))}
        </div>

        {retrieve.error && (
          <p className="text-red-400 text-xs mb-3 bg-red-950/30 border border-red-800/40 px-3 py-2">
            {retrieve.error.message}
          </p>
        )}

        <div className="flex gap-2 justify-end">
          <button onClick={onClose} className="btn-d2-ghost text-xs px-4 py-2">
            Cancel
          </button>
          <button
            onClick={handleRetrieve}
            disabled={retrieve.isPending}
            className="btn-d2 text-xs px-4 py-2"
          >
            {retrieve.isPending ? "Retrieving…" : "Retrieve"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Gold panel ───────────────────────────────────────────────────────────────

function GoldPanel({
  stashGold,
  vaultGold,
  machine,
  mode,
}: {
  stashGold: number;
  vaultGold: number;
  machine: Machine;
  mode: Mode;
}) {
  const deposit = useDepositGold();
  const withdraw = useWithdrawGold();
  const [depositInput, setDepositInput] = useState("");
  const [withdrawInput, setWithdrawInput] = useState("");
  const [depositError, setDepositError] = useState<string | null>(null);
  const [withdrawError, setWithdrawError] = useState<string | null>(null);

  const fmt = (n: number) => n.toLocaleString();

  const handleDeposit = async () => {
    const amount = parseInt(depositInput.replace(/[^0-9]/g, ""), 10);
    if (isNaN(amount) || amount <= 0) { setDepositError("Enter a valid amount"); return; }
    setDepositError(null);
    try {
      await deposit.mutateAsync({ machine, mode, amount });
      setDepositInput("");
    } catch (e: any) {
      setDepositError(e.response?.data?.detail ?? e.message);
    }
  };

  const handleWithdraw = async () => {
    const amount = parseInt(withdrawInput.replace(/[^0-9]/g, ""), 10);
    if (isNaN(amount) || amount <= 0) { setWithdrawError("Enter a valid amount"); return; }
    setWithdrawError(null);
    try {
      await withdraw.mutateAsync({ machine, mode, amount });
      setWithdrawInput("");
    } catch (e: any) {
      setWithdrawError(e.response?.data?.detail ?? e.message);
    }
  };

  return (
    <div className="bg-d2bg-elevated border border-d2bg-border p-4 space-y-4">
      <h3 className="font-diablo text-d2gold text-xs tracking-widest">Gold</h3>

      {/* Stash gold */}
      <div>
        <div className="flex items-center gap-3 mb-1.5">
          <span className="text-slate-500 text-xs w-20 shrink-0">Stash</span>
          <GoldBar current={stashGold} max={MAX_STASH_GOLD} />
          <span className="text-slate-400 text-xs w-32 text-right shrink-0 tabular-nums">
            {fmt(stashGold)} / {fmt(MAX_STASH_GOLD)}
          </span>
        </div>
        <div className="flex gap-2 ml-24">
          <input
            type="text"
            placeholder="Amount to deposit"
            value={depositInput}
            onChange={(e) => setDepositInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleDeposit()}
            className="flex-1 bg-d2bg-border/30 border border-d2bg-border text-slate-300 text-xs px-2 py-1.5 placeholder-slate-600 focus:outline-none focus:border-d2gold/50"
          />
          <button
            onClick={handleDeposit}
            disabled={deposit.isPending || !depositInput}
            className="btn-d2 text-xs px-3 py-1.5 shrink-0"
          >
            {deposit.isPending ? "…" : "Deposit"}
          </button>
        </div>
        {depositError && (
          <p className="text-red-400 text-xs ml-24 mt-1">{depositError}</p>
        )}
      </div>

      {/* Vault gold */}
      <div>
        <div className="flex items-center gap-3 mb-1.5">
          <span className="text-slate-500 text-xs w-20 shrink-0">Vault</span>
          <div className="flex-1 h-1.5 bg-d2bg-border/40 rounded-none overflow-hidden">
            <div className="h-full bg-purple-500/50" style={{ width: "100%" }} />
          </div>
          <span className="text-purple-300 text-xs w-32 text-right shrink-0 tabular-nums">
            {fmt(vaultGold)} stored
          </span>
        </div>
        <div className="flex gap-2 ml-24">
          <input
            type="text"
            placeholder="Amount to withdraw"
            value={withdrawInput}
            onChange={(e) => setWithdrawInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleWithdraw()}
            className="flex-1 bg-d2bg-border/30 border border-d2bg-border text-slate-300 text-xs px-2 py-1.5 placeholder-slate-600 focus:outline-none focus:border-d2gold/50"
          />
          <button
            onClick={handleWithdraw}
            disabled={withdraw.isPending || !withdrawInput}
            className="btn-d2 text-xs px-3 py-1.5 shrink-0"
          >
            {withdraw.isPending ? "…" : "Withdraw"}
          </button>
        </div>
        {withdrawError && (
          <p className="text-red-400 text-xs ml-24 mt-1">{withdrawError}</p>
        )}
      </div>
    </div>
  );
}

// ─── Stash tab view ───────────────────────────────────────────────────────────

function StashTabView({
  tabs,
  machine,
  mode,
  activeTab,
  onTabChange,
}: {
  tabs: { index: number; item_count: number; items: StashItem[] }[];
  machine: Machine;
  mode: Mode;
  activeTab: number;
  onTabChange: (i: number) => void;
}) {
  const [storeTarget, setStoreTarget] = useState<{ item: StashItem; tab: number } | null>(null);
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);
  const tab = tabs[activeTab];

  return (
    <div className="bg-d2bg-elevated border border-d2bg-border">
      {/* Tab selector */}
      <div className="flex border-b border-d2bg-border">
        {tabs.map((t, i) => (
          <button
            key={i}
            onClick={() => { onTabChange(i); setExpandedIdx(null); }}
            className={`flex-1 py-2.5 text-xs font-diablo tracking-wider transition-colors border-r border-d2bg-border last:border-r-0 ${
              activeTab === i
                ? "text-d2gold bg-d2bg-border/30 border-b-2 border-b-d2gold"
                : "text-slate-600 hover:text-slate-400"
            }`}
          >
            Tab {i + 1}
            {t.item_count > 0 && (
              <span className="ml-1 text-slate-700 text-[10px]">({t.item_count})</span>
            )}
          </button>
        ))}
      </div>

      {/* Item list */}
      <div className="p-3 min-h-[200px]">
        {!tab || tab.item_count === 0 ? (
          <p className="text-slate-700 text-xs text-center py-8">Empty tab</p>
        ) : (
          <div className="space-y-px">
            {tab.items.map((item, idx) => {
              const name = itemName(item.name);
              const colorClass = qualityColor(item.quality).split(" ")[0];
              const borderClass = qualityColor(item.quality).split(" ")[1] ?? "border-slate-600/60";
              const isExpanded = expandedIdx === idx;
              const hasProps = item.properties.length > 0;
              return (
                <div key={idx}>
                  <div
                    className={`px-3 py-2 border ${borderClass} bg-black/20 ${hasProps ? "cursor-pointer hover:bg-black/30" : ""}`}
                    onClick={() => hasProps && setExpandedIdx(isExpanded ? null : idx)}
                  >
                    {/* Name row */}
                    <div className="flex items-center gap-2">
                      <span className={`flex-1 text-sm font-semibold leading-snug ${colorClass}`}>
                        {name ?? item.base_item ?? qualityBadge(item.quality, item.quality_name)}
                      </span>
                      {item.is_ethereal && (
                        <span className="text-[10px] text-sky-400 font-mono shrink-0">ETH</span>
                      )}
                      {item.item_level > 0 && (
                        <span className="text-slate-600 text-[10px] shrink-0 tabular-nums">
                          ilvl {item.item_level}
                        </span>
                      )}
                      {hasProps && (
                        <span className="text-slate-600 text-[10px] shrink-0">
                          {isExpanded ? "▲" : "▼"}
                        </span>
                      )}
                      <button
                        onClick={(e) => { e.stopPropagation(); setStoreTarget({ item, tab: activeTab }); }}
                        className="text-[11px] text-slate-600 hover:text-d2gold border border-slate-800 hover:border-d2gold px-2 py-0.5 transition-colors shrink-0"
                        title="Store this item in vault"
                      >
                        Store
                      </button>
                    </div>
                    {/* Base item type — only shown as secondary when a catalog name is the primary */}
                    {name && item.base_item && (
                      <div className="text-slate-400 text-xs mt-0.5">{item.base_item}</div>
                    )}
                  </div>
                  {isExpanded && hasProps && (
                    <div className={`px-4 py-2.5 border-b border-l border-r ${borderClass} bg-black/50 space-y-0.5`}>
                      {item.properties.map((p, i) => (
                        <p key={i} className={`text-[12px] ${propColor(item.quality)}`}>{p}</p>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {storeTarget && (
        <StoreModal
          item={storeTarget.item}
          tab={storeTarget.tab}
          mode={mode}
          machine={machine}
          onClose={() => setStoreTarget(null)}
        />
      )}
    </div>
  );
}

// ─── Vault section ────────────────────────────────────────────────────────────

function VaultSection({ mode }: { mode: Mode }) {
  const { data: items, isLoading } = useVaultItems(mode);
  const [retrieveTarget, setRetrieveTarget] = useState<VaultItemResponse | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);

  if (isLoading) {
    return (
      <div className="bg-d2bg-elevated border border-d2bg-border p-4">
        <p className="text-slate-600 text-xs">Loading vault…</p>
      </div>
    );
  }

  return (
    <div className="bg-d2bg-elevated border border-d2bg-border">
      <div className="px-4 py-3 border-b border-d2bg-border flex items-center justify-between">
        <h3 className="font-diablo text-d2gold text-xs tracking-widest">Item Vault</h3>
        <span className="text-slate-600 text-xs">{items?.length ?? 0} stored</span>
      </div>

      {!items || items.length === 0 ? (
        <p className="text-slate-700 text-xs text-center py-8">
          No items stored. Use Store on any item in the live stash view.
        </p>
      ) : (
        <div className="divide-y divide-d2bg-border/30">
          {items.map((item) => {
            const name = itemName(item.name);
            const colorClass = qualityColor(item.quality).split(" ")[0];
            const borderClass = qualityColor(item.quality).split(" ")[1] ?? "border-slate-600/60";
            const hasProps = item.properties.length > 0;
            const isExpanded = expandedId === item.id;
            const date = new Date(item.stored_at).toLocaleDateString();
            return (
              <div key={item.id}>
                <div
                  className={`px-4 py-2.5 ${hasProps ? "cursor-pointer hover:bg-black/20" : ""}`}
                  onClick={() => hasProps && setExpandedId(isExpanded ? null : item.id)}
                >
                  {/* Name row */}
                  <div className="flex items-center gap-2">
                    <div className="flex-1 flex items-baseline gap-1.5 min-w-0">
                      <span className={`text-sm font-semibold leading-snug ${colorClass}`}>
                        {name ?? item.base_item ?? qualityBadge(item.quality, item.quality_name)}
                      </span>
                      {name && item.base_item && (
                        <span className="text-slate-500 text-xs font-normal shrink-0">{item.base_item}</span>
                      )}
                    </div>
                    {item.is_ethereal && (
                      <span className="text-[10px] text-sky-400 font-mono shrink-0">ETH</span>
                    )}
                    {item.item_level > 0 && (
                      <span className="text-slate-600 text-[10px] shrink-0 tabular-nums">
                        ilvl {item.item_level}
                      </span>
                    )}
                    {hasProps && (
                      <span className="text-slate-600 text-[10px] shrink-0">
                        {isExpanded ? "▲" : "▼"}
                      </span>
                    )}
                    <button
                      onClick={(e) => { e.stopPropagation(); setRetrieveTarget(item); }}
                      className="text-[11px] text-slate-600 hover:text-d2gold border border-slate-800 hover:border-d2gold px-2 py-0.5 transition-colors shrink-0"
                      title="Retrieve to tab 5"
                    >
                      Retrieve
                    </button>
                  </div>
                  {/* Metadata line */}
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className="text-slate-700 text-[10px]">Tab {item.tab + 1}</span>
                    <span className="text-slate-800 text-[10px]">·</span>
                    <span className="text-slate-700 text-[10px]">{date}</span>
                  </div>
                </div>
                {isExpanded && hasProps && (
                  <div className={`px-5 py-2.5 border-b border-l border-r ${borderClass} bg-black/50 space-y-0.5`}>
                    {item.properties.map((p, i) => (
                      <p key={i} className={`text-[12px] ${propColor(item.quality)}`}>{p}</p>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {retrieveTarget && (
        <RetrieveVaultModal
          item={retrieveTarget}
          mode={mode}
          onClose={() => setRetrieveTarget(null)}
        />
      )}
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function Stash() {
  const [machine, setMachine] = useState<Machine | null>(null);
  const [mode, setMode] = useState<Mode>("sc");
  const [activeTab, setActiveTab] = useState(0);
  const [fetchRequested, setFetchRequested] = useState(false);

  const { data: preflight } = usePreflight();

  const effectiveMachine = fetchRequested ? machine : null;
  const {
    data: stash,
    isFetching,
    error: stashError,
    refetch,
  } = useStash(effectiveMachine, mode);

  const handleLoad = () => {
    if (!machine) return;
    setActiveTab(0);
    if (fetchRequested && effectiveMachine === machine) {
      refetch();
    } else {
      setFetchRequested(true);
    }
  };

  const pcOnline = preflight ? preflight.pc_error === null : null;
  const deckOnline = preflight ? preflight.deck_error === null : null;

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="font-diablo text-d2gold text-lg tracking-widest">Item Vault</h2>
          <p className="text-slate-500 text-xs mt-1">
            Live stash view, unlimited gold storage, and item archival
          </p>
        </div>
      </div>

      {/* Controls */}
      <div className="flex flex-wrap gap-3 items-center">
        {/* Mode */}
        <div className="flex gap-1">
          {(["sc", "hc"] as const).map((m) => (
            <button
              key={m}
              onClick={() => { setMode(m); setFetchRequested(false); }}
              className={`px-3 py-1.5 text-xs border transition-colors ${
                mode === m
                  ? "border-d2gold text-d2gold bg-d2gold/8"
                  : "border-d2bg-border text-slate-500 hover:border-slate-500"
              }`}
            >
              {m === "sc" ? "Softcore" : "Hardcore"}
            </button>
          ))}
        </div>

        {/* Machine */}
        <div className="flex gap-1">
          {(["pc", "deck"] as const).map((m) => {
            const online = m === "pc" ? pcOnline : deckOnline;
            return (
              <button
                key={m}
                onClick={() => { setMachine(m); setFetchRequested(false); }}
                className={`flex items-center gap-1.5 px-3 py-1.5 text-xs border transition-colors ${
                  machine === m
                    ? "border-d2gold text-d2gold bg-d2gold/8"
                    : "border-d2bg-border text-slate-500 hover:border-slate-500"
                }`}
              >
                <span
                  className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                    online === null ? "bg-slate-600" : online ? "bg-green-400" : "bg-red-600"
                  }`}
                />
                {m === "pc" ? "Windows PC" : "Steam Deck"}
              </button>
            );
          })}
        </div>

        <button
          onClick={handleLoad}
          disabled={!machine || isFetching}
          className="btn-d2 text-xs px-4 py-1.5"
        >
          {isFetching ? "Loading…" : "Load Stash"}
        </button>
      </div>

      {/* Error */}
      {stashError && (
        <div className="bg-red-950/30 border border-red-800/40 px-4 py-3">
          <p className="text-red-400 text-xs">{(stashError as any).response?.data?.detail ?? (stashError as Error).message}</p>
        </div>
      )}

      {/* Live stash */}
      {stash && (
        <>
          {/* Gold panel */}
          <GoldPanel
            stashGold={stash.gold}
            vaultGold={stash.vault_gold}
            machine={machine!}
            mode={mode}
          />

          {/* Tab view */}
          <StashTabView
            tabs={stash.tabs}
            machine={machine!}
            mode={mode}
            activeTab={Math.min(activeTab, stash.tabs.length - 1)}
            onTabChange={setActiveTab}
          />
        </>
      )}

      {/* Vault */}
      <VaultSection mode={mode} />
    </div>
  );
}
