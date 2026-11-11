import { NavLink } from "react-router-dom";

const links = [
  { to: "/", label: "Jobs" },
  { to: "/tracker", label: "My applications" },
  { to: "/status", label: "System status" },
];

export function AppHeader({ dark, onToggleTheme }: { dark: boolean; onToggleTheme: () => void }) {
  return (
    <header className="sticky top-0 z-20 border-b border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-6 px-4">
        <NavLink to="/" className="flex items-center gap-2 font-semibold text-slate-900 dark:text-white">
          <span className="grid h-7 w-7 place-items-center rounded-md bg-brand-600 text-sm font-bold text-white">S</span>
          SkillMatch
        </NavLink>
        <nav aria-label="Primary" className="flex h-full items-stretch gap-1 text-sm">
          {links.map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              end
              className={({ isActive }) =>
                `flex items-center border-b-2 px-3 ${
                  isActive
                    ? "border-brand-600 text-slate-900 dark:text-white"
                    : "border-transparent text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white"
                }`
              }
            >
              {l.label}
            </NavLink>
          ))}
        </nav>
        <button
          type="button"
          onClick={onToggleTheme}
          className="ml-auto rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
          aria-pressed={dark}
        >
          {dark ? "Light mode" : "Dark mode"}
        </button>
      </div>
    </header>
  );
}
