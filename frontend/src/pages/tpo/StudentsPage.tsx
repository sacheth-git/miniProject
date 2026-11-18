import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, Download, Upload } from "lucide-react";
import { api, type StudentRow } from "../../lib/api";
import { download, tpo, type ImportPreview, type ImportStatus } from "../../lib/tpo";
import { DataTable, type Column } from "../../components/DataTable";
import { Chip, ErrorNote, Spinner } from "../../components/ui";

const TEMPLATE = "roll_no,name,email,branch,batch,cgpa,active_backlogs,history_backlogs,tenth,twelfth,diploma,gender\n4XX22CS001,Asha Rao,asha@college.edu,CSE,2026,8.4,0,0,91,88,,female\n";

const CONSENT: Record<StudentRow["consent_status"], JSX.Element> = {
  given: <Chip tone="green">Given</Chip>,
  pending: <Chip tone="slate">Pending</Chip>,
  withdrawn: <Chip tone="amber">Withdrawn</Chip>,
};

export function StudentsPage() {
  const inst = useQuery({ queryKey: ["tpo", "institution"], queryFn: api.tpoInstitution });
  const students = useQuery({ queryKey: ["tpo", "students"], queryFn: api.tpoStudents });
  const [importing, setImporting] = useState(false);
  const [q, setQ] = useState("");
  const [copied, setCopied] = useState(false);

  const cols: Column<StudentRow>[] = [
    { key: "roll_no", header: "Roll no.", render: (s) => <span className="font-mono text-xs">{s.roll_no ?? "-"}</span> },
    { key: "full_name", header: "Name", render: (s) => <>{s.full_name}<span className="block text-xs muted">{s.email}</span></> },
    { key: "branch", header: "Branch" },
    { key: "batch_year", header: "Batch", align: "right" },
    { key: "cgpa", header: "CGPA", align: "right", render: (s) => s.cgpa?.toFixed(2) ?? "-" },
    { key: "active_backlogs", header: "Backlogs", align: "right" },
    { key: "placed_status", header: "Placement", render: (s) => (s.placed_status === "unplaced" ? <span className="muted">Unplaced</span> : <Chip tone={s.placed_status === "placed" ? "green" : "blue"}>{s.placed_status === "placed" ? "Placed" : "Has offer"}</Chip>) },
    { key: "has_resume", header: "Resume", sortValue: (s) => (s.has_resume ? 1 : 0), render: (s) => (s.has_resume ? "Uploaded" : <span className="text-amber-700 dark:text-amber-300">Missing</span>) },
    { key: "consent_status", header: "Consent", render: (s) => CONSENT[s.consent_status] },
  ];

  return (
    <div className="page">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm muted">Placement office</p>
          <h1 className="text-2xl font-semibold">{inst.data?.name ?? "Students"}</h1>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          {inst.data && (
            <div className="card flex items-center gap-3 px-3 py-2">
              <div>
                <p className="text-[11px] muted">Student invite code</p>
                <p className="font-mono font-semibold tracking-widest">{inst.data.invite_code}</p>
              </div>
              <button className="btn-ghost h-8 w-8 p-0" aria-label="Copy invite code" onClick={() => navigator.clipboard?.writeText(inst.data!.invite_code).then(() => setCopied(true))}>
                <Copy className="h-4 w-4" />
              </button>
              {copied && <span className="text-xs muted">Copied</span>}
            </div>
          )}
          <button className="btn-primary" onClick={() => setImporting((v) => !v)} aria-expanded={importing}>
            <Upload className="h-4 w-4" aria-hidden /> Import students
          </button>
        </div>
      </div>

      {importing && <ImportWizard onClose={() => setImporting(false)} />}

      <section className="card overflow-hidden" aria-labelledby="roster-h">
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3 dark:border-slate-800">
          <h2 id="roster-h" className="font-semibold">
            Students <span className="font-normal muted">({students.data?.length ?? 0})</span>
          </h2>
          <input aria-label="Search students" className="input w-64 py-1.5" placeholder="Search name, roll no., branch" value={q} onChange={(e) => setQ(e.target.value)} />
        </header>
        {students.isLoading && <div className="p-5"><Spinner /></div>}
        {students.error && <div className="p-5"><ErrorNote error={students.error} /></div>}
        {students.data && (
          <DataTable
            caption="Students"
            rows={students.data}
            columns={cols}
            rowKey={(s) => s.user_id}
            initialSort={{ key: "roll_no", dir: "asc" }}
            filter={q}
            filterText={(s) => `${s.full_name} ${s.roll_no} ${s.branch} ${s.email}`}
            empty="No students yet. Share the invite code or import a CSV."
          />
        )}
      </section>
    </div>
  );
}

