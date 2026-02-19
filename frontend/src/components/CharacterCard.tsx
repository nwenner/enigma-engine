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
      className={`bg-d2bg-elevated border rounded p-3 flex items-start gap-3 transition-colors ${
        isNewer
          ? "border-d2gold shadow-md shadow-d2gold/10"
          : "border-d2bg-border"
      }`}
    >
      <span className="text-2xl leading-none mt-0.5">{icon}</span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-semibold text-amber-100 truncate">{character.name}</span>
          {character.hardcore && (
            <span className="text-xs bg-red-900/60 text-red-300 px-1.5 py-0.5 rounded border border-red-800">
              HC
            </span>
          )}
          {character.hardcore && character.ever_died && (
            <span className="text-xs bg-gray-800 text-gray-400 px-1.5 py-0.5 rounded border border-gray-700 line-through">
              RIP
            </span>
          )}
          {isNewer && (
            <span className="text-xs bg-d2gold/20 text-d2gold px-1.5 py-0.5 rounded border border-d2gold/40">
              newer
            </span>
          )}
        </div>
        <div className="text-sm text-amber-400 mt-0.5">
          {character.class_name} · Lvl {character.level}
        </div>
        <div className="text-xs text-amber-700 mt-0.5">
          {new Date(character.modified_at * 1000).toLocaleString()}
        </div>
      </div>
    </div>
  );
}
