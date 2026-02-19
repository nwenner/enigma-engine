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

function ConnectionStatus() {
  const { data, isLoading } = usePreflight();

  const StatusDot = ({ online }: { online: boolean | null }) => {
    if (isLoading || online === null) {
      return <span className="w-2 h-2 rounded-full bg-amber-900 inline-block shrink-0" />;
    }
    return online
      ? <span className="w-2 h-2 rounded-full bg-green-500 inline-block shrink-0" title="Online" />
      : <span className="w-2 h-2 rounded-full bg-red-600 inline-block shrink-0" title="Offline" />;
  };

  const pcOnline = data ? data.pc_error === null : null;
  const deckOnline = data ? data.deck_error === null : null;

  return (
    <div className="px-4 py-2.5 border-t border-d2bg-border space-y-1.5">
      <div className="flex items-center gap-2">
        <StatusDot online={pcOnline} />
        <span className="text-xs text-amber-700">Windows PC</span>
      </div>
      <div className="flex items-center gap-2">
        <StatusDot online={deckOnline} />
        <span className="text-xs text-amber-700">Steam Deck</span>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <div className="flex min-h-screen">
      {/* Sidebar */}
      <nav className="w-52 shrink-0 bg-d2bg-surface border-r border-d2bg-border flex flex-col">
        <div className="px-4 py-5 border-b border-d2bg-border">
          <h1 className="text-d2gold font-bold text-xl tracking-wide">Enigma Engine</h1>
          <p className="text-amber-700 text-xs mt-0.5">D2R Save Sync</p>
        </div>
        <div className="flex flex-col gap-1 p-3 flex-1">
          {NAV_ITEMS.map(({ to, label, icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              className={({ isActive }) =>
                `flex items-center gap-2.5 px-3 py-2 rounded text-sm transition-colors ${
                  isActive
                    ? "bg-d2bg-elevated text-d2gold border border-d2bg-border"
                    : "text-amber-300 hover:bg-d2bg-elevated hover:text-amber-100"
                }`
              }
            >
              <span>{icon}</span>
              <span>{label}</span>
            </NavLink>
          ))}
        </div>
        <ConnectionStatus />
        <div className="p-3 border-t border-d2bg-border">
          <p className="text-amber-800 text-xs text-center">v1.0.0</p>
        </div>
      </nav>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
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
