import { useEffect, useMemo, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../lib/api";
import { useCandidate } from "../lib/candidate";
import type { JobFilters, JobSummary, MatchItem } from "../lib/types";
import { FilterBar } from "../components/FilterBar";
import { JobCard } from "../components/JobCard";
import { JobDetailPanel } from "../components/JobDetailPanel";
import { EmptyState, ErrorNote, Spinner } from "../components/ui";

const FILTER_KEYS: (keyof JobFilters)[] = ["role", "location", "remote", "type", "source", "min_exp", "max_exp", "posted_within"];
const PAGE = 20;

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
  const [params, setParams] = useSearchParams();
  const [sort, setSort] = useState<"match" | "recent">("match");
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
    queryKey: ["jobs", filters, shown],
    queryFn: () => api.jobs(filters, shown, 0, candidateId),
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
    <div className="mx-auto max-w-7xl px-4 py-5">
      <FilterBar value={filters} onChange={setFilters} />

      <div className="mt-4 flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="text-lg font-semibold">
          {candidateId ? "Jobs matched to your profile" : "Latest jobs"}
          {q.data && <span className="ml-2 text-sm font-normal muted">{candidateId ? `top ${total}` : `${total.toLocaleString()} results`}</span>}
        </h1>
        <div className="flex items-center gap-3 text-sm">
          {candidateId && (
            <label className="flex items-center gap-2">
              <span className="muted">Sort by</span>
              <select className="input w-auto py-1" value={sort} onChange={(e) => setSort(e.target.value as "match" | "recent")}>
                <option value="match">Best match</option>
                <option value="recent">Most recent</option>
              </select>
            </label>
          )}
          <Link to="/elsewhere" className="text-brand-600 hover:underline">
            Search LinkedIn, Naukri, Indeed
          </Link>
        </div>
      </div>

      {!candidateId && (
        <div className="mt-3 rounded-lg border border-brand-200 bg-brand-50 px-4 py-3 text-sm dark:border-slate-700 dark:bg-slate-900">
          <Link to="/" className="font-medium text-brand-700 hover:underline dark:text-brand-200">
            Upload your resume
          </Link>{" "}
          to rank these jobs by how well they match your skills.
        </div>
      )}
      {candidate && candidate.skills.length === 0 && (
        <p className="mt-3 text-sm muted">
          We found no skills in your resume, so scores rely on text similarity. <Link to="/" className="text-brand-600 hover:underline">Add skills</Link>.
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
  );
}
