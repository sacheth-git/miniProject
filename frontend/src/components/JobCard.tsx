import { Building2, Clock, MapPin } from "lucide-react";
import { experienceLabel, jobTypeLabel, timeAgo } from "../lib/format";
import type { JobSummary, MatchItem } from "../lib/types";
import { ApplyMenu } from "./ApplyMenu";
import { SaveButton } from "./SaveButton";
import { Chip, MatchRing, SourceBadge } from "./ui";

interface Props {
  job: JobSummary;
  match?: MatchItem;
  selected: boolean;
  onSelect: () => void;
}

export function JobCard({ job, match, selected, onSelect }: Props) {
  const exp = experienceLabel(job.experience_min, job.experience_max);
  const matched = match?.matched_skills.slice(0, 3) ?? [];
  const missing = match?.missing_required.slice(0, 3) ?? [];
  const keySkills = !match ? job.required_skills.slice(0, 4) : [];

  return (
    <article
      className={`card cursor-pointer p-4 transition-shadow hover:shadow-sm ${
        selected ? "border-brand-500 ring-1 ring-brand-500 dark:border-brand-500" : ""
      }`}
      onClick={onSelect}
      aria-current={selected ? "true" : undefined}
    >
      <div className="flex gap-3">
        <div className="min-w-0 flex-1">
          <h3 className="text-[15px] font-semibold leading-snug">
            <button
              className="text-left hover:text-brand-600 hover:underline focus-visible:underline focus-visible:outline-none"
              onClick={(e) => {
                e.stopPropagation();
                onSelect();
              }}
            >
              {job.title}
            </button>
          </h3>
          <p className="mt-0.5 flex items-center gap-1 text-sm text-slate-700 dark:text-slate-300">
            <Building2 className="h-3.5 w-3.5 muted" aria-hidden />
            {job.company}
          </p>
          <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs muted">
            <span className="inline-flex items-center gap-1">
              <MapPin className="h-3.5 w-3.5" aria-hidden />
              {job.location || (job.remote ? "Remote" : "Location not listed")}
              {job.remote && job.location && !/remote/i.test(job.location) ? " (Remote)" : ""}
            </span>
            <span>{jobTypeLabel(job.job_type)}</span>
            {exp && <span>{exp}</span>}
            <span className="inline-flex items-center gap-1">
              <Clock className="h-3.5 w-3.5" aria-hidden />
              {timeAgo(job.posted_at)}
            </span>
          </p>
        </div>
        {match && <MatchRing percent={match.match_percent} />}
      </div>

      {(matched.length > 0 || missing.length > 0 || keySkills.length > 0) && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {matched.map((m) => (
            <Chip key={m.skill_id} tone="green" title={m.resume_skill ? `You have: ${m.resume_skill}` : undefined}>
              {m.name}
            </Chip>
          ))}
          {missing.map((m) => (
            <Chip key={m.skill_id} tone="red" title="Required, not found in your resume">
              {m.name}
            </Chip>
          ))}
          {keySkills.map((s) => (
            <Chip key={s.skill_id}>{s.name}</Chip>
          ))}
        </div>
      )}

      <div className="mt-3 flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
        <SourceBadge source={job.source} />
        <div className="ml-auto flex gap-2">
          <SaveButton job={job} size="sm" />
          <ApplyMenu job={job} size="sm" />
        </div>
      </div>
    </article>
  );
}
