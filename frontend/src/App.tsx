import { useEffect, useState } from "react";
import { Link, Navigate, Route, Routes } from "react-router-dom";
import { AppHeader } from "./components/AppHeader";
import { RequireAuth } from "./components/RequireAuth";
import { Spinner } from "./components/ui";
import { AuthProvider, isSeeker, useAuth } from "./lib/auth";
import { CandidateProvider } from "./lib/candidate";
import { TrackingProvider } from "./lib/tracking";
import { ChangePasswordPage, LoginPage, RegisterPage } from "./pages/AuthPages";
import { ElsewherePage } from "./pages/ElsewherePage";
import { GapPage } from "./pages/GapPage";
import { ImportPage } from "./pages/ImportPage";
import { JobsPage } from "./pages/JobsPage";
import { LandingPage } from "./pages/LandingPage";
import { SettingsPage } from "./pages/SettingsPage";
import { StatusPage } from "./pages/StatusPage";
import { TpoHomePage } from "./pages/TpoHomePage";
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

const SEEKERS = ["student", "job_seeker"] as const;

/** "/" is the landing page for guests, resume home for seekers, dashboard for TPOs. */
function Home() {
  const { user, loading } = useAuth();
  if (loading) return <div className="p-8"><Spinner /></div>;
  if (!user) return <LandingPage />;
  if (user.must_reset_password) return <Navigate to="/change-password" replace />;
  if (user.role === "tpo") return <Navigate to="/tpo" replace />;
  return isSeeker(user) ? <UploadPage /> : <LandingPage />;
}

function Shell() {
  const [dark, setDark] = useState(initialDark);
  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    try {
      localStorage.setItem("theme", dark ? "dark" : "light");
    } catch {
      /* ignore */
    }
  }, [dark]);

  const seeker = (el: JSX.Element) => <RequireAuth roles={[...SEEKERS]}>{el}</RequireAuth>;
  return (
    <div className="flex min-h-full flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-white focus:px-3 focus:py-2">
        Skip to content
      </a>
      <AppHeader dark={dark} onToggleTheme={() => setDark((d) => !d)} />
      <main id="main" className="flex-1">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/change-password" element={<RequireAuth><ChangePasswordPage /></RequireAuth>} />
          <Route path="/jobs" element={<JobsPage />} />
          <Route path="/skills" element={seeker(<GapPage />)} />
          <Route path="/tracker" element={seeker(<TrackerPage />)} />
          <Route path="/import" element={seeker(<ImportPage />)} />
          <Route path="/elsewhere" element={seeker(<ElsewherePage />)} />
          <Route path="/settings" element={<RequireAuth><SettingsPage /></RequireAuth>} />
          <Route path="/tpo" element={<RequireAuth roles={["tpo"]}><TpoHomePage /></RequireAuth>} />
          <Route path="/status" element={<StatusPage />} />
          <Route path="*" element={<div className="mx-auto max-w-3xl px-4 py-12">Page not found. <Link to="/" className="text-brand-600 hover:underline">Go home</Link></div>} />
        </Routes>
      </main>
      <footer className="border-t border-slate-200 py-4 text-center text-xs muted dark:border-slate-800">
        SkillMatch recommends jobs; you apply on the employer's or job board's own site. Listings come from official APIs.{" "}
        <Link to="/status" className="hover:underline">System status</Link>
      </footer>
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <CandidateProvider>
        <TrackingProvider>
          <Shell />
        </TrackingProvider>
      </CandidateProvider>
    </AuthProvider>
  );
}
