import { lazy, Suspense, useEffect, useState } from "react";
import { Link, Navigate, Route, Routes } from "react-router-dom";
import { AppHeader } from "./components/AppHeader";
import { RequireAuth } from "./components/RequireAuth";
import { EmptyState, PageLoading } from "./components/ui";
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
import { AuditPage, PolicyPage } from "./pages/tpo/AuditPolicyPages";
import { DriveDetailPage } from "./pages/tpo/DriveDetailPage";
import { DriveEditorPage } from "./pages/tpo/DriveEditorPage";
import { DrivesPage } from "./pages/tpo/DrivesPage";
import { StudentsPage } from "./pages/tpo/StudentsPage";
// Charts (Recharts) load only when a TPO opens them.
const DashboardPage = lazy(() => import("./pages/tpo/DashboardPage").then((m) => ({ default: m.DashboardPage })));
const AnalyticsPage = lazy(() => import("./pages/tpo/AnalyticsPage").then((m) => ({ default: m.AnalyticsPage })));
import { SharePage } from "./pages/SharePage";
import { ConsentPage } from "./pages/ConsentPage";
import { CampusDrivePage, CampusDrivesPage, ReadinessPage } from "./pages/CampusPages";
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
  if (loading) return <PageLoading />;
  if (!user) return <LandingPage />;
  if (user.must_reset_password) return <Navigate to="/change-password" replace />;
  if (user.role === "tpo") return <Navigate to="/tpo" replace />;
  if (user.role === "student" && user.consent_status === "pending") return <Navigate to="/consent" replace />;
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
  const tpoOnly = (el: JSX.Element) => (
    <RequireAuth roles={["tpo"]}>
      <Suspense fallback={<PageLoading />}>{el}</Suspense>
    </RequireAuth>
  );
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
          <Route path="/consent" element={<RequireAuth roles={["student"]}><ConsentPage /></RequireAuth>} />
          <Route path="/campus" element={<RequireAuth roles={["student"]}><CampusDrivesPage /></RequireAuth>} />
          <Route path="/campus/:id" element={<RequireAuth roles={["student"]}><CampusDrivePage /></RequireAuth>} />
          <Route path="/readiness" element={<RequireAuth roles={["student"]}><ReadinessPage /></RequireAuth>} />
          <Route path="/tpo" element={tpoOnly(<DashboardPage />)} />
          <Route path="/tpo/students" element={tpoOnly(<StudentsPage />)} />
          <Route path="/tpo/analytics" element={tpoOnly(<AnalyticsPage />)} />
          <Route path="/share/:token" element={<SharePage />} />
          <Route path="/tpo/drives" element={tpoOnly(<DrivesPage />)} />
          <Route path="/tpo/drives/new" element={tpoOnly(<DriveEditorPage />)} />
          <Route path="/tpo/drives/:id" element={tpoOnly(<DriveDetailPage />)} />
          <Route path="/tpo/drives/:id/edit" element={tpoOnly(<DriveEditorPage />)} />
          <Route path="/tpo/audit" element={tpoOnly(<AuditPage />)} />
          <Route path="/tpo/policy" element={tpoOnly(<PolicyPage />)} />
          <Route path="/status" element={<StatusPage />} />
          <Route path="*" element={<div className="page-narrow"><EmptyState title="Page not found" action={<Link to="/" className="btn-primary">Go home</Link>}>The link may be old or mistyped.</EmptyState></div>} />
        </Routes>
      </main>
      <footer className="border-t border-slate-200 dark:border-slate-800">
        <div className="mx-auto flex w-full max-w-7xl flex-wrap items-center justify-between gap-2 px-4 py-4 text-xs muted sm:px-6">
          <p>Listings come from official job APIs. You apply on the employer's or job board's own site</p>
          <Link to="/status" className="hover:underline">System status</Link>
        </div>
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
