import { useState } from "react";
import { useCharacters } from "../api/hooks";
import type { CharacterInfo } from "../api/types";

const CLASS_ICONS: Record<number, string> = {
  0: "🏹", 1: "🔥", 2: "💀", 3: "🛡️", 4: "⚔️", 5: "🌿", 6: "🗡️", 7: "🔮",
};

type SortKey = "name" | "level" | "class_name" | "source" | "modified_at";

export default function Characters() {
  const [source, setSource] = useState<"all" | "pc" | "deck">("all");
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("name");
  const [sortAsc, setSortAsc] = useState(true);

  const { data: chars, isLoading, error, refetch } = useCharacters(source);

  const filtered = (chars ?? [])
    .filter((c) =>
      search === "" ||
      c.name.toLowerCase().includes(search.toLowerCase()) ||
      c.class_name.toLowerCase().includes(search.toLowerCase())
    )
    .sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      const cmp = typeof av === "number" && typeof bv === "number"
        ? av - bv
        : String(av).localeCompare(String(bv));
      return sortAsc ? cmp : -cmp;
    });

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortAsc((v) => !v);
    else { setSortKey(key); setSortAsc(true); }
  };

  const SortIcon = ({ k }: { k: SortKey }) =>
    sortKey === k ? (sortAsc ? " ↑" : " ↓") : "";

  return (
    <div className="p-6 max-w-5xl mx-auto animate-fadeIn">
      <div className="flex items-center justify-between mb-7">
        <div>
          <h1 className="font-diablo text-d2gold text-2xl tracking-widest">Characters</h1>
        </div>
        <button onClick={() => refetch()} className="btn-d2-ghost text-xs px-3 py-1.5">
          Refresh
        </button>
      </div>

      {/* Filters */}
      <div className="flex gap-3 mb-5 flex-wrap">
        <input
          type="text"
          placeholder="Search name or class..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="input-d2 w-56"
        />
        <div className="flex gap-1">
          {(["all", "pc", "deck"] as const).map((s) => (
            <button
              key={s}
              onClick={() => setSource(s)}
              className={`px-3 py-1.5 text-sm transition-all duration-150 border ${
                source === s
                  ? "bg-d2gold/15 text-d2gold border-d2gold/50"
                  : "bg-d2bg-elevated text-slate-400 border-d2bg-border hover:border-slate-600 hover:text-slate-200"
              }`}
            >
              {s === "all" ? "All" : s === "pc" ? "PC" : "Steam Deck"}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="bg-red-950/30 border border-red-800/50 p-3 text-red-400 text-sm mb-4">
          Error loading characters
        </div>
      )}

      <div className="card-d2 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-d2bg-border">
              {[
                { key: "name" as SortKey, label: "Name", align: "left" },
                { key: "class_name" as SortKey, label: "Class", align: "left" },
                { key: "level" as SortKey, label: "Level", align: "right" },
                { key: null, label: "Flags", align: "center" },
                { key: "source" as SortKey, label: "Machine", align: "left" },
                { key: "modified_at" as SortKey, label: "Last Modified", align: "left" },
              ].map(({ key, label, align }) => (
                <th
                  key={label}
                  className={`text-${align} px-4 py-3 text-slate-500 font-medium text-xs tracking-wider uppercase ${
                    key ? "cursor-pointer hover:text-d2gold select-none transition-colors" : ""
                  }`}
                  onClick={() => key && toggleSort(key)}
                >
                  {label}{key ? <SortIcon k={key} /> : ""}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td colSpan={6} className="text-center py-10 text-slate-500">
                  Loading characters...
                </td>
              </tr>
            )}
            {!isLoading && filtered.length === 0 && (
              <tr>
                <td colSpan={6} className="text-center py-10 text-slate-500">
                  No characters found
                </td>
              </tr>
            )}
            {filtered.map((c) => (
              <CharacterRow key={`${c.source}-${c.filename}`} char={c} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function CharacterRow({ char }: { char: CharacterInfo }) {
  return (
    <tr className="border-b border-d2bg-border/50 hover:bg-d2bg-elevated/40 transition-colors">
      <td className="px-4 py-3 font-medium text-slate-100">{char.name}</td>
      <td className="px-4 py-3 text-slate-300">
        <span className="mr-1.5">{CLASS_ICONS[char.class_id] ?? "🎮"}</span>
        {char.class_name}
      </td>
      <td className="px-4 py-3 text-right text-slate-300 font-mono tabular-nums">{char.level}</td>
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
      <td className="px-4 py-3">
        <span className={`text-[10px] px-2 py-0.5 border tracking-wide ${
          char.source === "pc"
            ? "bg-violet-950/40 text-violet-400 border-violet-900/60"
            : "bg-cyan-950/40 text-cyan-400 border-cyan-900/60"
        }`}>
          {char.source === "pc" ? "PC" : "Deck"}
        </span>
      </td>
      <td className="px-4 py-3 text-slate-500 text-xs tabular-nums">
        {new Date(char.modified_at * 1000).toLocaleString()}
      </td>
    </tr>
  );
}
