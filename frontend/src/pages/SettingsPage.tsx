import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { useCandidate } from "../lib/candidate";
import { EmptyState, ErrorNote } from "../components/ui";

export function SettingsPage() {
  const { candidate, setCandidate, clear } = useCandidate();
  const navigate = useNavigate();
  const [confirm, setConfirm] = useState("");
  const bias = useMutation({ mutationFn: (v: boolean) => api.setBiasAware(candidate!.id, v), onSuccess: setCandidate });
  const del = useMutation({
    mutationFn: () => api.deleteResume(candidate!.id),
    onSuccess: () => {
      clear();
      navigate("/");
    },
  });

  if (!candidate) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-8">
        <EmptyState title="No resume on file" action={<Link to="/" className="btn-primary">Upload resume</Link>}>
          There is nothing stored about you.
        </EmptyState>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6 px-4 py-8">
      <h1 className="text-2xl font-semibold tracking-tight">Settings and privacy</h1>

      <section className="card p-5" aria-labelledby="bias-h">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 id="bias-h" className="font-semibold">Bias-aware matching</h2>
            <p className="mt-1 text-sm muted">
              Before matching, we hide your name, email, phone, profile links, gendered words and college name, so they
              can't influence your scores. Your skills and experience stay.
            </p>
          </div>
          <label className="flex shrink-0 items-center gap-2 text-sm font-medium">
            <input
              type="checkbox"
              role="switch"
              aria-checked={candidate.bias_aware}
              checked={candidate.bias_aware}
              disabled={bias.isPending}
              onChange={(e) => bias.mutate(e.target.checked)}
            />
            {candidate.bias_aware ? "On" : "Off"}
          </label>
        </div>
        {bias.isPending && <p className="mt-2 text-xs muted">Re-reading your resume</p>}
        {bias.error && <div className="mt-2"><ErrorNote error={bias.error} /></div>}
        {candidate.bias_aware && candidate.masked_text && (
          <details className="mt-4">
            <summary className="cursor-pointer text-sm text-brand-600">See exactly what the matcher reads</summary>
            <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap rounded-md bg-slate-50 p-3 text-xs dark:bg-slate-950">
              {candidate.masked_text}
            </pre>
          </details>
        )}
      </section>

      <section className="card border-rose-200 p-5 dark:border-rose-900" aria-labelledby="del-h">
        <h2 id="del-h" className="font-semibold">Delete my data</h2>
        <p className="mt-1 text-sm muted">
          Permanently deletes your resume text, extracted skills, match results, imported jobs and tracker. This cannot be
          undone.
        </p>
        <label className="label mt-4" htmlFor="confirm-del">
          Type DELETE to confirm
        </label>
        <div className="flex max-w-sm gap-2">
          <input id="confirm-del" className="input" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="off" />
          <button className="btn-danger" disabled={confirm !== "DELETE" || del.isPending} onClick={() => del.mutate()}>
            Delete everything
          </button>
        </div>
        {del.error && <div className="mt-2"><ErrorNote error={del.error} /></div>}
      </section>
    </div>
  );
}
