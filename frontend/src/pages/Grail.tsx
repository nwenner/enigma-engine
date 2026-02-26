import { useState, useRef, useMemo } from "react";
import {
  useGrailProgress,
  useSeedCatalog,
  useRetrieveGrailItem,
  useUnmarkGrailEntry,
  useDepositTab5,
  useResetGrail,
  usePreflight,
} from "../api/hooks";
import type { GrailItem } from "../api/types";

type Mode = "sc" | "hc";
type QualityFilter = "all" | "unique" | "set";
type FoundFilter = "all" | "found" | "missing";

// ─── Progress bar ─────────────────────────────────────────────────────────────

function ProgressBar({ found, total, label }: { found: number; total: number; label: string }) {
  const pct = total > 0 ? (found / total) * 100 : 0;
  return (
    <div className="flex items-center gap-3">
      <span className="text-slate-400 text-xs w-20 shrink-0">{label}</span>
      <div className="flex-1 h-1.5 bg-d2bg-elevated rounded-none overflow-hidden">
        <div
          className="h-full bg-d2gold/70 transition-all duration-300"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-slate-500 text-xs w-16 text-right shrink-0">
        {found} / {total}
      </span>
    </div>
  );
}

// ─── Retrieve modal ───────────────────────────────────────────────────────────

