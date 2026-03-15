import { useState } from "react";
import {
  useStash,
  useVaultItems,
  useDepositGold,
  useWithdrawGold,
  useStoreItem,
  useRetrieveVaultItem,
  useFetchStashItemBytes,
  useFetchVaultItemBytes,
  useActiveSeason,
  useRegisterRewardFromSnapshot,
  usePreflight,
} from "../api/hooks";
import type { StashItem, VaultItemResponse } from "../api/types";

function SeasonBanner() {
  const { data: season } = useActiveSeason();
  if (!season) return null;
  return (
    <div className="text-slate-500 text-xs flex items-center gap-1.5">
      <span className="text-d2gold">🗓</span>
      <span>Season: <span className="text-slate-300">{season.name}</span></span>
    </div>
  );
}
import { fmtRelative, fmtUtcDate } from "../utils/dates";

type Mode = "sc" | "hc";
type Machine = "pc" | "deck";

const MAX_STASH_GOLD = 12_500_000;

// ─── Quality styling ──────────────────────────────────────────────────────────

function qualityColor(quality: number): string {
  switch (quality) {
    case 7: return "text-d2gold border-d2gold/60";
    case 5: return "text-green-400 border-green-600/60";
    case 6: return "text-yellow-300 border-yellow-600/60";
    case 4: return "text-blue-300 border-blue-600/60";
    case 8: return "text-orange-400 border-orange-600/60";
    case 3: return "text-slate-300 border-slate-500/60";
    case 2: return "text-slate-400 border-slate-600/60";
    case 1: return "text-slate-500 border-slate-700/60";
    default: return "text-slate-400 border-slate-700/60";
  }
}

