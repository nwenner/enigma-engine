import { Routes, Route, NavLink, Navigate } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import Characters from "./pages/Characters";
import Backups from "./pages/Backups";
import History from "./pages/History";
import Settings from "./pages/Settings";
import { usePreflight } from "./api/hooks";

const NAV_ITEMS = [
  { to: "/", label: "Dashboard", icon: "⚔️" },
  { to: "/characters", label: "Characters", icon: "🧙" },
  { to: "/backups", label: "Backups", icon: "💾" },
  { to: "/history", label: "History", icon: "📜" },
  { to: "/settings", label: "Settings", icon: "⚙️" },
];

function StatusDot({ online }: { online: boolean | null }) {
  if (online === null) {
    return <span className="w-1.5 h-1.5 rounded-full bg-slate-600 inline-block shrink-0" />;
  }
  return online ? (
    <span className="relative inline-flex shrink-0">
      <span className="w-1.5 h-1.5 rounded-full bg-green-400 inline-block" />
      <span className="absolute inset-0 w-1.5 h-1.5 rounded-full bg-green-400 animate-ping opacity-60" />
    </span>
  ) : (
    <span className="w-1.5 h-1.5 rounded-full bg-red-600 inline-block shrink-0" />
  );
}

function ConnectionStatus() {
  const { data, isLoading } = usePreflight();
  const pcOnline = data ? data.pc_error === null : null;
  const deckOnline = data ? data.deck_error === null : null;

  return (
    <div className="px-4 py-3 border-t border-d2bg-border space-y-2">
      <p className="text-slate-600 text-[10px] uppercase tracking-widest mb-1">Devices</p>
      <div className="flex items-center gap-2">
        <StatusDot online={isLoading ? null : pcOnline} />
        <span className="text-xs text-slate-500">Windows PC</span>
      </div>
      <div className="flex items-center gap-2">
        <StatusDot online={isLoading ? null : deckOnline} />
        <span className="text-xs text-slate-500">Steam Deck</span>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <div className="flex min-h-screen">
      {/* Sidebar */}
      <nav
        className="w-52 shrink-0 flex flex-col border-r border-d2bg-border"
        style={{ background: "linear-gradient(180deg, #0d0f14 0%, #0b0d11 100%)" }}
      >
        {/* Branding */}
        <div className="px-5 py-6 border-b border-d2bg-border">
          <h1 className="font-diablo text-d2gold text-base tracking-widest leading-tight">
            Enigma Engine
          </h1>
          <p className="text-slate-600 text-[10px] tracking-widest uppercase mt-1">
            D2R Save Sync
          </p>
        </div>

        {/* Nav */}
        <div className="flex flex-col gap-0.5 p-3 flex-1">
          {NAV_ITEMS.map(({ to, label, icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              className={({ isActive }) =>
                `group flex items-center gap-3 px-3 py-2.5 text-sm transition-all duration-150 ${
                  isActive
                    ? "bg-d2bg-elevated text-d2gold border-l-2 border-d2gold pl-[10px]"
                    : "text-slate-500 hover:text-slate-200 hover:bg-d2bg-elevated/60 border-l-2 border-transparent pl-[10px]"
                }`
              }
            >
              {({ isActive }) => (
                <>
                  <span className={`text-base transition-all duration-150 ${isActive ? "" : "opacity-60 group-hover:opacity-100"}`}>
                    {icon}
                  </span>
                  <span className="tracking-wide">{label}</span>
                </>
              )}
            </NavLink>
          ))}
        </div>

        <ConnectionStatus />

        {/* Version */}
        <div className="p-3 border-t border-d2bg-border">
          <p className="text-slate-700 text-[10px] text-center tracking-widest">v1.0.0</p>
        </div>
      </nav>

      {/* Main content */}
      <main
        className="flex-1 overflow-auto"
        style={{
          backgroundColor: "#0c0e12",
          backgroundImage: [
            // Circular vignette — listed first so it renders on top of the grid
            "radial-gradient(ellipse 58% 80% at 50% 44%, transparent 0%, rgba(12,14,18,0.72) 50%, rgba(12,14,18,0.99) 82%)",
            // Vertical lines (0°)
            "repeating-linear-gradient(0deg,  rgba(255,255,255,0.03) 0px, rgba(255,255,255,0.03) 1px, transparent 1px, transparent 40px)",
            // Horizontal lines (90°)
            "repeating-linear-gradient(90deg, rgba(255,255,255,0.03) 0px, rgba(255,255,255,0.03) 1px, transparent 1px, transparent 40px)",
          ].join(", "),
          // Inset shadow pins an additional vignette to the viewport edges as content scrolls
          boxShadow: "inset 0 0 200px rgba(12,14,18,0.98)",
        }}
      >
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/characters" element={<Characters />} />
          <Route path="/backups" element={<Backups />} />
          <Route path="/history" element={<History />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
