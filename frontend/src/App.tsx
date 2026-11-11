import { useEffect, useState } from "react";
import { Route, Routes } from "react-router-dom";
import { AppHeader } from "./components/AppHeader";
import { StatusPage } from "./pages/StatusPage";
import { Placeholder } from "./pages/Placeholder";

function initialDark(): boolean {
  try {
    const saved = localStorage.getItem("theme");
    if (saved) return saved === "dark";
  } catch {
    /* storage unavailable: fall back to system preference */
  }
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
}

export default function App() {
  const [dark, setDark] = useState(initialDark);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    try {
      localStorage.setItem("theme", dark ? "dark" : "light");
    } catch {
      /* ignore */
    }
  }, [dark]);

  return (
    <div className="min-h-full">
      <AppHeader dark={dark} onToggleTheme={() => setDark((d) => !d)} />
      <main>
        <Routes>
          <Route path="/" element={<Placeholder title="Find jobs that match your skills" note="Resume upload and ranked results arrive in Phase 2-5." />} />
          <Route path="/tracker" element={<Placeholder title="My applications" note="Tracker arrives in Phase 5." />} />
          <Route path="/status" element={<StatusPage />} />
        </Routes>
      </main>
    </div>
  );
}
