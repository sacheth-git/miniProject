import { useEffect, useRef, useState } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { Menu, Moon, Sun, UserRound, X } from "lucide-react";
import { isSeeker, useAuth } from "../lib/auth";
import { useTracking } from "../lib/tracking";
import { NotificationBell } from "./NotificationBell";

/** The HireX wordmark: the X is the one place the accent always appears. */
export function Wordmark() {
  return (
    <span>
      Hire<span className="text-brand-500">X</span>
    </span>
  );
}

const SEEKER_LINKS = [
  { to: "/jobs", label: "Jobs" },
  { to: "/skills", label: "Skill gap" },
  { to: "/tracker", label: "Applications" },
  { to: "/import", label: "Import" },
  { to: "/elsewhere", label: "Search elsewhere" },
];
const STUDENT_LINKS = [
  { to: "/jobs", label: "Jobs" },
  { to: "/campus", label: "Campus drives" },
  { to: "/readiness", label: "Readiness" },
  { to: "/skills", label: "Skill gap" },
  { to: "/tracker", label: "Applications" },
  { to: "/import", label: "Import" },
];
const TPO_LINKS = [
  { to: "/tpo", label: "Dashboard" },
  { to: "/tpo/students", label: "Students" },
  { to: "/tpo/drives", label: "Drives" },
  { to: "/tpo/analytics", label: "Analytics" },
  { to: "/tpo/audit", label: "Audit log" },
  { to: "/tpo/policy", label: "Policy" },
];
const GUEST_LINKS = [
  { to: "/jobs", label: "Jobs" },
  { to: "/#colleges", label: "For colleges (TPO)" },
];

const ROLE_LABEL: Record<string, string> = {
  student: "Student",
  job_seeker: "Job seeker",
  tpo: "Placement officer",
  recruiter_view: "Recruiter",
};

export function AppHeader({ dark, onToggleTheme }: { dark: boolean; onToggleTheme: () => void }) {
  const { user, logout } = useAuth();
  const { applications } = useTracking();
  const navigate = useNavigate();
  const [menu, setMenu] = useState(false);
  const [mobile, setMobile] = useState(false);
  const loc = useLocation();
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setMenu(false);
    setMobile(false);
  }, [loc.pathname]);
  useEffect(() => {
    if (!menu) return;
    const on = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setMenu(false);
    document.addEventListener("mousedown", on);
    return () => document.removeEventListener("mousedown", on);
  }, [menu]);

  const links = !user ? GUEST_LINKS : user.role === "tpo" ? TPO_LINKS : user.role === "student" ? STUDENT_LINKS : isSeeker(user) ? SEEKER_LINKS : GUEST_LINKS;
  const active = applications.filter((a) => a.status !== "Rejected").length;
  const navCls = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-1.5 border-b-2 px-3 text-sm ${
      isActive
        ? "border-brand-500 font-medium text-white"
        : "border-transparent text-slate-400 hover:text-white"
    }`;

  const signOut = async () => {
    await logout();
    navigate("/", { replace: true });
  };

  return (
    <header className="sticky top-0 z-30 border-b border-white/10 bg-ink-950 text-white">
      <div className="mx-auto flex h-14 max-w-7xl items-stretch gap-6 px-4 sm:px-6">
        <Link to="/" className="flex items-center text-lg font-semibold text-white" aria-label="HireX home">
          <Wordmark />
        </Link>
        <nav aria-label="Primary" className="hidden items-stretch md:flex">
          {links.map((l) => (
            <NavLink key={l.to} to={l.to} end={l.to === "/tpo"} className={({ isActive }) => navCls({ isActive: isActive && !l.to.includes("#") })}>
              {l.label}
              {l.to === "/tracker" && active > 0 && (
                <span className="text-xs tabular-nums text-slate-400">{active}</span>
              )}
            </NavLink>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-1">
          {isSeeker(user) && <NotificationBell />}
          <button className="btn-onink w-9 p-0" onClick={onToggleTheme} aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}>
            {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </button>
          {!user ? (
            <>
              <Link to="/login" className="btn-onink">Sign in</Link>
              <Link to="/register" className="btn-primary hidden sm:inline-flex">Join now</Link>
            </>
          ) : (
            <div className="relative" ref={ref}>
              <button className="btn-onink gap-2 px-2" aria-haspopup="menu" aria-expanded={menu} onClick={() => setMenu((m) => !m)}>
                <span className="grid h-7 w-7 place-items-center rounded-full bg-white/10">
                  <UserRound className="h-4 w-4" aria-hidden />
                </span>
                <span className="hidden max-w-40 truncate text-sm sm:inline">{user.full_name || user.email}</span>
              </button>
              {menu && (
                <div role="menu" className="card absolute right-0 mt-1 w-64 py-1 text-slate-900 shadow-lg dark:text-slate-100">
                  <div className="border-b border-slate-100 px-3 py-2 dark:border-slate-800">
                    <p className="truncate text-sm font-medium">{user.full_name || user.email}</p>
                    <p className="truncate text-xs muted">
                      {ROLE_LABEL[user.role]}
                      {user.institution_name ? ` · ${user.institution_name}` : ""}
                    </p>
                  </div>
                  {isSeeker(user) && (
                    <Link role="menuitem" to="/" className="block px-3 py-2 text-sm hover:bg-slate-100 dark:hover:bg-slate-800">
                      My profile and resume
                    </Link>
                  )}
                  <Link role="menuitem" to="/settings" className="block px-3 py-2 text-sm hover:bg-slate-100 dark:hover:bg-slate-800">
                    Settings and privacy
                  </Link>
                  <button role="menuitem" onClick={signOut} className="block w-full px-3 py-2 text-left text-sm hover:bg-slate-100 dark:hover:bg-slate-800">
                    Sign out
                  </button>
                </div>
              )}
            </div>
          )}
          <button className="btn-onink w-9 p-0 md:hidden" onClick={() => setMobile((m) => !m)} aria-label="Menu" aria-expanded={mobile}>
            {mobile ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>
      </div>
      {mobile && (
        <nav aria-label="Primary" className="border-t border-white/10 px-2 py-2 md:hidden">
          {links.map((l) => (
            <NavLink key={l.to} to={l.to} className={({ isActive }) => `block rounded-lg px-3 py-2 text-sm ${isActive && !l.to.includes("#") ? "bg-white/10 font-medium text-white" : "text-slate-300"}`}>
              {l.label}
            </NavLink>
          ))}
        </nav>
      )}
    </header>
  );
}
