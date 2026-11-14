import { useEffect, useState, type FormEvent } from "react";
import { Search, X } from "lucide-react";
import type { JobFilters } from "../lib/types";

const EXPERIENCE: Record<string, [string?, string?]> = {
  "": [],
  "0-1": ["0", "1"],
  "1-3": ["1", "3"],
  "3-5": ["3", "5"],
  "5+": ["5", undefined],
};

function expKey(f: JobFilters): string {
  const hit = Object.entries(EXPERIENCE).find(([, [a, b]]) => (a ?? "") === (f.min_exp ?? "") && (b ?? "") === (f.max_exp ?? ""));
  return hit ? hit[0] : "";
}

interface Props {
  value: JobFilters;
  onChange: (f: JobFilters) => void;
}

export function FilterBar({ value, onChange }: Props) {
  const [role, setRole] = useState(value.role ?? "");
  const [location, setLocation] = useState(value.location ?? "");
  useEffect(() => {
    setRole(value.role ?? "");
    setLocation(value.location ?? "");
  }, [value.role, value.location]);

  const set = (patch: Partial<JobFilters>) => onChange({ ...value, ...patch });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    set({ role: role.trim() || undefined, location: location.trim() || undefined });
  };
  const active = Object.values(value).some(Boolean);

  const select = "input w-auto min-w-0 py-1.5";
  return (
    <div className="card p-3">
      <form onSubmit={submit} className="flex flex-col gap-2 sm:flex-row">
        <label className="sr-only" htmlFor="f-role">
          Role or keyword
        </label>
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 muted" aria-hidden />
          <input
            id="f-role"
            className="input pl-8"
            placeholder="Role, e.g. data analyst"
            value={role}
            onChange={(e) => setRole(e.target.value)}
          />
        </div>
        <label className="sr-only" htmlFor="f-loc">
          Location
        </label>
        <input
          id="f-loc"
          className="input sm:w-56"
          placeholder="City or country"
          value={location}
          onChange={(e) => setLocation(e.target.value)}
        />
        <button className="btn-primary" type="submit">
          Search
        </button>
      </form>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <select
          aria-label="Work mode"
          className={select}
          value={value.remote ?? ""}
          onChange={(e) => set({ remote: (e.target.value || undefined) as JobFilters["remote"] })}
        >
          <option value="">Remote or onsite</option>
          <option value="true">Remote</option>
          <option value="false">Onsite / hybrid</option>
        </select>
        <select aria-label="Job type" className={select} value={value.type ?? ""} onChange={(e) => set({ type: e.target.value || undefined })}>
          <option value="">Any job type</option>
          <option value="internship">Internship</option>
          <option value="full-time">Full-time</option>
          <option value="contract">Contract</option>
          <option value="part-time">Part-time</option>
        </select>
        <select
          aria-label="Experience"
          className={select}
          value={expKey(value)}
          onChange={(e) => {
            const [a, b] = EXPERIENCE[e.target.value];
            set({ min_exp: a, max_exp: b });
          }}
        >
          <option value="">Any experience</option>
          <option value="0-1">0-1 years</option>
          <option value="1-3">1-3 years</option>
          <option value="3-5">3-5 years</option>
          <option value="5+">5+ years</option>
        </select>
        <select aria-label="Source" className={select} value={value.source ?? ""} onChange={(e) => set({ source: e.target.value || undefined })}>
          <option value="">All sources</option>
          <option value="greenhouse,lever,ashby">Company career sites</option>
          <option value="jsearch,serpapi">LinkedIn / Naukri / Indeed (Google Jobs)</option>
          <option value="adzuna">Adzuna</option>
          <option value="jooble">Jooble</option>
          <option value="remotive">Remotive</option>
          <option value="import">My imports</option>
        </select>
        <select
          aria-label="Date posted"
          className={select}
          value={value.posted_within ?? ""}
          onChange={(e) => set({ posted_within: e.target.value || undefined })}
        >
          <option value="">Any time</option>
          <option value="1">Past 24 hours</option>
          <option value="7">Past week</option>
          <option value="30">Past month</option>
        </select>
        {active && (
          <button className="btn-ghost px-2 py-1.5 text-xs" onClick={() => onChange({})}>
            <X className="h-3.5 w-3.5" aria-hidden />
            Clear filters
          </button>
        )}
      </div>
    </div>
  );
}