function qualityLabel(quality: number): string {
  switch (quality) {
    case 7: return "UNQ";
    case 5: return "SET";
    case 6: return "RAR";
    case 4: return "MAG";
    case 8: return "CRF";
    case 3: return "SUP";
    case 2: return "NRM";
    case 1: return "INF";
    default: return "NRM";
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

// ─── Copy hex button ──────────────────────────────────────────────────────────

function CopyStashHexButton({ mode, tab, index }: { mode: Mode; tab: number; index: number }) {
  const fetch = useFetchStashItemBytes();
  const [state, setState] = useState<"idle" | "loading" | "copied" | "error">("idle");

  const handleClick = async () => {
    setState("loading");
    try {
      const result = await fetch.mutateAsync({ mode, tab, index });
      await navigator.clipboard.writeText(result.hex);
      setState("copied");
      setTimeout(() => setState("idle"), 2000);
    } catch {
      setState("error");
      setTimeout(() => setState("idle"), 2000);
    }
  };

  return (
    <button
      onClick={handleClick}
      disabled={state === "loading"}
      title="Copy raw item hex bytes (for season rewards)"
      className={`text-[10px] font-mono px-1.5 py-0.5 border transition-colors shrink-0 ${
        state === "copied" ? "text-green-400 border-green-700" :
        state === "error"  ? "text-red-400 border-red-700" :
        "text-slate-600 border-slate-800 hover:text-d2gold hover:border-d2gold/50"
      }`}
    >
      {state === "loading" ? "…" : state === "copied" ? "✓hex" : state === "error" ? "err" : "hex"}
    </button>
  );
}

function CopyVaultHexButton({ itemId }: { itemId: number }) {
  const fetch = useFetchVaultItemBytes();
  const [state, setState] = useState<"idle" | "loading" | "copied" | "error">("idle");

  const handleClick = async () => {
    setState("loading");
    try {
      const result = await fetch.mutateAsync(itemId);
      await navigator.clipboard.writeText(result.hex);
      setState("copied");
      setTimeout(() => setState("idle"), 2000);
    } catch {
      setState("error");
      setTimeout(() => setState("idle"), 2000);
    }
  };

  return (
    <button
      onClick={handleClick}
      disabled={state === "loading"}
      title="Copy raw item hex bytes (for season rewards)"
      className={`text-[10px] font-mono px-1.5 py-0.5 border transition-colors shrink-0 ${
        state === "copied" ? "text-green-400 border-green-700" :
        state === "error"  ? "text-red-400 border-red-700" :
        "text-slate-600 border-slate-800 hover:text-d2gold hover:border-d2gold/50"
      }`}
    >
      {state === "loading" ? "…" : state === "copied" ? "✓hex" : state === "error" ? "err" : "hex"}
    </button>
  );
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
  const { data: preflight } = usePreflight();
  const d2rRunning = preflight?.pc_running === true || preflight?.deck_running === true;
  const displayName = item.name ?? item.base_item ?? qualityLabel(item.quality);
  const colorText = qualityColor(item.quality).split(" ")[0];

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
      <div className="card-d2 w-full max-w-sm p-6 animate-fadeIn">
        <h3 className="font-diablo text-d2gold text-sm tracking-widest mb-1">Store Item</h3>
        <p className="text-slate-400 text-xs mb-1">
          <span className={`font-semibold ${colorText}`}>{displayName}</span>
          {item.base_item && item.name && (
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
          <button onClick={onClose} className="btn-d2-ghost text-xs px-4 py-2">Cancel</button>
          <button
            onClick={handleStore}
            disabled={store.isPending || d2rRunning}
            title={d2rRunning ? "D2R is running — close the game first" : undefined}
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
  const { data: preflight } = usePreflight();
  const d2rRunning = preflight?.pc_running === true || preflight?.deck_running === true;
  const displayName = item.name ?? item.base_item ?? qualityLabel(item.quality);

  const handleRetrieve = async () => {
    try {
      await retrieve.mutateAsync({ itemId: item.id, mode });
      onClose();
    } catch {
      // error shown below
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4">
      <div className="card-d2 w-full max-w-sm p-6 animate-fadeIn">
        <h3 className="font-diablo text-d2gold text-sm tracking-widest mb-1">Retrieve Item</h3>
        <p className="text-slate-400 text-xs mb-5">
          <span className={`font-semibold ${qualityColor(item.quality).split(" ")[0]}`}>
            {displayName}
          </span>{" "}
          will be written to stash tab 5 in the vault snapshot. Use <span className="text-d2gold">Sync to Device</span> to push it to your machine.
        </p>

        {retrieve.error && (
          <p className="text-red-400 text-xs mb-3 bg-red-950/30 border border-red-800/40 px-3 py-2">
            {retrieve.error.message}
          </p>
        )}

        <div className="flex gap-2 justify-end">
          <button onClick={onClose} className="btn-d2-ghost text-xs px-4 py-2">Cancel</button>
          <button
            onClick={handleRetrieve}
            disabled={retrieve.isPending || d2rRunning}
            title={d2rRunning ? "D2R is running — close the game first" : undefined}
            className="btn-d2 text-xs px-4 py-2"
          >
            {retrieve.isPending ? "Retrieving…" : "Retrieve to Snapshot"}
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
  const { data: preflight } = usePreflight();
  const d2rRunning = preflight?.pc_running === true || preflight?.deck_running === true;
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
    <div className="card-d2 p-4 space-y-4">
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
            className="flex-1 bg-d2bg border border-d2bg-border text-slate-200 text-xs px-2 py-1.5 placeholder-slate-600 focus:outline-none focus:border-d2gold/50 transition-colors"
          />
          <button
            onClick={handleDeposit}
            disabled={deposit.isPending || !depositInput || d2rRunning}
            title={d2rRunning ? "D2R is running — close the game first" : undefined}
            className="btn-d2 text-xs px-3 py-1.5 shrink-0"
          >
            {deposit.isPending ? "…" : "Deposit"}
          </button>
        </div>
        {depositError && <p className="text-red-400 text-xs ml-24 mt-1">{depositError}</p>}
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
            className="flex-1 bg-d2bg border border-d2bg-border text-slate-200 text-xs px-2 py-1.5 placeholder-slate-600 focus:outline-none focus:border-d2gold/50 transition-colors"
          />
          <button
            onClick={handleWithdraw}
            disabled={withdraw.isPending || !withdrawInput || d2rRunning}
            title={d2rRunning ? "D2R is running — close the game first" : undefined}
            className="btn-d2 text-xs px-3 py-1.5 shrink-0"
          >
            {withdraw.isPending ? "…" : "Withdraw"}
          </button>
        </div>
        {withdrawError && <p className="text-red-400 text-xs ml-24 mt-1">{withdrawError}</p>}
      </div>
    </div>
  );
}

// ─── Quality summary bar ──────────────────────────────────────────────────────

const SUMMARY_ORDER = [7, 5, 6, 4, 3, 2, 1, 8, 0] as const;

function QualitySummary({ items }: { items: StashItem[] }) {
  const counts: Record<number, number> = {};
  for (const item of items) {
    counts[item.quality] = (counts[item.quality] ?? 0) + 1;
  }

  const parts = SUMMARY_ORDER
    .filter((q) => counts[q])
    .map((q) => {
      const colorText = qualityColor(q).split(" ")[0];
      return (
        <span key={q} className={`${colorText} tabular-nums`}>
          {counts[q]} {qualityLabel(q)}
        </span>
      );
    });

  if (parts.length === 0) return null;

  return (
    <div className="px-3 py-1.5 border-b border-d2bg-border bg-black/20 flex flex-wrap gap-x-3 gap-y-0.5">
      {parts.map((p, i) => (
        <span key={i} className="text-[10px]">{p}</span>
      ))}
    </div>
  );
}

// ─── Register reward dialog ───────────────────────────────────────────────────

const REWARD_CATEGORIES = [
  "Rune", "Runeword", "Material", "Unique", "Set Item",
  "Key", "Charm", "Worldstone Shard", "Uber Ancient Summon",
] as const;

function autoCategory(quality: number, isRuneword: boolean = false): string {
  if (isRuneword) return "Runeword";
  if (quality === 7) return "Unique";
  if (quality === 5) return "Set Item";
  return "";
}

function RegisterRewardDialog({
  item,
  mode,
  onSaved,
  onClose,
}: {
  item: StashItem;
  mode: Mode;
  onSaved: () => void;
  onClose: () => void;
}) {
  const register = useRegisterRewardFromSnapshot();
  const displayName = item.name ?? item.base_item ?? item.quality_name ?? "";
  const colorText = qualityColor(item.quality).split(" ")[0];
  const [name, setName] = useState(displayName);
  const [category, setCategory] = useState(autoCategory(item.quality, item.is_runeword));
  const [notes, setNotes] = useState("");

  const handleSave = async () => {
    if (!name.trim()) return;
    try {
      await register.mutateAsync({
        mode,
        item_index: item.page_item_index,
        name: name.trim(),
        category: category || null,
        notes: notes.trim() || null,
      });
      onSaved();
      onClose();
    } catch {
      // error shown below
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4">
      <div className="card-d2 w-full max-w-sm p-6 animate-fadeIn space-y-4">
        <h3 className="font-diablo text-d2gold text-sm tracking-widest">Register as Reward</h3>

        <div className={`border px-3 py-2 flex items-center gap-2 ${qualityColor(item.quality)}`}>
          <span className={`text-[9px] font-mono px-1 border leading-4 shrink-0 ${qualityColor(item.quality)}`}>
            {qualityLabel(item.quality)}
          </span>
          <span className={`text-sm font-semibold ${colorText}`}>{displayName}</span>
          {item.is_ethereal && <span className="text-[10px] text-sky-400 font-mono ml-1">ETH</span>}
        </div>

        <div className="space-y-1.5">
          <label className="text-[10px] uppercase tracking-widest text-slate-500">Label</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Harlequin Crest, Enigma (AP)…"
            className="input-d2"
            autoFocus
          />
        </div>

        <div className="space-y-1.5">
          <label className="text-[10px] uppercase tracking-widest text-slate-500">Category</label>
          <select value={category} onChange={(e) => setCategory(e.target.value)} className="input-d2 text-sm">
            <option value="">— Uncategorized —</option>
            {REWARD_CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
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

        {register.error && (
          <p className="text-red-400 text-xs bg-red-950/30 border border-red-800/40 px-3 py-2">
            {register.error.message}
          </p>
        )}

        <div className="flex gap-2 justify-end">
          <button onClick={onClose} className="btn-d2-ghost text-xs px-4 py-2">Cancel</button>
          <button
            onClick={handleSave}
            disabled={register.isPending || !name.trim()}
            className="btn-d2 text-xs px-4 py-2"
          >
            {register.isPending ? "Saving…" : "Save to Reward Library"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Single item row ──────────────────────────────────────────────────────────

const REWARD_QUALITY_THRESHOLD = 5; // set(5), crafted(6), unique(7), tempered(8)
const PORTAL_TAB = 4;

function ItemRow({
  item,
  tab,
  mode,
  isRegistered,
  onStore,
  onRegisterReward,
}: {
  item: StashItem;
  tab: number;
  mode: Mode;
  isRegistered?: boolean;
  onStore: () => void;
  onRegisterReward?: () => void;
}) {
  const { data: preflight } = usePreflight();
  const d2rRunning = preflight?.pc_running === true || preflight?.deck_running === true;
  const colorText = qualityColor(item.quality).split(" ")[0];
  const colorBorder = qualityColor(item.quality).split(" ")[1] ?? "border-slate-700/60";
  const displayName = item.name ?? item.base_item ?? item.quality_name;
  const showRegister = tab === PORTAL_TAB && (item.is_runeword || item.quality >= REWARD_QUALITY_THRESHOLD);

  return (
    <div className={`px-3 py-2 border ${colorBorder} bg-black/20`}>
      <div className="flex items-center gap-2">
        <span className={`text-[9px] font-mono px-1 border shrink-0 leading-4 ${colorText} ${colorBorder}`}>
          {qualityLabel(item.quality)}
        </span>

        <span className={`flex-1 text-sm font-semibold leading-snug min-w-0 truncate ${colorText}`}>
          {displayName}
        </span>

        {item.is_ethereal && (
          <span className="text-[10px] text-sky-400 font-mono shrink-0">ETH</span>
        )}
        {item.item_level > 0 && (
          <span className="text-slate-600 text-[10px] shrink-0 tabular-nums">
            ilvl {item.item_level}
          </span>
        )}
        <span className="text-slate-700 text-[10px] font-mono shrink-0 w-8 text-right">
          {item.item_type}
        </span>

        <CopyStashHexButton mode={mode} tab={tab} index={item.page_item_index} />
        {showRegister && (
          isRegistered ? (
            <span className="text-[11px] text-green-500 border border-green-800 px-2 py-0.5 shrink-0">✓ Saved</span>
          ) : (
            <button
              onClick={onRegisterReward}
              className="text-[11px] text-d2gold/70 hover:text-d2gold border border-d2gold/30 hover:border-d2gold/60 px-2 py-0.5 transition-colors shrink-0"
              title="Register as season reward"
            >
              Reward ★
            </button>
          )
        )}
        <button
          onClick={onStore}
          disabled={d2rRunning}
          className="text-[11px] text-slate-600 hover:text-d2gold border border-slate-800 hover:border-d2gold px-2 py-0.5 transition-colors shrink-0 disabled:opacity-40 disabled:cursor-not-allowed"
          title={d2rRunning ? "D2R is running — close the game first" : "Store this item in vault"}
        >
          Store
        </button>
      </div>

      {item.name && item.base_item && (
        <div className="text-slate-500 text-xs mt-0.5 ml-9">{item.base_item}</div>
      )}
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
  const [registerTarget, setRegisterTarget] = useState<StashItem | null>(null);
  const [registeredIndices, setRegisteredIndices] = useState<Set<number>>(new Set());
  const tab = tabs[activeTab];

  return (
    <div className="card-d2">
      {/* Tab selector */}
      <div className="flex border-b border-d2bg-border">
        {tabs.map((t, i) => (
          <button
            key={i}
            onClick={() => onTabChange(i)}
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

      {tab && tab.items.length > 0 && <QualitySummary items={tab.items} />}

      <div className="p-3 min-h-[200px]">
        {!tab || tab.item_count === 0 ? (
          <p className="text-slate-700 text-xs text-center py-8">Empty tab</p>
        ) : (
          <div className="space-y-px">
            {tab.items.map((item, idx) => (
              <ItemRow
                key={idx}
                item={item}
                tab={activeTab}
                mode={mode}
                isRegistered={registeredIndices.has(item.page_item_index)}
                onStore={() => setStoreTarget({ item, tab: activeTab })}
                onRegisterReward={() => setRegisterTarget(item)}
              />
            ))}
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

      {registerTarget && (
        <RegisterRewardDialog
          item={registerTarget}
          mode={mode}
          onSaved={() => setRegisteredIndices((prev) => new Set(prev).add(registerTarget.page_item_index))}
          onClose={() => setRegisterTarget(null)}
        />
      )}
    </div>
  );
}

// ─── Vault section ────────────────────────────────────────────────────────────

function VaultSection({ mode }: { mode: Mode }) {
  const { data: items, isLoading } = useVaultItems(mode);
  const { data: preflight } = usePreflight();
  const d2rRunning = preflight?.pc_running === true || preflight?.deck_running === true;
  const [retrieveTarget, setRetrieveTarget] = useState<VaultItemResponse | null>(null);

  if (isLoading) {
    return (
      <div className="card-d2 p-4">
        <p className="text-slate-600 text-xs">Loading vault…</p>
      </div>
    );
  }

  return (
    <div className="card-d2">
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
            const colorText = qualityColor(item.quality).split(" ")[0];
            const displayName = item.name ?? item.base_item ?? qualityLabel(item.quality);
            const date = fmtUtcDate(item.stored_at);
            return (
              <div key={item.id} className="px-4 py-2.5">
                <div className="flex items-center gap-2">
                  <span className={`text-[9px] font-mono px-1 border shrink-0 leading-4 ${qualityColor(item.quality)}`}>
                    {qualityLabel(item.quality)}
                  </span>
                  <div className="flex-1 flex items-baseline gap-1.5 min-w-0">
                    <span className={`text-sm font-semibold leading-snug truncate ${colorText}`}>
                      {displayName}
                    </span>
                    {item.name && item.base_item && (
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
                  <CopyVaultHexButton itemId={item.id} />
                  <button
                    onClick={() => setRetrieveTarget(item)}
                    disabled={d2rRunning}
                    className="text-[11px] text-slate-600 hover:text-d2gold border border-slate-800 hover:border-d2gold px-2 py-0.5 transition-colors shrink-0 disabled:opacity-40 disabled:cursor-not-allowed"
                    title={d2rRunning ? "D2R is running — close the game first" : "Retrieve to tab 5"}
                  >
                    Retrieve
                  </button>
                </div>
                <div className="flex items-center gap-2 mt-0.5 ml-9">
                  <span className="text-slate-700 text-[10px]">Tab {item.tab + 1}</span>
                  <span className="text-slate-800 text-[10px]">·</span>
                  <span className="text-slate-700 text-[10px]">{date}</span>
                </div>
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
  const mode: Mode = "sc";
  const [activeTab, setActiveTab] = useState(0);

  const {
    data: stash,
    error: stashError,
  } = useStash(mode);

  // Derive write target from the active snapshot's source machine.
  // Since you always check in from the device you're playing on, this is always correct.
  const writeMachine: Machine = (stash?.machine === "deck" ? "deck" : "pc") as Machine;

  return (
    <div className="p-4 sm:p-6 max-w-4xl mx-auto animate-fadeIn space-y-6">
      {/* Header */}
      <div className="mb-1">
        <h1 className="font-diablo text-d2gold text-2xl tracking-widest">Item Vault</h1>
        <p className="text-slate-500 text-sm mt-1">Latest snapshot view, unlimited gold storage, and item archival</p>
        <div className="mt-2">
          <SeasonBanner />
        </div>
      </div>

      {/* Snapshot source info */}
      {stash?.snapshot_at && (
        <p className="text-slate-600 text-xs -mt-3">
          Snapshot from {stash.machine === "pc" ? "Windows PC" : "Steam Deck"} · {fmtRelative(stash.snapshot_at)}
        </p>
      )}

      {/* Error */}
      {stashError && (
        <div className="bg-red-950/30 border border-red-800/50 px-4 py-3">
          <p className="text-red-400 text-xs">
            {(stashError as any).response?.data?.detail ?? (stashError as Error).message}
          </p>
        </div>
      )}

      {/* Stash view */}
      {stash && !stashError && (
        <>
          <GoldPanel
            stashGold={stash.gold}
            vaultGold={stash.vault_gold}
            machine={writeMachine}
            mode={mode}
          />
          <StashTabView
            tabs={stash.tabs}
            machine={writeMachine}
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
