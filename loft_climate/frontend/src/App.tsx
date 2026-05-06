import { NavLink, Route, Routes } from "react-router-dom";

import { Dashboard } from "./routes/Dashboard";
import { Entry } from "./routes/Entry";
import { History } from "./routes/History";
import { Config } from "./routes/Config";
import { Simulate } from "./routes/Simulate";
import { Notifications } from "./routes/Notifications";

const NAV = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/entry", label: "Entry" },
  { to: "/history", label: "History" },
  { to: "/config", label: "Config" },
  { to: "/notifications", label: "Notifications" },
  { to: "/simulate", label: "Simulate" },
];

export default function App() {
  return (
    <div className="min-h-screen px-4 py-6 sm:px-8 sm:py-10 max-w-6xl mx-auto">
      <header className="mb-6 flex flex-wrap items-center gap-x-6 gap-y-3">
        <h1 className="font-display uppercase text-2xl tracking-tight text-primary">Loft Climate</h1>
        <nav className="flex flex-wrap gap-x-2 gap-y-1 text-sm">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.end}
              className={({ isActive }) =>
                `px-3 py-1.5 rounded uppercase tracking-label text-xs font-bold transition ${
                  isActive
                    ? "bg-primary text-surface"
                    : "text-secondary hover:text-primary hover:bg-secondary/10"
                }`
              }
            >
              {n.label}
            </NavLink>
          ))}
        </nav>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/entry" element={<Entry />} />
          <Route path="/history" element={<History />} />
          <Route path="/config" element={<Config />} />
          <Route path="/notifications" element={<Notifications />} />
          <Route path="/simulate" element={<Simulate />} />
        </Routes>
      </main>
    </div>
  );
}
