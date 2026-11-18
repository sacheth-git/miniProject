import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { analytics } from "../lib/tpo";
import { PageError, PageLoading } from "../components/ui";

/** Public, read-only recruiter view of a drive shortlist (no sign-in; the link expires). */
export function SharePage() {
  const { token = "" } = useParams();
  const q = useQuery({ queryKey: ["share", token], queryFn: () => analytics.shared(token), retry: false });
  if (q.isLoading) return <PageLoading />;
  if (q.error) return <PageError error={q.error} />;
  const s = q.data!;
  const cell = (v: unknown) => (Array.isArray(v) ? v.join(", ") : v === null || v === undefined ? "-" : String(v));
  return (
    <div className="page">
      <div>
        <p className="text-sm muted">{s.institution} · shared shortlist</p>
        <h1 className="text-2xl font-semibold">{s.company}: {s.role}</h1>
        <p className="mt-1 text-sm muted">
          {s.location ?? ""}{s.ctc_lpa ? ` · ${s.ctc_lpa} LPA` : ""}{s.rounds.length ? ` · Rounds: ${s.rounds.join(" → ")}` : ""}
        </p>
        <p className="mt-1 text-xs muted">
          Read-only{s.blind ? ", names hidden" : ""}. This link expires on {new Date(s.expires_at).toLocaleString()}.
        </p>
      </div>
      <section className="card overflow-x-auto">
        <table className="w-full text-sm">
          <caption className="sr-only">Shortlisted students</caption>
          <thead className="bg-slate-50 text-left text-xs muted dark:bg-slate-900">
            <tr>{s.columns.map((c) => <th key={c.key} scope="col" className="px-3 py-2 font-medium">{c.label}</th>)}</tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {s.rows.map((r, i) => <tr key={i}>{s.columns.map((c) => <td key={c.key} className="px-3 py-2">{cell(r[c.key])}</td>)}</tr>)}
          </tbody>
        </table>
        {s.rows.length === 0 && <p className="p-5 text-center text-sm muted">No students are shortlisted yet.</p>}
      </section>
      <p className="text-xs muted">Shortlist prepared by the placement office with SkillMatch. Rankings are recommendations; the placement office made the final selection.</p>
    </div>
  );
}
