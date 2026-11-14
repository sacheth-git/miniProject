import { useEffect, useState } from "react";
import { Link, Route, Routes } from "react-router-dom";
import { AppHeader } from "./components/AppHeader";
import { CandidateProvider } from "./lib/candidate";
import { TrackingProvider } from "./lib/tracking";
import { ElsewherePage } from "./pages/ElsewherePage";
import { GapPage } from "./pages/GapPage";
import { ImportPage } from "./pages/ImportPage";
import { JobsPage } from "./pages/JobsPage";
import { SettingsPage } from "./pages/SettingsPage";
import { StatusPage } from "./pages/StatusPage";
import { TrackerPage } from "./pages/TrackerPage";
import { UploadPage } from "./pages/UploadPage";

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
    <CandidateProvider>
      <TrackingProvider>
        <div className="flex min-h-full flex-col">
          <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-white focus:px-3 focus:py-2">
            Skip to content
          </a>
          <AppHeader dark={dark} onToggleTheme={() => setDark((d) => !d)} />
          <main id="main" className="flex-1">
            <Routes>
              <Route path="/" element={<UploadPage />} />
              <Route path="/jobs" element={<JobsPage />} />
              <Route path="/skills" element={<GapPage />} />
              <Route path="/tracker" element={<TrackerPage />} />
              <Route path="/import" element={<ImportPage />} />
              <Route path="/elsewhere" element={<ElsewherePage />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="/status" element={<StatusPage />} />
              <Route path="*" element={<div className="mx-auto max-w-3xl px-4 py-12">Page not found. <Link to="/jobs" className="text-brand-600 hover:underline">Go to jobs</Link></div>} />
            </Routes>
          </main>
          <footer className="border-t border-slate-200 py-4 text-center text-xs muted dark:border-slate-800">
            SkillMatch recommends jobs; you apply on the employer's or job board's own site. Listings come from official APIs.{" "}
            <Link to="/status" className="hover:underline">System status</Link>
          </footer>
        </div>
      </TrackingProvider>
    </CandidateProvider>
  );
}