function ImportWizard({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [csv, setCsv] = useState<File | null>(null);
  const [zip, setZip] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [dlError, setDlError] = useState<unknown>(null);

  const doPreview = useMutation({ mutationFn: () => tpo.importPreview(csv!, zip), onSuccess: setPreview });
  const commit = useMutation({ mutationFn: () => tpo.importCommit(preview!.job_id), onSuccess: (s) => setJobId(s.job_id) });
  const status = useQuery({
    queryKey: ["tpo", "import", jobId],
    queryFn: () => tpo.importStatus(jobId!),
    enabled: !!jobId,
    refetchInterval: (q) => ((q.state.data as ImportStatus | undefined)?.status === "running" ? 1000 : false),
  });
  const st = status.data;
  useEffect(() => {
    if (st?.status === "done") qc.invalidateQueries({ queryKey: ["tpo", "students"] });
  }, [st?.status, qc]);

  const templateHref = `data:text/csv;charset=utf-8,${encodeURIComponent(TEMPLATE)}`;
  const rows = preview ? (showAll ? preview.rows : preview.rows.filter((r) => r.status !== "ok")) : [];

  return (
    <section className="card p-5" aria-labelledby="import-h">
      <div className="flex items-start justify-between">
        <h2 id="import-h" className="font-semibold">Import students</h2>
        <button className="btn-ghost h-8 px-2 text-xs" onClick={onClose}>Close</button>
      </div>

      {!preview && (
        <div className="mt-3 space-y-4">
          <p className="text-sm muted">
            Upload a CSV with one row per student, and optionally a ZIP of resumes named by roll number (e.g. <span className="font-mono">4XX22CS001.pdf</span>).
            Nothing changes until you review the preview and confirm.{" "}
            <a href={templateHref} download="students-template.csv" className="link">Download CSV template</a>
          </p>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="label" htmlFor="csv">Students CSV</label>
              <input id="csv" type="file" accept=".csv,text/csv" className="block w-full text-sm" onChange={(e) => setCsv(e.target.files?.[0] ?? null)} />
            </div>
            <div>
              <label className="label" htmlFor="zip">Resumes ZIP (optional)</label>
              <input id="zip" type="file" accept=".zip,application/zip" className="block w-full text-sm" onChange={(e) => setZip(e.target.files?.[0] ?? null)} />
            </div>
          </div>
          <button className="btn-primary" disabled={!csv || doPreview.isPending} onClick={() => doPreview.mutate()}>
            {doPreview.isPending ? "Checking file" : "Preview import"}
          </button>
          {doPreview.error && <ErrorNote error={doPreview.error} />}
        </div>
      )}

      {preview && !jobId && (
        <div className="mt-3 space-y-4">
          <div className="flex flex-wrap gap-2 text-sm">
            <Chip tone="green">{preview.ok} ready</Chip>
            <Chip tone="amber">{preview.warnings} with warnings</Chip>
            <Chip tone="red">{preview.errors} with errors (skipped)</Chip>
            <Chip>{preview.creates} new accounts</Chip>
            <Chip>{preview.updates} updates</Chip>
            <Chip>{preview.with_resume} resumes</Chip>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} /> Show all rows (default: only rows with problems)
          </label>
          <div className="max-h-96 overflow-auto rounded-md border border-slate-200 dark:border-slate-800">
            <table className="w-full text-sm">
              <caption className="sr-only">Import preview</caption>
              <thead className="sticky top-0 bg-slate-50 text-left text-xs muted dark:bg-slate-900">
                <tr><th className="px-3 py-2">Line</th><th className="px-3 py-2">Roll no.</th><th className="px-3 py-2">Name</th><th className="px-3 py-2">Status</th><th className="px-3 py-2">Details</th></tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {rows.map((r) => (
                  <tr key={r.line}>
                    <td className="px-3 py-1.5 tabular-nums">{r.line}</td>
                    <td className="px-3 py-1.5 font-mono text-xs">{r.roll_no || "-"}</td>
                    <td className="px-3 py-1.5">{r.name}</td>
                    <td className="px-3 py-1.5">{r.status === "error" ? <Chip tone="red">Error</Chip> : r.status === "warning" ? <Chip tone="amber">Warning</Chip> : <Chip tone="green">{r.action === "update" ? "Update" : "New"}</Chip>}</td>
                    <td className="px-3 py-1.5 text-xs">{[...r.errors, ...r.warnings].join("; ") || (r.has_resume ? "Resume found" : "")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {rows.length === 0 && <p className="p-4 text-center text-sm muted">No problems found.</p>}
          </div>
          <div className="flex gap-2">
            <button className="btn-primary" disabled={preview.ok + preview.warnings === 0 || commit.isPending} onClick={() => commit.mutate()}>
              Import {preview.ok + preview.warnings} students
            </button>
            <button className="btn-secondary" onClick={() => setPreview(null)}>Choose other files</button>
          </div>
          {commit.error && <ErrorNote error={commit.error} />}
        </div>
      )}

      {jobId && st && (
        <div className="mt-3 space-y-3" aria-live="polite">
          <div className="flex justify-between text-sm">
            <span>{st.status === "running" ? "Importing and reading resumes" : st.status === "done" ? "Import finished" : `Import ${st.status}`}</span>
            <span className="muted">{st.done} / {st.total}</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800" role="progressbar" aria-valuemin={0} aria-valuemax={st.total} aria-valuenow={st.done}>
            <div className="h-full bg-brand-500 transition-all" style={{ width: `${(st.done / Math.max(1, st.total)) * 100}%` }} />
          </div>
          {st.status === "done" && (
            <>
              <p className="text-sm">{st.created} accounts created, {st.updated} updated, {st.resumes_parsed} resumes read.</p>
              {st.credentials_available && (
                <div className="rounded-md bg-amber-50 p-3 text-sm dark:bg-amber-950">
                  <p>New students sign in with a temporary password and must set their own. This file is available <b>once</b>; share each login privately.</p>
                  <button
                    className="btn-secondary mt-2"
                    onClick={() => download(`/tpo/students/import/${jobId}/credentials`, "student-logins.csv").then(() => status.refetch()).catch(setDlError)}
                  >
                    <Download className="h-4 w-4" aria-hidden /> Download logins (CSV)
                  </button>
                </div>
              )}
              {dlError !== null && <ErrorNote error={dlError} />}
            </>
          )}
          {st.errors.length > 0 && (
            <ul className="text-xs text-rose-700 dark:text-rose-300">
              {st.errors.map((e) => <li key={e.line}>Line {e.line} ({e.roll_no}): {e.error}</li>)}
            </ul>
          )}
          {st.message && <ErrorNote error={st.message} />}
        </div>
      )}
    </section>
  );
}
