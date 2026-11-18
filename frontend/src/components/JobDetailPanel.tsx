import { useQuery } from "@tanstack/react-query";
import { Building2, CheckCircle2, CircleAlert, CircleMinus, MapPin, X } from "lucide-react";
import { api } from "../lib/api";
import { useCandidate } from "../lib/candidate";
import { experienceLabel, hostOf, jobTypeLabel, pct, timeAgo } from "../lib/format";
import type { Explanation, SkillMatch } from "../lib/types";
import { ApplyMenu } from "./ApplyMenu";
import { SaveButton } from "./SaveButton";
import { Chip, ErrorNote, MatchRing, ScoreBar, SourceBadge, Spinner } from "./ui";

const CONTEXT_LABELS: Record<string, string> = {
  experience: "Experience level",
  job_type: "Job type",
  location: "Location",
  education: "Education",
};

export function JobDetailPanel({ jobId, onClose }: { jobId: string; onClose?: () => void }) {
  const { candidateId } = useCandidate();
  const job = useQuery({ queryKey: ["job", jobId], queryFn: () => api.job(jobId) });
  const why = useQuery({
    queryKey: ["explain", candidateId, jobId],
    queryFn: () => api.explain(candidateId!, jobId),
    enabled: !!candidateId,
  });

  if (job.isLoading) return <div className="p-6"><Spinner label="Loading job" /></div>;
  if (job.error) return <div className="p-6"><ErrorNote error={job.error} /></div>;
  const j = job.data!;
  const exp = experienceLabel(j.experience_min, j.experience_max);

  return (
    <div className="flex h-full flex-col">
      <header className="border-b border-slate-200 p-5 dark:border-slate-800">
        <div className="flex items-start gap-3">
          <div className="min-w-0 flex-1">
            <h2 className="text-xl font-semibold leading-tight">{j.title}</h2>
            <p className="mt-1 flex items-center gap-1 text-sm">
              <Building2 className="h-4 w-4 muted" aria-hidden />
              {j.company}
            </p>
            <p className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-sm muted">
              <span className="inline-flex items-center gap-1">
                <MapPin className="h-4 w-4" aria-hidden />
                {j.location || "Location not listed"}
                {j.remote ? " · Remote" : ""}
              </span>
              <span>{jobTypeLabel(j.job_type)}</span>
              {exp && <span>{exp}</span>}
              <span>Posted {timeAgo(j.posted_at).toLowerCase()}</span>
            </p>
          </div>
          {why.data && <MatchRing percent={Math.round(why.data.score * 100)} size={60} />}
          {onClose && (
            <button className="btn-ghost h-8 w-8 p-0" onClick={onClose} aria-label="Close job details">
              <X className="h-5 w-5" />
            </button>
          )}
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <ApplyMenu job={j} />
          <SaveButton job={j} />
          <span className="ml-auto flex items-center gap-2 text-xs muted">
            <SourceBadge source={j.source} publisher={j.apply_options[0]?.publisher} />
            {hostOf(j.apply_url)}
          </span>
        </div>
        {!j.is_active && (
          <p className="mt-3 rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:bg-amber-950 dark:text-amber-200">
            This posting looks closed: the employer's page no longer lists it.
          </p>
        )}
      </header>

      <div className="flex-1 space-y-6 overflow-y-auto p-5">
        {candidateId && (
          <section aria-labelledby="why-h">
            <h3 id="why-h" className="text-base font-semibold">
              Why this score
            </h3>
            {why.isLoading && <Spinner label="Scoring against your resume" />}
            {why.error && <ErrorNote error={why.error} />}
            {why.data && <Why e={why.data} />}
          </section>
        )}
        {!candidateId && j.required_skills.length + j.preferred_skills.length > 0 && (
          <section>
            <h3 className="text-base font-semibold">Skills in this job</h3>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {[...j.required_skills, ...j.preferred_skills].map((s) => (
                <Chip key={s.skill_id} tone={s.type === "required" ? "blue" : "slate"}>
                  {s.name}
                </Chip>
              ))}
            </div>
          </section>
        )}
        <section aria-labelledby="jd-h">
          <h3 id="jd-h" className="text-base font-semibold">
            About the job
          </h3>
          <div className="mt-2 whitespace-pre-line text-sm leading-relaxed text-slate-700 dark:text-slate-300">{j.description}</div>
        </section>
      </div>
    </div>
  );
}

function Why({ e }: { e: Explanation }) {
  return (
    <div className="mt-2 space-y-4">
      <p className="text-sm">{e.summary}</p>
      <div className="grid gap-3 sm:grid-cols-3">
        <ScoreBar label="Skills" value={e.skill} hint="Weighted by how important each skill is to this job" />
        <ScoreBar label="Relevance" value={e.sem} hint="How closely your experience and projects match the role" />
        <ScoreBar label="Fit" value={e.context} hint="Experience level, job type, location, education" />
      </div>
      {e.penalty > 0 && (
        <p className="text-xs muted">
          {pct(e.penalty)} of required skills are missing, which lowers the score by {pct(e.weights.delta * e.penalty)}.
        </p>
      )}
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs muted">
        {Object.entries(e.context_parts).map(([k, v]) => (
          <span key={k}>
            {CONTEXT_LABELS[k] ?? k}: {pct(v)}
          </span>
        ))}
      </div>
      <SkillList title="Skills you have" icon="ok" items={e.matched} />
      <SkillList title="Required skills you're missing" icon="missing" items={e.missing_required} />
      <SkillList title="Nice-to-have skills you're missing" icon="pref" items={e.missing_preferred} />
    </div>
  );
}

function SkillList({ title, icon, items }: { title: string; icon: "ok" | "missing" | "pref"; items: SkillMatch[] }) {
  if (!items.length) return null;
  const Icon = icon === "ok" ? CheckCircle2 : icon === "missing" ? CircleAlert : CircleMinus;
  const color = icon === "ok" ? "text-emerald-600" : icon === "missing" ? "text-rose-600" : "text-slate-400";
  return (
    <div>
      <h4 className="text-sm font-semibold">
        {title} <span className="font-normal muted">({items.length})</span>
      </h4>
      <ul className="mt-2 divide-y divide-slate-100 dark:divide-slate-800">
        {items.map((m) => (
          <li key={m.skill_id} className="flex gap-2 py-2 text-sm">
            <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${color}`} aria-hidden />
            <div className="min-w-0">
              <p>
                <span className="font-medium">{m.name}</span>
                <span className="ml-2 text-xs muted">
                  {m.type}
                  {icon === "ok" && m.resume_skill && m.resume_skill !== m.name && ` · via ${m.resume_skill} (${pct(m.similarity)} similar)`}
                </span>
              </p>
              {icon === "ok" && m.resume_evidence && (
                <p className="mt-0.5 text-xs muted">
                  <span className="font-medium text-slate-600 dark:text-slate-300">Your resume:</span> {m.resume_evidence}
                </p>
              )}
              {m.jd_evidence && (
                <p className="mt-0.5 text-xs muted">
                  <span className="font-medium text-slate-600 dark:text-slate-300">Job:</span> {m.jd_evidence}
                </p>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
