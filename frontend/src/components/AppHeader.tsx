import { useEffect, useRef, useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { Menu, Moon, Sun, UserRound, X } from "lucide-react";
import { useCandidate } from "../lib/candidate";
import { useTracking } from "../lib/tracking";

const LINKS = [
  { to: "/jobs", label: "Jobs" },
  { to: "/skills", label: "Skill gap" },
  { to: "/tracker", label: "Applications" },
  { to: "/import", label: "Import" },
  { to: "/elsewhere", label: "Search elsewhere" },
];

export function AppHeader({ dark, onToggleTheme }: { dark: boolean; onToggleTheme: () => void }) {
  const { candidate } = useCandidate();
  const { applications } = useTracking();
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

  const active = applications.filter((a) => a.status !== "Rejected").length;
  const navCls = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-1.5 border-b-2 px-3 text-sm ${
      isActive
        ? "border-brand-600 font-medium text-slate-900 dark:text-white"
        : "border-transparent text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white"
    }`;

  return (
    <header className="sticky top-0 z-30 border-b border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
      <div className="mx-auto flex h-14 max-w-7xl items-stretch gap-4 px-4">
        <Link to="/" className="flex items-center gap-2 font-semibold text-slate-900 dark:text-white">
          <span className="grid h-7 w-7 place-items-center rounded-md bg-brand-600 text-sm font-bold text-white" aria-hidden>
            S
          </span>
          SkillMatch
        </Link>
        <nav aria-label="Primary" className="hidden items-stretch md:flex">
          {LINKS.map((l) => (
            <NavLink key={l.to} to={l.to} className={navCls}>
              {l.label}
              {l.to === "/tracker" && active > 0 && (
                <span className="rounded-full bg-slate-200 px-1.5 text-[11px] font-medium text-slate-700 dark:bg-slate-700 dark:text-slate-200">{active}</span>
              )}
            </NavLink>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-1">
          <button className="btn-ghost p-2" onClick={onToggleTheme} aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}>
            {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </button>
          <div className="relative" ref={ref}>
            <button className="btn-ghost gap-2 px-2" aria-haspopup="menu" aria-expanded={menu} onClick={() => setMenu((m) => !m)}>
              <span className="grid h-7 w-7 place-items-center rounded-full bg-slate-200 dark:bg-slate-700">
                <UserRound className="h-4 w-4" aria-hidden />
              </span>
              <span className="hidden max-w-40 truncate text-sm sm:inline">{candidate ? candidate.filename ?? "My resume" : "No resume"}</span>
            </button>
            {menu && (
              <div role="menu" className="card absolute right-0 mt-1 w-56 py-1 shadow-lg">
                <Link role="menuitem" to="/" className="block px-3 py-2 text-sm hover:bg-slate-100 dark:hover:bg-slate-800">
                  {candidate ? "My profile and skills" : "Upload resume"}
                </Link>
                <Link role="menuitem" to="/settings" className="block px-3 py-2 text-sm hover:bg-slate-100 dark:hover:bg-slate-800">
                  Settings and privacy
                </Link>
              </div>
            )}
          </div>
          <button className="btn-ghost p-2 md:hidden" onClick={() => setMobile((m) => !m)} aria-label="Menu" aria-expanded={mobile}>
            {mobile ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>
      </div>
      {mobile && (
        <nav aria-label="Primary" className="border-t border-slate-200 px-2 py-2 md:hidden dark:border-slate-800">
          {LINKS.map((l) => (
            <NavLink key={l.to} to={l.to} className={({ isActive }) => `block rounded-md px-3 py-2 text-sm ${isActive ? "bg-slate-100 font-medium dark:bg-slate-800" : ""}`}>
              {l.label}
            </NavLink>
          ))}
        </nav>
      )}
    </header>
  );
}
