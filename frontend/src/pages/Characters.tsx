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
    <div className="p-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-d2gold">Characters</h1>
        <button
          onClick={() => refetch()}
          className="text-sm text-amber-500 hover:text-amber-300 underline"
        >
          Refresh
        </button>
      </div>

      {/* Filters */}
      <div className="flex gap-3 mb-4 flex-wrap">
        <input
          type="text"
          placeholder="Search name or class..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="bg-d2bg-elevated border border-d2bg-border rounded px-3 py-1.5 text-sm text-amber-100 placeholder-amber-700 focus:outline-none focus:border-d2gold w-56"
        />
        <div className="flex gap-1">
          {(["all", "pc", "deck"] as const).map((s) => (
            <button
              key={s}
              onClick={() => setSource(s)}
              className={`px-3 py-1.5 text-sm rounded transition-colors ${
                source === s
                  ? "bg-d2gold text-d2bg font-bold"
                  : "bg-d2bg-elevated text-amber-400 border border-d2bg-border hover:border-d2gold/50"
              }`}
            >
              {s === "all" ? "All" : s === "pc" ? "PC" : "Steam Deck"}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="bg-red-950/50 border border-red-800 rounded p-3 text-red-300 text-sm mb-4">
          Error loading characters
        </div>
      )}

      <div className="bg-d2bg-surface border border-d2bg-border rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-d2bg-border text-amber-600">
              <th
                className="text-left px-4 py-2.5 cursor-pointer hover:text-d2gold select-none"
                onClick={() => toggleSort("name")}
              >
                Name<SortIcon k="name" />
              </th>
              <th
                className="text-left px-4 py-2.5 cursor-pointer hover:text-d2gold select-none"
                onClick={() => toggleSort("class_name")}
              >
                Class<SortIcon k="class_name" />
              </th>
              <th
                className="text-right px-4 py-2.5 cursor-pointer hover:text-d2gold select-none"
                onClick={() => toggleSort("level")}
              >
                Level<SortIcon k="level" />
              </th>
              <th className="text-center px-4 py-2.5">Flags</th>
              <th
                className="text-left px-4 py-2.5 cursor-pointer hover:text-d2gold select-none"
                onClick={() => toggleSort("source")}
              >
                Machine<SortIcon k="source" />
              </th>
              <th
                className="text-left px-4 py-2.5 cursor-pointer hover:text-d2gold select-none"
                onClick={() => toggleSort("modified_at")}
              >
                Last Modified<SortIcon k="modified_at" />
              </th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td colSpan={6} className="text-center py-8 text-amber-700">
                  Loading characters...
                </td>
              </tr>
            )}
            {!isLoading && filtered.length === 0 && (
              <tr>
                <td colSpan={6} className="text-center py-8 text-amber-700">
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
    <tr className="border-b border-d2bg-border/50 hover:bg-d2bg-elevated/50 transition-colors">
      <td className="px-4 py-2.5 font-medium text-amber-100">{char.name}</td>
      <td className="px-4 py-2.5 text-amber-300">
        <span className="mr-1.5">{CLASS_ICONS[char.class_id] ?? "🎮"}</span>
        {char.class_name}
      </td>
      <td className="px-4 py-2.5 text-right text-amber-300 font-mono">{char.level}</td>
      <td className="px-4 py-2.5 text-center">
        <span className="flex gap-1 justify-center">
          {char.hardcore && (
            <span className="text-xs bg-red-900/60 text-red-300 px-1.5 py-0.5 rounded border border-red-800">
              HC
            </span>
          )}
          {char.expansion && (
            <span className="text-xs bg-blue-900/40 text-blue-300 px-1.5 py-0.5 rounded border border-blue-800">
              LOD
            </span>
          )}
        </span>
      </td>
      <td className="px-4 py-2.5">
        <span className={`text-xs px-2 py-0.5 rounded border ${
          char.source === "pc"
            ? "bg-violet-900/40 text-violet-300 border-violet-800"
            : "bg-cyan-900/40 text-cyan-300 border-cyan-800"
        }`}>
          {char.source === "pc" ? "PC" : "Deck"}
        </span>
      </td>
      <td className="px-4 py-2.5 text-amber-600 text-xs">
        {new Date(char.modified_at * 1000).toLocaleString()}
      </td>
    </tr>
  );
}
