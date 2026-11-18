import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ChevronLeft, Loader2 } from "lucide-react";
import { SOURCE_LABELS } from "../lib/format";

/** Standard page title block: optional back link or context line, title, description, actions on the right. */
export function PageHeader({
  title,
  description,
  actions,
  back,
  eyebrow,
  children,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  back?: { to: string; label: string };
  eyebrow?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0 flex-1">
        {back && (
          <Link to={back.to} className="mb-2 inline-flex items-center gap-1 text-sm muted hover:text-slate-900 dark:hover:text-white">
            <ChevronLeft className="h-4 w-4" aria-hidden />
            {back.label}
          </Link>
        )}
        {eyebrow && <p className="mb-1 text-sm muted">{eyebrow}</p>}
        <h1 className="text-2xl font-semibold text-slate-900 dark:text-white">{title}</h1>
        {description && <div className="mt-1 max-w-3xl text-sm muted">{description}</div>}
        {children}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

/** Full-page loading and error states, sized like the page they replace. */
export function PageLoading({ label = "Loading" }: { label?: string }) {
  return (
    <div className="page-narrow">
      <Spinner label={label} />
    </div>
  );
}

export function PageError({ error }: { error: unknown }) {
  return (
    <div className="page-narrow">
      <ErrorNote error={error} />
    </div>
  );
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <span role="status" className="inline-flex items-center gap-2 text-sm muted">
      <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
      {label}
    </span>
  );
}

export function EmptyState({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="card flex flex-col items-center px-6 py-12 text-center">
      <h2 className="section-title">{title}</h2>
      {children && <div className="mt-1 max-w-md text-sm muted">{children}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorNote({ error }: { error: unknown }) {
  const msg = error instanceof Error ? error.message : String(error);
  return (
    <p role="alert" className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-200">
      {msg}
    </p>
  );
}

type Tone = "green" | "red" | "slate" | "blue" | "amber";
const TONES: Record<Tone, string> = {
  green: "bg-emerald-50 text-emerald-800 ring-emerald-200 dark:bg-emerald-950 dark:text-emerald-200 dark:ring-emerald-900",
  red: "bg-rose-50 text-rose-800 ring-rose-200 dark:bg-rose-950 dark:text-rose-200 dark:ring-rose-900",
  slate: "bg-slate-100 text-slate-700 ring-slate-200 dark:bg-slate-800 dark:text-slate-200 dark:ring-slate-700",
  blue: "bg-brand-50 text-brand-700 ring-brand-200 dark:bg-slate-800 dark:text-brand-200 dark:ring-slate-700",
  amber: "bg-amber-50 text-amber-800 ring-amber-200 dark:bg-amber-950 dark:text-amber-200 dark:ring-amber-900",
};

export function Chip({ tone = "slate", children, title }: { tone?: Tone; children: ReactNode; title?: string }) {
  return (
    <span title={title} className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${TONES[tone]}`}>
      {children}
    </span>
  );
}

export function SourceBadge({ source }: { source: string }) {
  return (
    <span className="inline-flex items-center rounded border border-slate-200 px-1.5 py-0.5 text-[11px] font-medium text-slate-600 dark:border-slate-700 dark:text-slate-300">
      via {SOURCE_LABELS[source] ?? source}
    </span>
  );
}

/** Circular match indicator. Colour bands: >= 70 strong, >= 50 fair, else weak. */
export function MatchRing({ percent, size = 52 }: { percent: number; size?: number }) {
  const r = (size - 6) / 2;
  const c = 2 * Math.PI * r;
  const p = Math.max(0, Math.min(100, percent));
  const color = p >= 70 ? "stroke-emerald-500" : p >= 50 ? "stroke-amber-500" : "stroke-slate-400";
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }} aria-label={`${p}% match`} role="img">
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} strokeWidth={5} className="fill-none stroke-slate-200 dark:stroke-slate-700" />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          strokeWidth={5}
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - p / 100)}
          className={`fill-none ${color}`}
        />
      </svg>
      <span className="absolute inset-0 flex items-center justify-center leading-none">
        <span className={`${size >= 80 ? "text-xl" : "text-sm"} font-semibold tabular-nums`}>{p}%</span>
      </span>
    </div>
  );
}

export function ScoreBar({ label, value, hint }: { label: string; value: number; hint?: string }) {
  const p = Math.round(Math.max(0, Math.min(1, value)) * 100);
  return (
    <div>
      <div className="flex justify-between text-xs">
        <span className="font-medium">{label}</span>
        <span className="tabular-nums muted">{p}%</span>
      </div>
      <div className="mt-1 h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800" title={hint}>
        <div className="h-full rounded-full bg-brand-500" style={{ width: `${p}%` }} />
      </div>
    </div>
  );
}
