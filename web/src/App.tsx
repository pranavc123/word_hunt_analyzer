import { NavLink, Route, Routes } from "react-router-dom";
import { BoardConfirm } from "./pages/BoardConfirm";
import { GameReview } from "./pages/GameReview";
import { Dictionary, Patterns, Settings, Strategy } from "./pages/Pages";
import { SessionSummary } from "./pages/SessionSummary";
import { Sessions } from "./pages/Sessions";

const NAV = [
  { to: "/", label: "Sessions", icon: "▦" },
  { to: "/patterns", label: "Patterns", icon: "◔" },
  { to: "/strategy", label: "Strategy", icon: "➚" },
  { to: "/dictionary", label: "Dictionary", icon: "Aa" },
  { to: "/settings", label: "Settings", icon: "⚙" },
];

export default function App() {
  return (
    <div className="shell">
      <Routes>
        <Route path="/" element={<Sessions />} />
        <Route path="/sessions/:id" element={<SessionSummary />} />
        <Route path="/sessions/:id/confirm" element={<BoardConfirm />} />
        <Route path="/boards/:id" element={<GameReview />} />
        <Route path="/patterns" element={<Patterns />} />
        <Route path="/strategy" element={<Strategy />} />
        <Route path="/dictionary" element={<Dictionary />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="*" element={<Sessions />} />
      </Routes>
      <nav className="bottom-nav" aria-label="Main">
        {NAV.map((n) => (
          <NavLink key={n.to} to={n.to} end={n.to === "/"}>
            <span className="icon" aria-hidden>
              {n.icon}
            </span>
            {n.label}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
