import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { analytics, type FairnessRow, type SkillGap, type UnplacedStudent } from "../../lib/tpo";
import { SEQ } from "../../components/charts";
import { DataTable, type Column } from "../../components/DataTable";
import { Chip, ErrorNote, Spinner } from "../../components/ui";

export function AnalyticsPage() {
  return (
    <div className="mx-auto max-w-7xl space-y-6 px-4 py-8">
      <h1 className="text-2xl font-semibold tracking-tight">Placement analytics</h1>
      <SkillGapSection />
      <FairnessSection />
      <UnplacedSection />
    </div>
  );
}

/** 0-100 % missing -> sequential blue step; text flips to white on the darker steps. */
function cellStyle(pct: number): { background: string; color: string } {
  const step = Math.min(SEQ.length - 1, Math.floor((pct / 100) * SEQ.length));
  return { background: SEQ[step], color: step >= 3 ? "#ffffff" : "#0b0b0b" };
}

function SkillGapSection() {
  const q = useQuery({ queryKey: ["tpo", "skill-gap"], queryFn: analytics.skillGap });
  return (
    <section className="card p-5" aria-labelledby="sg-h">
      <h2 id="sg-h" className="font-semibold">Batch skill gap</h2>
      <p className="mt-1 text-sm muted">Share of students in each branch missing a skill that drives require (consenting students with a resume).</p>
      {q.isLoading && <div className="mt-4"><Spinner /></div>}
      {q.error && <div className="mt-4"><ErrorNote error={q.error} /></div>}
      {q.data && q.data.skills.length === 0 && <p className="mt-4 text-sm muted">No drive lists required skills yet.</p>}
      {q.data && q.data.skills.length > 0 && <Heatmap g={q.data} />}
      {q.data && q.data.recommendations.length > 0 && (
        <div className="mt-5">
          <h3 className="text-sm font-semibold">Training recommendations</h3>
          <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm">{q.data.recommendations.map((r) => <li key={r.text}>{r.text}</li>)}</ol>
        </div>
      )}
    </section>
  );
}