function RetrieveModal({
  item,
  mode,
  onClose,
  d2rRunning,
}: {
  item: GrailItem;
  mode: Mode;
  onClose: () => void;
  d2rRunning: boolean;
}) {
  const retrieve = useRetrieveGrailItem();
  const [machine, setMachine] = useState<"pc" | "deck">("pc");

  const handleRetrieve = async () => {
    try {
      await retrieve.mutateAsync({ mode, catalogId: item.catalog_id, machine });
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
          {item.name} will be written to stash tab 5 on the selected machine.
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

        {d2rRunning && (
          <p className="text-amber-400 text-xs mb-3 bg-amber-950/30 border border-amber-800/40 px-3 py-2">
            ⚠ Close D2R before retrieving items
          </p>
        )}

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
            disabled={retrieve.isPending || d2rRunning}
            className="btn-d2 text-xs px-4 py-2"
          >
            {retrieve.isPending ? "Retrieving…" : "Retrieve"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Item row ─────────────────────────────────────────────────────────────────

function ItemRow({
  item,
  onRetrieve,
  onUnmark,
}: {
  item: GrailItem;
  onRetrieve: (item: GrailItem) => void;
  onUnmark: (item: GrailItem) => void;
}) {
  return (
    <div
      className={`flex items-center gap-3 px-3 py-2 border-b border-d2bg-border/50 last:border-0 ${
        item.found ? "" : "opacity-50"
      }`}
    >
      <div className="flex-1 min-w-0">
        <span className={`text-sm ${item.found ? "text-slate-200" : "text-slate-500"}`}>
          {item.name}
        </span>
        <span className="text-slate-600 text-xs ml-2">{item.base_item}</span>
      </div>

      {item.found ? (
        <div className="flex items-center gap-2 shrink-0">
          <span className={`text-xs tracking-wide ${item.is_deposited ? "text-green-500" : "text-amber-500"}`}>
            {item.is_deposited ? "✓ deposited" : "⊙ detected"}
          </span>
          {item.find_count > 1 && (
            <span className="text-slate-600 text-xs">×{item.find_count}</span>
          )}
          {item.is_deposited ? (
            <button
              onClick={() => onRetrieve(item)}
              className="text-[11px] text-slate-600 hover:text-d2gold border border-slate-800 hover:border-d2gold px-2 py-0.5 transition-colors"
              title="Retrieve this item to tab 5"
            >
              Request
            </button>
          ) : (
            <span className="text-[11px] text-slate-600 px-2 py-0.5" title="Deposit tab 5 to enable retrieval">
              In tab 5
            </span>
          )}
          <button
            onClick={() => onUnmark(item)}
            className="text-[11px] text-slate-600 hover:text-red-400 transition-colors px-1"
            title="Unmark (admin)"
          >
            ✕
          </button>
        </div>
      ) : (
        <span className="text-slate-600 text-xs shrink-0">missing</span>
      )}
    </div>
  );
}

// ─── Set group ────────────────────────────────────────────────────────────────

function SetGroup({
  setName,
  items,
  onRetrieve,
  onUnmark,
}: {
  setName: string;
  items: GrailItem[];
  onRetrieve: (item: GrailItem) => void;
  onUnmark: (item: GrailItem) => void;
}) {
  const found = items.filter((i) => i.found).length;
  return (
    <div className="mb-2">
      <div className="flex items-center gap-2 px-3 py-1.5 bg-d2bg-elevated/40 border-b border-d2bg-border">
        <span className="text-slate-400 text-xs font-medium">{setName}</span>
        <span className="text-slate-600 text-xs ml-auto">
          {found}/{items.length}
        </span>
      </div>
      {items.map((item) => (
        <ItemRow key={item.catalog_id} item={item} onRetrieve={onRetrieve} onUnmark={onUnmark} />
      ))}
    </div>
  );
}

// ─── Deposit panel ────────────────────────────────────────────────────────────

function DepositPanel({ d2rRunning }: { d2rRunning: boolean }) {
  const deposit = useDepositTab5();
  const [machine, setMachine] = useState<"pc" | "deck">("pc");
  const [result, setResult] = useState<{
    registered: string[];
    errors: string[];
  } | null>(null);

  const handleDeposit = async () => {
    setResult(null);
    try {
      const res = await deposit.mutateAsync({ machine });
      setResult({ registered: res.registered, errors: res.errors });
    } catch {
      // error shown via deposit.error
    }
  };

  return (
    <div className="card-d2 p-4 mb-4">
      <h2 className="font-diablo text-d2gold text-sm tracking-widest mb-1">Deposit Tab 5</h2>
      <p className="text-slate-500 text-xs mb-4 leading-relaxed">
        Register unique and set items from stash tab 5 into your grail, then clear that tab.
        D2R must not be running.
      </p>

      <div className="flex gap-2 mb-4">
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

      {d2rRunning && (
        <div className="text-amber-400 text-xs mb-3 bg-amber-950/30 border border-amber-800/40 px-3 py-2">
          ⚠ Close D2R before depositing items
        </div>
      )}

      <button
        onClick={handleDeposit}
        disabled={deposit.isPending || d2rRunning}
        className="btn-d2 text-xs px-4 py-2 w-full"
      >
        {deposit.isPending ? "Depositing…" : "Deposit Items"}
      </button>

      {deposit.error && (
        <p className="text-red-400 text-xs mt-3 bg-red-950/30 border border-red-800/40 px-3 py-2">
          {deposit.error.message}
        </p>
      )}

      {result && (
        <div className="mt-3 space-y-1">
          {result.registered.length > 0 ? (
            <p className="text-green-400 text-xs">
              Registered: {result.registered.join(", ")}
            </p>
          ) : (
            <p className="text-slate-500 text-xs">No new items found in tab 5.</p>
          )}
          {result.errors.map((e, i) => (
            <p key={i} className="text-red-400 text-xs">{e}</p>
          ))}
        </div>
      )}
    </div>
  );
}


// ─── Seed panel ───────────────────────────────────────────────────────────────

function SeedPanel() {
  const seed = useSeedCatalog();
  const fileRef = useRef<HTMLInputElement>(null);
  const [expanded, setExpanded] = useState(false);
  const [result, setResult] = useState<string | null>(null);

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setResult(null);
    try {
      const res = await seed.mutateAsync(file);
      setResult(`Seeded ${res.count} items successfully.`);
    } catch (err: unknown) {
      setResult(`Error: ${err instanceof Error ? err.message : String(err)}`);
    }
    if (fileRef.current) fileRef.current.value = "";
  };

  return (
    <div className="mt-6 border border-d2bg-border">
      <button
        onClick={() => setExpanded((x) => !x)}
        className="w-full flex items-center justify-between px-4 py-3 text-slate-500 hover:text-slate-300 transition-colors text-sm"
      >
        <span>Seed Catalog</span>
        <span>{expanded ? "▾" : "▸"}</span>
      </button>

      {expanded && (
        <div className="px-4 pb-4 border-t border-d2bg-border">
          <p className="text-slate-500 text-xs mt-3 mb-3 leading-relaxed">
            Upload a JSON array of catalog items. This replaces the existing catalog and all grail entries.
          </p>
          <input
            ref={fileRef}
            type="file"
            accept=".json"
            onChange={handleFile}
            className="hidden"
            id="grail-seed-input"
          />
          <label
            htmlFor="grail-seed-input"
            className={`btn-d2-ghost text-xs px-4 py-2 cursor-pointer inline-block ${
              seed.isPending ? "opacity-50 pointer-events-none" : ""
            }`}
          >
            {seed.isPending ? "Uploading…" : "Upload grail_catalog.json"}
          </label>
          {result && (
            <p
              className={`text-xs mt-2 ${
                result.startsWith("Error") ? "text-red-400" : "text-green-400"
              }`}
            >
              {result}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Reset panel ──────────────────────────────────────────────────────────────

function ResetPanel() {
  const reset = useResetGrail();
  const [expanded, setExpanded] = useState(false);
  const [result, setResult] = useState<string | null>(null);

  const handleReset = async () => {
    if (!confirm("Delete ALL grail entries (SC + HC)? This cannot be undone. The catalog will remain intact.")) {
      return;
    }
    setResult(null);
    try {
      const res = await reset.mutateAsync();
      setResult(`✓ Deleted ${res.deleted} entries. Catalog intact.`);
    } catch (err: unknown) {
      setResult(`Error: ${err instanceof Error ? err.message : String(err)}`);
    }
  };

  return (
    <div className="mt-2 border border-d2bg-border">
      <button
        onClick={() => setExpanded((x) => !x)}
        className="w-full flex items-center justify-between px-4 py-3 text-slate-500 hover:text-slate-300 transition-colors text-sm"
      >
        <span>Reset Grail</span>
        <span>{expanded ? "▾" : "▸"}</span>
      </button>

      {expanded && (
        <div className="px-4 pb-4 border-t border-d2bg-border">
          <p className="text-slate-500 text-xs mt-3 mb-3 leading-relaxed">
            Delete all found items (both SC and HC). The catalog remains intact. Use this to start fresh if items were incorrectly registered.
          </p>
          <button
            onClick={handleReset}
            disabled={reset.isPending}
            className="btn-d2-ghost text-xs px-4 py-2 text-red-400 hover:text-red-300 border-red-800/40 hover:border-red-700/60"
          >
            {reset.isPending ? "Resetting…" : "Reset All Entries"}
          </button>
          {result && (
            <p
              className={`text-xs mt-2 ${
                result.startsWith("Error") ? "text-red-400" : "text-green-400"
              }`}
            >
              {result}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function Grail() {
  const [mode, setMode] = useState<Mode>("sc");
  const [qualityFilter, setQualityFilter] = useState<QualityFilter>("all");
  const [foundFilter, setFoundFilter] = useState<FoundFilter>("found");
  const [search, setSearch] = useState("");
  const [retrieveItem, setRetrieveItem] = useState<GrailItem | null>(null);
  const unmark = useUnmarkGrailEntry();

  const { data, isLoading, error } = useGrailProgress(mode);
  const { data: preflight } = usePreflight();
  const d2rRunning = preflight?.pc_running === true || preflight?.deck_running === true;

  const filteredItems = useMemo(() => {
    if (!data) return [];
    return data.items.filter((item) => {
      if (qualityFilter !== "all" && item.quality !== qualityFilter) return false;
      if (foundFilter === "found" && !item.found) return false;
      if (foundFilter === "missing" && item.found) return false;
      if (search) {
        const q = search.toLowerCase();
        if (
          !item.name.toLowerCase().includes(q) &&
          !item.base_item.toLowerCase().includes(q) &&
          !(item.set_name?.toLowerCase().includes(q))
        ) {
          return false;
        }
      }
      return true;
    });
  }, [data, qualityFilter, foundFilter, search]);

  const uniqueItems = filteredItems.filter((i) => i.quality === "unique");

  // Group set items by set_name
  const setGroups = useMemo(() => {
    const setItems = filteredItems.filter((i) => i.quality === "set");
    const groups: Record<string, GrailItem[]> = {};
    for (const item of setItems) {
      const key = item.set_name ?? "Unknown Set";
      if (!groups[key]) groups[key] = [];
      groups[key].push(item);
    }
    return groups;
  }, [filteredItems]);

  const handleUnmark = (item: GrailItem) => {
    if (confirm(`Unmark "${item.name}" as found? This cannot be undone.`)) {
      unmark.mutate({ mode, catalogId: item.catalog_id });
    }
  };

  return (
    <div className="p-4 sm:p-6 max-w-4xl mx-auto animate-fadeIn">
      {/* Header */}
      <div className="mb-6">
        <h1 className="font-diablo text-d2gold text-2xl tracking-widest">Holy Grail</h1>
        <p className="text-slate-500 text-sm mt-1">
          Track your Unique and Set item collection — place items in stash tab 5, then use Deposit to register and clear them
        </p>
      </div>

      {/* D2R Running Warning */}
      {d2rRunning && (
        <div className="bg-amber-950/30 border border-amber-700/50 text-amber-300 text-sm px-4 py-3 mb-5 flex items-center gap-3">
          <span className="text-lg">⚠</span>
          <div className="flex-1">
            <div className="font-medium mb-0.5">D2R is currently running</div>
            <div className="text-xs text-amber-400/80">Close the game before depositing or retrieving items</div>
          </div>
        </div>
      )}

      {/* Mode toggle */}
      <div className="flex gap-2 mb-5">
        {(["sc", "hc"] as const).map((m) => (
          <button
            key={m}
            onClick={() => setMode(m)}
            className={`text-xs px-5 py-2 border transition-colors ${
              mode === m
                ? "border-d2gold text-d2gold bg-d2gold/8"
                : "border-d2bg-border text-slate-500 hover:border-slate-500 hover:text-slate-300"
            }`}
          >
            {m === "sc" ? "Softcore" : "Hardcore"}
          </button>
        ))}
      </div>

      {/* Progress summary */}
      {data && (
        <div className="card-d2 p-4 mb-5 space-y-2">
          <ProgressBar found={data.unique_found} total={data.unique_total} label="Uniques" />
          <ProgressBar found={data.set_found} total={data.set_total} label="Set Items" />
        </div>
      )}

      {/* Deposit panel */}
      <DepositPanel d2rRunning={d2rRunning} />

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2 mb-4">
        {/* Quality filter */}
        <div className="flex border border-d2bg-border text-xs">
          {(["all", "unique", "set"] as const).map((q) => (
            <button
              key={q}
              onClick={() => setQualityFilter(q)}
              className={`px-3 py-1.5 capitalize transition-colors ${
                qualityFilter === q
                  ? "bg-d2bg-elevated text-slate-200"
                  : "text-slate-500 hover:text-slate-300"
              }`}
            >
              {q}
            </button>
          ))}
        </div>

        {/* Found filter */}
        <div className="flex border border-d2bg-border text-xs">
          {(["all", "found", "missing"] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFoundFilter(f)}
              className={`px-3 py-1.5 capitalize transition-colors ${
                foundFilter === f
                  ? "bg-d2bg-elevated text-slate-200"
                  : "text-slate-500 hover:text-slate-300"
              }`}
            >
              {f}
            </button>
          ))}
        </div>

        {/* Search */}
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search…"
          className="flex-1 min-w-32 bg-d2bg-elevated border border-d2bg-border text-slate-300 text-xs px-3 py-1.5 placeholder-slate-600 focus:outline-none focus:border-slate-500"
        />
      </div>

      {/* Loading / error / empty states */}
      {isLoading && (
        <div className="text-slate-500 text-sm text-center py-16">Loading grail…</div>
      )}

      {error && !isLoading && (
        <div className="text-slate-500 text-sm text-center py-16">Failed to load grail data</div>
      )}

      {!isLoading && !error && data && data.unique_total === 0 && data.set_total === 0 && (
        <div className="card-d2 p-8 text-center">
          <p className="text-slate-500 text-sm mb-2">No catalog items yet</p>
          <p className="text-slate-600 text-xs">
            Upload a catalog JSON file below to get started
          </p>
        </div>
      )}

      {/* Uniques section */}
      {!isLoading && uniqueItems.length > 0 && (qualityFilter === "all" || qualityFilter === "unique") && (
        <div className="card-d2 mb-4">
          <div className="px-4 py-3 border-b border-d2bg-border">
            <h2 className="font-diablo text-d2gold text-sm tracking-widest">
              Uniques
              <span className="text-slate-600 font-sans text-xs ml-2 font-normal">
                ({data?.unique_found}/{data?.unique_total})
              </span>
            </h2>
          </div>
          <div>
            {uniqueItems.map((item) => (
              <ItemRow
                key={item.catalog_id}
                item={item}
                onRetrieve={setRetrieveItem}
                onUnmark={handleUnmark}
              />
            ))}
          </div>
        </div>
      )}

      {/* Sets section */}
      {!isLoading && Object.keys(setGroups).length > 0 && (qualityFilter === "all" || qualityFilter === "set") && (
        <div className="card-d2 mb-4">
          <div className="px-4 py-3 border-b border-d2bg-border">
            <h2 className="font-diablo text-d2gold text-sm tracking-widest">
              Sets
              <span className="text-slate-600 font-sans text-xs ml-2 font-normal">
                ({data?.set_found}/{data?.set_total})
              </span>
            </h2>
          </div>
          <div>
            {Object.entries(setGroups)
              .sort(([a], [b]) => a.localeCompare(b))
              .map(([setName, items]) => (
                <SetGroup
                  key={setName}
                  setName={setName}
                  items={items}
                  onRetrieve={setRetrieveItem}
                  onUnmark={handleUnmark}
                />
              ))}
          </div>
        </div>
      )}

      {/* Seed panel */}
      <SeedPanel />

      {/* Reset panel */}
      <ResetPanel />

      {/* Retrieve modal */}
      {retrieveItem && (
        <RetrieveModal
          item={retrieveItem}
          mode={mode}
          onClose={() => setRetrieveItem(null)}
          d2rRunning={d2rRunning}
        />
      )}
    </div>
  );
}
