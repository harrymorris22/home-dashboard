import { Link, Route, Routes, useLocation } from "react-router-dom";

import { Home } from "./routes/Home";
import { WidgetDetail } from "./routes/WidgetDetail";

function Header() {
  const location = useLocation();
  const isDetail = location.pathname.startsWith("/widget/");
  const today = new Date().toLocaleDateString([], {
    weekday: "long",
    day: "numeric",
    month: "long",
  });

  return (
    <header className="mb-6 flex items-center justify-between gap-4">
      <Link to="/" className="font-display uppercase text-2xl tracking-tight text-primary no-underline">
        Desk
      </Link>
      <span className="hud-label text-secondary">{today}</span>
      {isDetail && (
        <Link to="/" className="hud-button-secondary text-xs">Back</Link>
      )}
    </header>
  );
}

export default function App() {
  return (
    <div className="min-h-screen px-4 py-6 sm:px-8 sm:py-10 max-w-7xl mx-auto">
      <Header />
      <main>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/widget/:name" element={<WidgetDetail />} />
        </Routes>
      </main>
    </div>
  );
}
