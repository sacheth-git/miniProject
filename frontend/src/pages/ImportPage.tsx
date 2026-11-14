import { useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { useCandidate } from "../lib/candidate";
import type { ImportResult } from "../lib/types";
import { ErrorNote } from "../components/ui";

export function ImportPage() {
  const [tab, setTab] = useState<"text" | "email">("text");
  const [result, setResult] = useState<ImportResult | null>(null);
  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <h1 className="text-2xl font-semibold tracking-tight">Import a job</h1>
      <p className="mt-1 muted">
        Found a role somewhere else? Paste its description, or upload job-alert emails you received. Imported jobs are
        private to you and get scored like any other.
      </p>
      <div role="tablist" className="mt-6 flex gap-1 border-b border-slate-200 dark:border-slate-800">
        {(["text", "email"] as const).map((t) => (
          <button
            key={t}
            role="tab"
            aria-selected={tab === t}
            className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium ${
              tab === t ? "border-brand-600 text-brand-700 dark:text-brand-200" : "border-transparent muted hover:text-slate-900 dark:hover:text-white"
            }`}
            onClick={() => {
              setTab(t);
              setResult(null);
            }}
          >
            {t === "text" ? "Paste a job description" : "Job-alert emails"}
          </button>
        ))}
      </div>
      <div className="mt-5">{tab === "text" ? <PasteForm onDone={setResult} /> : <EmailForm onDone={setResult} />}</div>
      {result && (
        <div className="card mt-6 p-5" aria-live="polite">
          <h2 className="font-semibold">
            Imported {result.created + result.updated} job{result.created + result.updated === 1 ? "" : "s"}
          </h2>
          <ul className="mt-3 divide-y divide-slate-100 dark:divide-slate-800">
            {result.jobs.map((j) => (
              <li key={j.id} className="flex items-center justify-between gap-3 py-2 text-sm">
                <span>
                  <span className="font-medium">{j.title}</span> <span className="muted">· {j.company}</span>
                </span>
                <Link to={`/jobs?job=${j.id}&source=import`} className="text-brand-600 hover:underline">
                  View match
                </Link>
              </li>
            ))}
          </ul>
          {result.skipped_files.length > 0 && (
            <ul className="mt-3 text-xs muted">
              {result.skipped_files.map((s) => (
                <li key={s}>Skipped {s}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

function PasteForm({ onDone }: { onDone: (r: ImportResult) => void }) {
  const { candidateId } = useCandidate();
  const qc = useQueryClient();
  const [f, setF] = useState({ title: "", company: "", url: "", location: "", text: "" });
  const m = useMutation({
    mutationFn: () =>
      api.importText({
        text: f.text,
        title: f.title || undefined,
        company: f.company || undefined,
        url: f.url || undefined,
        location: f.location || undefined,
        candidate_id: candidateId ?? undefined,
      }),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["match"] });
      onDone(r);
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    m.mutate();
  };
  const field = (k: keyof typeof f, label: string, placeholder: string, type = "text") => (
    <div>
      <label className="label" htmlFor={`imp-${k}`}>
        {label}
      </label>
      <input id={`imp-${k}`} type={type} className="input" placeholder={placeholder} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} />
    </div>
  );
  return (
    <form onSubmit={submit} className="card space-y-4 p-5">
      <div className="grid gap-4 sm:grid-cols-2">
        {field("title", "Job title", "e.g. Data Analyst")}
        {field("company", "Company", "e.g. Acme")}
        {field("url", "Link to the job (where you'll apply)", "https://...", "url")}
        {field("location", "Location", "e.g. Pune")}
      </div>
      <div>
        <label className="label" htmlFor="imp-text">
          Job description
        </label>
        <textarea
          id="imp-text"
          className="input min-h-48"
          required
          minLength={30}
          placeholder="Paste the full job description, including requirements"
          value={f.text}
          onChange={(e) => setF({ ...f, text: e.target.value })}
        />
      </div>
      {!candidateId && <p className="text-xs muted">Tip: upload your resume first so this job is scored for you.</p>}
      <button className="btn-primary" disabled={m.isPending}>
        {m.isPending ? "Importing" : "Import job"}
      </button>
      {m.error && <ErrorNote error={m.error} />}
    </form>
  );
}

function EmailForm({ onDone }: { onDone: (r: ImportResult) => void }) {
  const { candidateId } = useCandidate();
  const qc = useQueryClient();
  const [files, setFiles] = useState<File[]>([]);
  const m = useMutation({
    mutationFn: () => api.importEmail(files, candidateId),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["match"] });
      onDone(r);
    },
  });
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        m.mutate();
      }}
      className="card space-y-4 p-5"
    >
      <p className="text-sm">
        In Gmail or Outlook, open a LinkedIn, Naukri or Indeed job alert and save it as a file (<span className="font-mono">.eml</span>
        ). We read only the job titles and links in it, here on the server. Nothing is fetched from those sites.
      </p>
      <div>
        <label className="label" htmlFor="eml">
          Alert emails (.eml, up to 20)
        </label>
        <input
          id="eml"
          type="file"
          multiple
          accept=".eml,message/rfc822"
          className="block w-full text-sm file:mr-3 file:rounded-md file:border file:border-slate-300 file:bg-white file:px-3 file:py-1.5 file:text-sm dark:file:border-slate-700 dark:file:bg-slate-900 dark:file:text-slate-100"
          onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
        />
      </div>
      <button className="btn-primary" disabled={!files.length || m.isPending}>
        {m.isPending ? "Reading emails" : `Import ${files.length || ""} email${files.length === 1 ? "" : "s"}`}
      </button>
      {m.error && <ErrorNote error={m.error} />}
    </form>
  );
}