function Heatmap({ g }: { g: SkillGap }) {
  const cell = new Map(g.cells.map((c) => [`${c.branch}|${c.skill_id}`, c]));
  return (
    <div className="mt-4 overflow-x-auto">
      <table className="border-separate text-xs" style={{ borderSpacing: 2 }}>
        <caption className="sr-only">Percentage of students missing each demanded skill, by branch</caption>
        <thead>
          <tr>
            <th scope="col" className="px-2 text-left font-medium muted">Branch</th>
            {g.skills.map((s) => (
              <th key={s.skill_id} scope="col" className="h-24 w-12 align-bottom font-medium" title={`Required by ${s.drives} drive(s)`}>
                <span className="inline-block origin-bottom-left -rotate-45 translate-x-3 whitespace-nowrap">{s.name}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {g.branches.map((b) => (
            <tr key={b}>
              <th scope="row" className="px-2 text-left font-medium">{b}</th>
              {g.skills.map((s) => {
                const c = cell.get(`${b}|${s.skill_id}`);
                if (!c) return <td key={s.skill_id} />;
                return (
                  <td key={s.skill_id} style={cellStyle(c.missing_pct)} className="h-9 w-12 rounded text-center tabular-nums"
                    title={`${c.missing_pct}% of ${c.students} ${b} students lack ${c.skill}; required by ${c.drives_demanding} drive(s) open to ${b}`}>
                    {c.missing_pct}%
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-2 flex items-center gap-2 text-[11px] muted" aria-hidden>
        <span>0% missing</span>
        {SEQ.map((c) => <span key={c} className="h-3 w-6 rounded-sm" style={{ background: c }} />)}
        <span>100% missing</span>
      </div>
    </div>
  );
}

function ParityChip({ v }: { v: number | null }) {
  if (v === null) return <Chip>n/a</Chip>;
  return <Chip tone={v >= 0.8 ? "green" : "amber"}>{v.toFixed(2)}{v < 0.8 ? " · review" : ""}</Chip>;
}

function FairnessSection() {
  const q = useQuery({ queryKey: ["tpo", "fairness"], queryFn: analytics.fairness });
  const table = (title: string, rows: FairnessRow[], sp: number | null, ap: number | null) => (
    <div>
      <h3 className="text-sm font-semibold">{title}</h3>
      <table className="mt-2 w-full text-sm">
        <thead className="text-left text-xs muted"><tr><th className="py-1">Group</th><th className="text-right">Eligible</th><th className="text-right">System top-K rate</th><th className="text-right">Actual shortlist rate</th></tr></thead>
        <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
          {rows.map((r) => (
            <tr key={r.group}>
              <td className="py-1 capitalize">{r.group}</td>
              {r.suppressed ? <td colSpan={3} className="text-right text-xs muted">Hidden: fewer than {q.data?.min_group} students</td> : (
                <><td className="text-right tabular-nums">{r.eligible}</td><td className="text-right tabular-nums">{r.system_rate}%</td><td className="text-right tabular-nums">{r.actual_rate}%</td></>
              )}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 flex flex-wrap items-center gap-2 text-xs">Parity, system: <ParityChip v={sp} /> actual: <ParityChip v={ap} /></p>
    </div>
  );
  return (
    <section className="card p-5" aria-labelledby="fr-h">
      <h2 id="fr-h" className="font-semibold">Fairness report</h2>
      {q.isLoading && <div className="mt-3"><Spinner /></div>}
      {q.error && <div className="mt-3"><ErrorNote error={q.error} /></div>}
      {q.data && (
        <>
          <p className="mt-1 text-sm muted">{q.data.note} Based on {q.data.drives_used} drive(s) with a shortlist.</p>
          <div className="mt-4 grid gap-6 md:grid-cols-2">
            {table("By gender", q.data.gender.rows, q.data.gender.system_parity, q.data.gender.actual_parity)}
            {table("By branch", q.data.branch.rows, q.data.branch.system_parity, q.data.branch.actual_parity)}
          </div>
        </>
      )}
    </section>
  );
}

function UnplacedSection() {
  const q = useQuery({ queryKey: ["tpo", "unplaced"], queryFn: analytics.unplaced });
  const [filter, setFilter] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const jobs = useMutation({ mutationFn: (uid: string) => analytics.unplacedJobs(uid) });
  const cols: Column<UnplacedStudent>[] = [
    { key: "roll_no", header: "Roll no.", render: (s) => <span className="font-mono text-xs">{s.roll_no}</span> },
    { key: "name", header: "Name" },
    { key: "branch", header: "Branch" },
    { key: "cgpa", header: "CGPA", align: "right", render: (s) => s.cgpa?.toFixed(2) ?? "-" },
    { key: "best", header: "Best-fit open drives", sortable: false, render: (s) =>
      s.best_drives.length ? (
        <ul className="text-xs">{s.best_drives.map((d) => <li key={d.drive_id}><Link className="text-brand-600 hover:underline" to={`/tpo/drives/${d.drive_id}`}>{d.company}</Link> · {d.match_percent}%</li>)}</ul>
      ) : <span className="text-xs muted">{s.has_resume ? "No eligible open drive" : "No resume"}</span> },
    { key: "jobs", header: "Open-market jobs", sortable: false, render: (s) =>
      open === s.user_id && jobs.data ? (
        <ul className="text-xs">{jobs.data.map((j) => <li key={j.job_id}><a className="text-brand-600 hover:underline" href={j.apply_url} target="_blank" rel="noopener noreferrer">{j.title}</a> · {j.company} · {j.match_percent}%</li>)}{jobs.data.length === 0 && <li className="muted">None found</li>}</ul>
      ) : (
        <button className="btn-ghost px-2 py-1 text-xs" disabled={!s.has_resume || (jobs.isPending && open === s.user_id)} onClick={() => { setOpen(s.user_id); jobs.mutate(s.user_id); }}>
          {jobs.isPending && open === s.user_id ? "Finding" : "Find jobs"}
        </button>
      ) },
  ];
  return (
    <section className="card overflow-hidden" aria-labelledby="up-h">
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 px-4 py-3 dark:border-slate-800">
        <h2 id="up-h" className="font-semibold">Unplaced students <span className="font-normal muted">({q.data?.length ?? 0}, consenting only)</span></h2>
        <input aria-label="Filter unplaced students" className="input w-56 py-1" placeholder="Filter" value={filter} onChange={(e) => setFilter(e.target.value)} />
      </header>
      {q.isLoading && <div className="p-5"><Spinner /></div>}
      {q.error && <div className="p-5"><ErrorNote error={q.error} /></div>}
      {jobs.error && <div className="px-4 pt-3"><ErrorNote error={jobs.error} /></div>}
      {q.data && <DataTable caption="Unplaced students" rows={q.data} columns={cols} rowKey={(s) => s.user_id} pageSize={20}
        filter={filter} filterText={(s) => `${s.roll_no} ${s.name} ${s.branch} ${s.best_drives.map((d) => d.company).join(" ")}`} />}
    </section>
  );
}
