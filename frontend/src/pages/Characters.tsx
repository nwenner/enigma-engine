import { useState } from "react";
import { useCharacters, useRefreshCharacters } from "../api/hooks";
import type { CharacterInfo } from "../api/types";

const CLASS_ICONS: Record<number, string> = {
  0: "🏹", 1: "🔥", 2: "💀", 3: "🛡️", 4: "⚔️", 5: "🌿", 6: "🗡️", 7: "🔮",
};

type SortKey = "name" | "level" | "class_name" | "modified_at";

export default function Characters() {
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("modified_at");
  const [sortAsc, setSortAsc] = useState(false);

  const { data: chars, isLoading, error } = useCharacters();
  const refresh = useRefreshCharacters();

  const filtered = (chars ?? [])
    .filter(
      (c) =>
        search === "" ||
        c.name.toLowerCase().includes(search.toLowerCase()) ||
        c.class_name.toLowerCase().includes(search.toLowerCase())
    )
    .sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      const cmp =
        typeof av === "number" && typeof bv === "number"
          ? av - bv
          : String(av).localeCompare(String(bv));
      return sortAsc ? cmp : -cmp;
    });

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortAsc((v) => !v);
    else {
      setSortKey(key);
      setSortAsc(true);
    }
  };

  const SortIcon = ({ k }: { k: SortKey }) =>
    sortKey === k ? (sortAsc ? " ↑" : " ↓") : "";

  return (
    <div className="p-4 sm:p-6 max-w-5xl mx-auto animate-fadeIn">
      <div className="flex items-center justify-between mb-7">
        <div>
          <h1 className="font-diablo text-d2gold text-2xl tracking-widest">Characters</h1>
        </div>
        <button
          onClick={() => refresh.mutate()}
          disabled={refresh.isPending}
          className="btn-d2-ghost text-xs px-3 py-1.5"
        >
          {refresh.isPending ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      {/* Search */}
      <div className="mb-5">
        <input
          type="text"
          placeholder="Search name or class..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="input-d2 w-full sm:w-56"
        />
      </div>

      {error && (
        <div className="bg-red-950/30 border border-red-800/50 p-3 text-red-400 text-sm mb-4">
          Error loading characters
        </div>
      )}

      {refresh.error && (
        <div className="bg-red-950/30 border border-red-800/50 p-3 text-red-400 text-sm mb-4">
          Refresh failed — one or more machines may be offline
        </div>
      )}

      {/* Mobile card list */}
      <div className="md:hidden space-y-2">
        {isLoading && (
          <div className="text-slate-500 text-sm py-8 text-center">Loading characters...</div>
        )}
        {!isLoading && filtered.length === 0 && (
          <div className="text-slate-500 text-sm py-8 text-center">No characters found</div>
        )}
        {filtered.map((c) => (
          <CharacterMobileCard
            key={c.filename}
            char={c}
          />
        ))}
      </div>

      {/* Desktop table */}
      <div className="hidden md:block card-d2 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-d2bg-border">
              {[
                { key: "name" as SortKey, label: "Name", align: "left" },
                { key: "class_name" as SortKey, label: "Class", align: "left" },
                { key: "level" as SortKey, label: "Level", align: "right" },
                { key: null, label: "Flags", align: "center" },
                { key: "modified_at" as SortKey, label: "Last Modified", align: "left" },
              ].map(({ key, label, align }) => (
                <th
                  key={label}
                  className={`text-${align} px-4 py-3 text-slate-500 font-medium text-xs tracking-wider uppercase ${
                    key ? "cursor-pointer hover:text-d2gold select-none transition-colors" : ""
                  }`}
                  onClick={() => key && toggleSort(key)}
                >
                  {label}
                  {key ? <SortIcon k={key} /> : ""}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td colSpan={5} className="text-center py-10 text-slate-500">
                  Loading characters...
                </td>
              </tr>
            )}
            {!isLoading && filtered.length === 0 && (
              <tr>
                <td colSpan={5} className="text-center py-10 text-slate-500">
                  No characters found
                </td>
              </tr>
            )}
            {filtered.map((c) => (
              <CharacterRow
                key={c.filename}
                char={c}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function CharacterMobileCard({
  char,
}: {
  char: CharacterInfo;
}) {
  return (
    <div className="card-d2 p-3 flex items-center gap-3">
      <span className="text-xl leading-none shrink-0">{CLASS_ICONS[char.class_id] ?? "🎮"}</span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="font-medium text-slate-100 text-sm truncate">{char.name}</span>
          {char.hardcore && (
            <span className="text-[10px] bg-red-950/60 text-red-400 px-1.5 py-0.5 border border-red-900/80">
              HC
            </span>
          )}
        </div>
        <div className="text-xs text-slate-400 mt-0.5">
          {char.class_name} · Lvl {char.level}
        </div>
      </div>
      <div className="text-xs text-slate-500 tabular-nums shrink-0">
        {new Date(char.modified_at * 1000).toLocaleDateString()}
      </div>
    </div>
  );
}

function CharacterRow({
  char,
}: {
  char: CharacterInfo;
}) {
  return (
    <tr className="border-b border-d2bg-border/50 hover:bg-d2bg-elevated/40 transition-colors">
      <td className="px-4 py-3 font-medium text-slate-100">{char.name}</td>
      <td className="px-4 py-3 text-slate-300">
        <span className="mr-1.5">{CLASS_ICONS[char.class_id] ?? "🎮"}</span>
        {char.class_name}
      </td>
      <td className="px-4 py-3 text-right text-slate-300 font-mono tabular-nums">
        {char.level}
      </td>
      <td className="px-4 py-3 text-center">
        <span className="flex gap-1 justify-center">
          {char.hardcore && (
            <span className="text-[10px] bg-red-950/60 text-red-400 px-1.5 py-0.5 border border-red-900/80">
              HC
            </span>
          )}
          {char.expansion && (
            <span className="text-[10px] bg-blue-950/50 text-blue-400 px-1.5 py-0.5 border border-blue-900/70">
              LOD
            </span>
          )}
        </span>
      </td>
      <td className="px-4 py-3 text-slate-500 text-xs tabular-nums">
        {new Date(char.modified_at * 1000).toLocaleString()}
      </td>
    </tr>
  );
}
