import { useEffect, useRef, useState } from "react";
import { ChevronDown, ExternalLink } from "lucide-react";
import { useTracking } from "../lib/tracking";
import type { ApplyOption, JobSummary } from "../lib/types";

export function applyLabel(o: ApplyOption): string {
  const p = o.publisher;
  if (/ application form$/.test(p)) return "application form";
  if (/careers \((Greenhouse|Lever|Ashby)\)$/.test(p) || (o.is_direct && !/linkedin|naukri|indeed/i.test(p))) {
    return "company site";
  }
  return p;
}

export function menuLabel(o: ApplyOption): string {
  const l = applyLabel(o);
  return l === "application form" ? "Application form" : l === "company site" ? "Job page on company site" : `Apply on ${l}`;
}

/** Apply opens the best link (the application form when we have it) in one click; the chevron lists the others. */
export function ApplyMenu({ job, size = "md" }: { job: JobSummary; size?: "sm" | "md" }) {
  const { openApply } = useTracking();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const options = job.apply_options.length
    ? job.apply_options
    : job.apply_url
      ? [{ publisher: "Company site", url: job.apply_url, is_direct: true }]
      : [];

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  // One entry per destination (duplicates of the same posting can carry several careers-page links).
  const unique = options
    .filter((o, i) => options.findIndex((x) => applyLabel(x) === applyLabel(o)) === i)
    .sort((a, b) => Number(b.is_direct) - Number(a.is_direct)); // employer's own page before job boards
  const [first, ...rest] = unique;
  const cls = size === "sm" ? "btn-primary h-8 px-3 text-xs" : "btn-primary px-4";
  if (!first) {
    return (
      <button className={cls} disabled title="No application link for this job">
        Apply
      </button>
    );
  }
  return (
    <div className="relative inline-flex" ref={ref}>
      <button
        className={`${cls} ${rest.length ? "rounded-r-none" : ""}`}
        onClick={() => openApply(job, first)}
        title={`Opens the ${applyLabel(first)} in a new tab`}
      >
        Apply
        <ExternalLink className="h-3.5 w-3.5" aria-hidden />
      </button>
      {rest.length > 0 && (
        <button
          className={`${cls} rounded-l-none border-l border-white/25 px-2`}
          aria-label="More ways to apply"
          aria-haspopup="menu"
          aria-expanded={open}
          onClick={() => setOpen((o) => !o)}
        >
          <ChevronDown className="h-3.5 w-3.5" aria-hidden />
        </button>
      )}
      {open && (
        <div role="menu" className="card absolute right-0 top-full z-30 mt-1 min-w-56 py-1 shadow-lg">
          {unique.map((o) => (
            <button
              key={o.url}
              role="menuitem"
              className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-sm hover:bg-slate-100 dark:hover:bg-slate-800"
              onClick={() => {
                setOpen(false);
                openApply(job, o);
              }}
            >
              <span>{menuLabel(o)}</span>
              <ExternalLink className="h-3.5 w-3.5 muted" aria-hidden />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
