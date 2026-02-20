import type { CharacterInfo } from "../api/types";

const CLASS_ICONS: Record<number, string> = {
  0: "🏹", // Amazon
  1: "🔥", // Sorceress
  2: "💀", // Necromancer
  3: "🛡️", // Paladin
  4: "⚔️", // Barbarian
  5: "🌿", // Druid
  6: "🗡️", // Assassin
  7: "🔮", // Warlock
};

interface Props {
  character: CharacterInfo;
  newerOn?: "pc" | "deck" | null;
}

export default function CharacterCard({ character, newerOn }: Props) {
  const icon = CLASS_ICONS[character.class_id] ?? "🎮";
  const isNewer = newerOn === character.source;

  return (
    <div
      className={`p-3 flex items-start gap-3 transition-all duration-200 ${
        isNewer
          ? "bg-d2bg-elevated border border-d2gold/40 shadow-md shadow-d2gold/8"
          : "bg-d2bg-elevated border border-d2bg-border hover:border-slate-600"
      }`}
    >
      <span className="text-2xl leading-none mt-0.5 opacity-90">{icon}</span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-semibold text-slate-100 truncate">{character.name}</span>
          {character.hardcore && (
            <span className="text-[10px] bg-red-950/60 text-red-400 px-1.5 py-0.5 border border-red-900/80 tracking-wide">
              HC
            </span>
          )}
          {character.hardcore && character.ever_died && (
            <span className="text-[10px] bg-slate-800/60 text-slate-500 px-1.5 py-0.5 border border-slate-700 line-through">
              RIP
            </span>
          )}
          {isNewer && (
            <span className="text-[10px] bg-d2gold/10 text-d2gold px-1.5 py-0.5 border border-d2gold/30 tracking-wide">
              newer
            </span>
          )}
        </div>
        <div className="text-sm text-slate-400 mt-0.5">
          {character.class_name} · Lvl {character.level}
        </div>
        <div className="text-xs text-slate-600 mt-0.5">
          {new Date(character.modified_at * 1000).toLocaleString()}
        </div>
      </div>
    </div>
  );
}
