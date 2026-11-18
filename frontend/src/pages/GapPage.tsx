import { useMutation, useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { useCandidate } from "../lib/candidate";
import type { GapSkill } from "../lib/types";
import { EmptyState, ErrorNote, PageHeader, Spinner } from "../components/ui";

export function GapPage() {
  const { candidateId, candidate, setCandidate } = useCandidate();
  const gap = useQuery({ queryKey: ["gap", candidateId], queryFn: () => api.gap(candidateId!, {}), enabled: !!candidateId });
  const add = useMutation({
    mutationFn: (name: string) => api.editSkills(candidateId!, [name], []),
    onSuccess: setCandidate,
  });

  if (!candidateId) {
    return (
      <div className="page-narrow">
        <EmptyState title="Upload your resume first" action={<Link to="/" className="btn-primary">Upload resume</Link>}>
          Skill-gap advice compares your skills with the jobs that fit you best.
        </EmptyState>
      </div>
    );
  }
  const max = Math.max(0.01, ...(gap.data?.by_total_gain ?? []).map((g) => g.total_gain));
  const have = new Set(candidate?.skills.map((s) => s.skill_id));

  return (
    <div className="page-mid">
      <PageHeader
        title="Skills to learn next"
        description={`We re-scored your ${gap.data?.jobs_considered ?? 50} best-matching jobs as if you had each missing skill. These raise your matches the most.`}
      />
      {gap.isLoading && <div className="mt-6"><Spinner label="Working out your skill gap" /></div>}
      {gap.error && <div className="mt-6"><ErrorNote error={gap.error} /></div>}
      {gap.data && gap.data.by_total_gain.length === 0 && (
        <div className="mt-6">
          <EmptyState title="No gaps found">Your top matches don't list skills you're missing.</EmptyState>
        </div>
      )}
      {gap.data && gap.data.by_total_gain.length > 0 && (
        <div className="mt-6 grid gap-6 md:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
          <section className="card p-5" aria-labelledby="impact-h">
            <h2 id="impact-h" className="font-semibold">Biggest overall impact</h2>
            <ol className="mt-4 space-y-5">
              {gap.data.by_total_gain.map((g, i) => (
                <GapRow key={g.skill_id} g={g} rank={i + 1} max={max} owned={have.has(g.skill_id)} onAdd={() => add.mutate(g.name)} />
              ))}
            </ol>
          </section>
          <section className="card p-5" aria-labelledby="reach-h">
            <h2 id="reach-h" className="font-semibold">Opens up the most jobs</h2>
            <ol className="mt-4 space-y-3">
              {gap.data.by_jobs_improved.map((g) => (
                <li key={g.skill_id} className="flex items-baseline justify-between gap-3 text-sm">
                  <span className="font-medium">{g.name}</span>
                  <span className="muted">
                    {g.jobs_improved} job{g.jobs_improved === 1 ? "" : "s"} · +{Math.round(g.avg_gain * 100)}% avg
                  </span>
                </li>
              ))}
            </ol>
            <p className="mt-5 text-xs muted">
              Already know one of these? Add it to your profile so it counts.
            </p>
          </section>
        </div>
      )}
      {add.error && <div className="mt-4"><ErrorNote error={add.error} /></div>}
    </div>
  );
}

function GapRow({ g, rank, max, owned, onAdd }: { g: GapSkill; rank: number; max: number; owned: boolean; onAdd: () => void }) {
  return (
    <li>
      <div className="flex items-baseline gap-2">
        <span className="w-5 text-sm muted">{rank}.</span>
        <span className="font-medium">{g.message}</span>
      </div>
      <div className="ml-7 mt-1.5 h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800">
        <div className="h-full rounded-full bg-brand-500" style={{ width: `${(g.total_gain / max) * 100}%` }} />
      </div>
      <div className="ml-7 mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs muted">
        <span>For example:</span>
        {g.example_jobs.map((j) => (
          <Link key={j.id} to={`/jobs?job=${j.id}`} className="link">
            {j.title} at {j.company}
          </Link>
        ))}
        {!owned && (
          <button className="ml-auto link" onClick={onAdd}>
            I already know this
          </button>
        )}
      </div>
    </li>
  );
}
