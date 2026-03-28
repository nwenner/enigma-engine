import { useState, useEffect } from "react";
import { Routes, Route, NavLink, Navigate, Link, useLocation } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import Characters from "./pages/Characters";
import Backups from "./pages/Backups";
import History from "./pages/History";
import Settings from "./pages/Settings";
import Grail from "./pages/Grail";
import Stash from "./pages/Stash";
import Seasons from "./pages/Seasons";
import Rewards from "./pages/Rewards";
import Demon from "./pages/Demon";
import Seeds from "./pages/Seeds";
import BossPortals from "./pages/BossPortals";
import { usePreflight, useSyncToasts } from "./api/hooks";
import { useEventStream } from "./api/useEventStream";
import { Toaster } from "sonner";

const NAV_ITEMS = [
  { to: "/", label: "Dashboard", icon: "⚔️" },
  { to: "/characters", label: "Characters", icon: "🧙" },
  { to: "/backups", label: "Backups", icon: "💾" },
  { to: "/history", label: "History", icon: "📜" },
  { to: "/grail", label: "Holy Grail", icon: "🏆" },
  { to: "/stash", label: "Item Vault", icon: "🏺" },
  { to: "/demon", label: "Demon Registry", icon: "👹" },
  { to: "/seeds", label: "Map Seeds", icon: "🗺️" },
  { to: "/portals", label: "Boss Portals", icon: "🌀" },
  { to: "/seasons", label: "Seasons", icon: "🗓️" },
  { to: "/rewards", label: "Reward Library", icon: "🎁" },
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
  const { data, isLoading } = usePreflight(60_000);
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

const SIDEBAR_BG = "linear-gradient(180deg, #0d0f14 0%, #0b0d11 100%)";

export default function App() {
  useEventStream();
  useSyncToasts();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const location = useLocation();

  // Close sidebar on navigation
  useEffect(() => {
    setSidebarOpen(false);
  }, [location.pathname]);

  return (
    <div className="flex h-screen overflow-hidden">
      <Toaster position="bottom-right" richColors />
      {/* Mobile backdrop */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/60 md:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar — fixed off-canvas on mobile, static on desktop */}
      <nav
        className={`fixed inset-y-0 left-0 z-40 w-52 flex flex-col border-r border-d2bg-border
          transition-transform duration-200 ease-in-out
          md:relative md:translate-x-0 md:shrink-0
          ${sidebarOpen ? "translate-x-0" : "-translate-x-full"}`}
        style={{ background: SIDEBAR_BG }}
      >
        {/* Branding */}
        <Link to="/" className="block px-5 py-6 border-b border-d2bg-border hover:bg-white/5 transition-colors">
          <h1 className="font-diablo text-d2gold text-base tracking-widest leading-tight">
            Enigma Engine
          </h1>
          <p className="text-slate-600 text-[10px] tracking-widest uppercase mt-1">
            D2R Season Manager
          </p>
        </Link>

        {/* Nav */}
        <div className="flex flex-col gap-0.5 p-3 flex-1 overflow-y-auto">
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

      {/* Content wrapper */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Mobile header */}
        <header
          className="md:hidden flex items-center gap-3 px-4 py-3 border-b border-d2bg-border shrink-0"
          style={{ background: SIDEBAR_BG }}
        >
          <button
            onClick={() => setSidebarOpen(true)}
            className="text-slate-400 hover:text-slate-200 transition-colors p-1 -ml-1"
            aria-label="Open menu"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="square" strokeLinejoin="miter" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
          <h1 className="font-diablo text-d2gold text-sm tracking-widest leading-tight">
            Enigma Engine
          </h1>
        </header>

        {/* Main content */}
        <main
          className="flex-1 overflow-auto"
          style={{
            backgroundColor: "#0c0e12",
            backgroundImage: [
              "radial-gradient(ellipse 58% 80% at 50% 44%, transparent 0%, rgba(12,14,18,0.72) 50%, rgba(12,14,18,0.99) 82%)",
              "repeating-linear-gradient(0deg,  rgba(255,255,255,0.03) 0px, rgba(255,255,255,0.03) 1px, transparent 1px, transparent 40px)",
              "repeating-linear-gradient(90deg, rgba(255,255,255,0.03) 0px, rgba(255,255,255,0.03) 1px, transparent 1px, transparent 40px)",
            ].join(", "),
            boxShadow: "inset 0 0 200px rgba(12,14,18,0.98)",
          }}
        >
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/characters" element={<Characters />} />
            <Route path="/backups" element={<Backups />} />
            <Route path="/history" element={<History />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="/grail" element={<Grail />} />
            <Route path="/stash" element={<Stash />} />
            <Route path="/seasons" element={<Seasons />} />
            <Route path="/rewards" element={<Rewards />} />
            <Route path="/demon" element={<Demon />} />
            <Route path="/seeds" element={<Seeds />} />
            <Route path="/portals" element={<BossPortals />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}
