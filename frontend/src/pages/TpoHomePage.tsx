import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Copy } from "lucide-react";
import { api } from "../lib/api";
import { Chip, EmptyState, ErrorNote, Spinner } from "../components/ui";

/** Placement office home: institution, invite code and student roster (drives arrive in 5B). */
export function TpoHomePage() {
  const inst = useQuery({ queryKey: ["tpo", "institution"], queryFn: api.tpoInstitution });
  const students = useQuery({ queryKey: ["tpo", "students"], queryFn: api.tpoStudents });
  const [copied, setCopied] = useState(false);

  return (
    <div className="mx-auto max-w-6xl space-y-6 px-4 py-8">
      {inst.error && <ErrorNote error={inst.error} />}
      {inst.data && (
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-sm muted">Placement office</p>
            <h1 className="text-2xl font-semibold tracking-tight">{inst.data.name}</h1>
          </div>
          <div className="card flex items-center gap-3 px-4 py-3">
            <div>
              <p className="text-xs muted">Student invite code</p>
              <p className="font-mono text-lg font-semibold tracking-widest">{inst.data.invite_code}</p>
            </div>
            <button
              className="btn-secondary px-2 py-1.5 text-xs"
              onClick={() => {
                navigator.clipboard?.writeText(inst.data!.invite_code).then(() => setCopied(true));
              }}
            >
              <Copy className="h-3.5 w-3.5" aria-hidden />
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
        </div>
      )}

      <section className="card overflow-hidden" aria-labelledby="roster-h">
        <header className="flex items-baseline justify-between border-b border-slate-200 px-5 py-3 dark:border-slate-800">
          <h2 id="roster-h" className="font-semibold">Students</h2>
          <span className="text-sm muted">{students.data?.length ?? 0} joined</span>
        </header>
        {students.isLoading && <div className="p-5"><Spinner /></div>}
        {students.error && <div className="p-5"><ErrorNote error={students.error} /></div>}
        {students.data && students.data.length === 0 && (
          <div className="p-5">
            <EmptyState title="No students yet">
              Share the invite code above. Bulk import from a CSV arrives with campus drives.
            </EmptyState>
          </div>
        )}
        {students.data && students.data.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-left text-xs muted dark:bg-slate-900">
                <tr>
                  <th scope="col" className="px-5 py-2 font-medium">Roll no.</th>
                  <th scope="col" className="px-5 py-2 font-medium">Name</th>
                  <th scope="col" className="px-5 py-2 font-medium">Branch</th>
                  <th scope="col" className="px-5 py-2 font-medium">CGPA</th>
                  <th scope="col" className="px-5 py-2 font-medium">Resume</th>
                  <th scope="col" className="px-5 py-2 font-medium">Consent</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {students.data.map((s) => (
                  <tr key={s.user_id}>
                    <td className="px-5 py-2 font-mono text-xs">{s.roll_no ?? "-"}</td>
                    <td className="px-5 py-2">{s.full_name}<span className="block text-xs muted">{s.email}</span></td>
                    <td className="px-5 py-2">{s.branch ?? "-"}</td>
                    <td className="px-5 py-2">{s.cgpa ?? "-"}</td>
                    <td className="px-5 py-2">{s.has_resume ? "Uploaded" : <span className="muted">Missing</span>}</td>
                    <td className="px-5 py-2">{s.consent ? <Chip tone="green">Given</Chip> : <Chip tone="amber">Withdrawn</Chip>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
