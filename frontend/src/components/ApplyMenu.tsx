import { useEffect, useRef, useState } from "react";
import { ChevronDown, ExternalLink } from "lucide-react";
import { useTracking } from "../lib/tracking";
import type { ApplyOption, JobSummary } from "../lib/types";

export function applyLabel(o: ApplyOption): string {
  const p = o.publisher;
  if (/careers \((Greenhouse|Lever|Ashby)\)$/.test(p) || (o.is_direct && !/linkedin|naukri|indeed/i.test(p))) {
    return "company site";
  }
  return p;
}

/** One apply option: a button. Several (e.g. LinkedIn / Naukri / company site): a menu. */
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

  const cls = size === "sm" ? "btn-primary h-8 px-2.5 text-xs" : "btn-primary";
  if (!options.length) {
    return (
      <button className={cls} disabled title="No application link for this job">
        Apply
      </button>
    );
  }
  if (options.length === 1) {
    return (
      <button className={cls} onClick={() => openApply(job, options[0])} title={`Opens ${options[0].url} in a new tab`}>
        Apply on {applyLabel(options[0])}
        <ExternalLink className="h-3.5 w-3.5" aria-hidden />
      </button>
    );
  }
  return (
    <div className="relative" ref={ref}>
      <button className={cls} aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        Apply
        <ChevronDown className="h-3.5 w-3.5" aria-hidden />
      </button>
      {open && (
        <div role="menu" className="card absolute right-0 z-30 mt-1 min-w-52 py-1 shadow-lg">
          {options.map((o) => (
            <button
              key={o.url}
              role="menuitem"
              className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-sm hover:bg-slate-100 dark:hover:bg-slate-800"
              onClick={() => {
                setOpen(false);
                openApply(job, o);
              }}
            >
              <span>Apply on {applyLabel(o)}</span>
              <ExternalLink className="h-3.5 w-3.5 muted" aria-hidden />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
