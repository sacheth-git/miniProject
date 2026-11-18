import { useEffect, useMemo, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useCandidate } from "../lib/candidate";
import type { JobFilters, JobSummary, MatchItem } from "../lib/types";
import { FilterBar } from "../components/FilterBar";
import { JobCard } from "../components/JobCard";
import { JobDetailPanel } from "../components/JobDetailPanel";
import { EmptyState, ErrorNote, Spinner } from "../components/ui";

const FILTER_KEYS: (keyof JobFilters)[] = ["role", "location", "remote", "type", "source", "min_exp", "max_exp", "posted_within"];
const PAGE = 20;
const QUICK: [string, Partial<JobFilters>][] = [
  ["Remote", { remote: "true" }],
  ["Internships", { type: "internship" }],
  ["Freshers", { min_exp: "0", max_exp: "1" }],
  ["India", { location: "india" }],
  ["Past 24 hours", { posted_within: "1" }],
];

function useIsDesktop(): boolean {
  const q = "(min-width: 1024px)";
  const [m, setM] = useState(() => window.matchMedia?.(q).matches ?? true);
  useEffect(() => {
    const mq = window.matchMedia?.(q);
    if (!mq) return;
    const on = () => setM(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return m;
}

export function JobsPage() {
  const { candidateId, candidate } = useCandidate();
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const [sort, setSort] = useState<"match" | "recent">("match");
  const [browseSort, setBrowseSort] = useState<"mixed" | "recent">("mixed");
  const [shown, setShown] = useState(PAGE);
  const desktop = useIsDesktop();

  const filters = useMemo(() => {
    const f: JobFilters = {};
    for (const k of FILTER_KEYS) {
      const v = params.get(k);
      if (v) (f as Record<string, string>)[k] = v;
    }
    return f;
  }, [params]);
  const selectedId = params.get("job");

  const setFilters = (f: JobFilters) => {
    const next = new URLSearchParams();
    for (const [k, v] of Object.entries(f)) if (v) next.set(k, v);
    setParams(next);
    setShown(PAGE);
  };
  const select = (id: string | null) => {
    const next = new URLSearchParams(params);
    if (id) next.set("job", id);
    else next.delete("job");
    setParams(next, { replace: true });
  };

  const matchQ = useQuery({
    queryKey: ["match", candidateId, filters, Math.max(50, shown)],
    queryFn: () => api.match(candidateId!, filters, Math.min(100, Math.max(50, shown))),
    enabled: !!candidateId,
    placeholderData: keepPreviousData,
  });
  const browseQ = useQuery({
    queryKey: ["jobs", filters, shown, browseSort],
    queryFn: () => api.jobs(filters, shown, 0, candidateId, browseSort),
    enabled: !candidateId,
    placeholderData: keepPreviousData,
  });

  const rows: { job: JobSummary; match?: MatchItem }[] = useMemo(() => {
    if (candidateId) {
      const items = [...(matchQ.data?.items ?? [])];
      if (sort === "recent") items.sort((a, b) => (b.job.posted_at ?? "").localeCompare(a.job.posted_at ?? ""));
      return items.slice(0, shown).map((m) => ({ job: m.job, match: m }));
    }
    return (browseQ.data?.items ?? []).map((job) => ({ job }));
  }, [candidateId, matchQ.data, browseQ.data, sort, shown]);

  const q = candidateId ? matchQ : browseQ;
  const total = candidateId ? (matchQ.data?.returned ?? 0) : (browseQ.data?.total ?? 0);
  // Match mode fetches up to 100 ranked jobs (50 at a time); browse mode pages through /jobs.
  const requested = Math.min(100, Math.max(50, shown));
  const returned = matchQ.data?.returned ?? 0;
  const canMore = candidateId ? shown < returned || (returned === requested && requested < 100) : shown < total;

  // Desktop: keep a job open on the right.
  useEffect(() => {
    if (desktop && !selectedId && rows.length) select(rows[0].job.id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [desktop, rows.length > 0]);

  return (
    <div>
      <div className="bg-ink-950 pb-6 pt-8 text-white">
        <div className="mx-auto w-full max-w-7xl px-4 sm:px-6">
          <h1 className="text-2xl font-semibold">{candidateId ? "Jobs matched to your profile" : "Find your next job"}</h1>
          <p className="mt-1 text-sm text-slate-400">
            {candidateId ? "Ranked by how well your skills fit each job" : "Every source in one feed: company career sites and job boards"}
          </p>
          <div className="mt-5">
            <FilterBar value={filters} onChange={setFilters} />
          </div>
          <div className="mt-3 flex flex-wrap gap-2" aria-label="Quick filters">
            {QUICK.map(([label, patch]) => {
              const on = Object.entries(patch).every(([k, v]) => filters[k as keyof JobFilters] === v);
              const toggle = () => {
                const next = { ...filters };
                for (const [k, v] of Object.entries(patch)) (next as Record<string, string | undefined>)[k] = on ? undefined : v;
                setFilters(next);
              };
              return (
                <button key={label} onClick={toggle} aria-pressed={on}
                  className={`h-8 rounded-full border px-3 text-sm transition-colors ${on ? "border-brand-500 bg-brand-500/15 text-white" : "border-white/15 text-slate-300 hover:border-white/40 hover:text-white"}`}>
                  {label}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      <div className="mx-auto w-full max-w-7xl px-4 py-6 sm:px-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm muted" aria-live="polite">
          {q.data && (candidateId ? `Top ${total} matches` : `${total.toLocaleString()} jobs`)}
        </p>
        <div className="flex items-center gap-3 text-sm">
          <label className="flex items-center gap-2">
            <span className="muted">Sort by</span>
            {candidateId ? (
              <select className="input h-8 w-auto py-0" value={sort} onChange={(e) => setSort(e.target.value as "match" | "recent")}>
                <option value="match">Best match</option>
                <option value="recent">Most recent</option>
              </select>
            ) : (
              <select className="input h-8 w-auto py-0" value={browseSort} onChange={(e) => setBrowseSort(e.target.value as "mixed" | "recent")}>
                <option value="mixed">Recommended</option>
                <option value="recent">Most recent</option>
              </select>
            )}
          </label>
        </div>
      </div>

      {!candidateId && (
        <div className="mt-3 rounded-lg border border-brand-200 bg-brand-50 px-4 py-3 text-sm dark:border-slate-700 dark:bg-slate-900">
          {user ? (
            <>
              <Link to="/" className="font-medium text-brand-700 hover:underline dark:text-brand-200">Upload your resume</Link> to rank
              these jobs by how well they match your skills.
            </>
          ) : (
            <>
              <Link to="/register" className="font-medium text-brand-700 hover:underline dark:text-brand-200">Join</Link> or{" "}
              <Link to="/login" className="font-medium text-brand-700 hover:underline dark:text-brand-200">sign in</Link> and upload your
              resume to rank these jobs by how well they match your skills.
            </>
          )}
        </div>
      )}
      {candidate && candidate.skills.length === 0 && (
        <p className="mt-3 text-sm muted">
          We found no skills in your resume, so scores rely on text similarity. <Link to="/" className="link">Add skills</Link>.
        </p>
      )}

      <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)]">
        <section aria-label="Job results" className="space-y-3">
          {q.isLoading && <Spinner label={candidateId ? "Ranking jobs for you" : "Loading jobs"} />}
          {q.error && <ErrorNote error={q.error} />}
          {q.data && rows.length === 0 && (
            <EmptyState title="No jobs match these filters" action={<button className="btn-secondary" onClick={() => setFilters({})}>Clear filters</button>}>
              Try a wider location or remove the experience filter.
            </EmptyState>
          )}
          {rows.map(({ job, match }) => (
            <JobCard key={job.id} job={job} match={match} selected={job.id === selectedId} onSelect={() => select(job.id)} />
          ))}
          {rows.length > 0 && canMore && (
            <button className="btn-secondary w-full" onClick={() => setShown((n) => n + PAGE)} disabled={q.isFetching}>
              {q.isFetching ? "Loading" : "Show more jobs"}
            </button>
          )}
        </section>

        {selectedId && desktop && (
          <aside className="card sticky top-20 hidden h-[calc(100vh-6rem)] overflow-hidden lg:block" aria-label="Job details">
            <JobDetailPanel key={selectedId} jobId={selectedId} />
          </aside>
        )}
      </div>

      {selectedId && !desktop && (
        <div className="fixed inset-0 z-40 bg-white dark:bg-slate-900" role="dialog" aria-modal="true" aria-label="Job details">
          <JobDetailPanel key={selectedId} jobId={selectedId} onClose={() => select(null)} />
        </div>
      )}
      </div>
    </div>
  );
}
