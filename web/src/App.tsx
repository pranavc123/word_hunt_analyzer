import { NavLink, Route, Routes } from "react-router-dom";
import { Dictionary, Patterns, Sessions, Settings, Strategy } from "./pages/Pages";

const NAV = [
  { to: "/", label: "Sessions", icon: "▦", element: <Sessions /> },
  { to: "/patterns", label: "Patterns", icon: "◔", element: <Patterns /> },
  { to: "/strategy", label: "Strategy", icon: "➚", element: <Strategy /> },
  { to: "/dictionary", label: "Dictionary", icon: "Aa", element: <Dictionary /> },
  { to: "/settings", label: "Settings", icon: "⚙", element: <Settings /> },
];

export default function App() {
  return (
    <div className="shell">
      <Routes>
        {NAV.map((n) => (
          <Route key={n.to} path={n.to} element={n.element} />
        ))}
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
