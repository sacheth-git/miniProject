import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { isSeeker, useAuth } from "../lib/auth";
import { useCandidate } from "../lib/candidate";
import { setTokens } from "../lib/session";
import { Chip, ErrorNote } from "../components/ui";

export function SettingsPage() {
  const { user } = useAuth();
  const { candidate } = useCandidate();
  return (
    <div className="mx-auto max-w-3xl space-y-6 px-4 py-8">
      <h1 className="text-2xl font-semibold tracking-tight">Settings and privacy</h1>
      {isSeeker(user) && candidate && <BiasSection />}
      {isSeeker(user) && !candidate && (
        <p className="card p-5 text-sm">
          No resume on file. <Link to="/" className="text-brand-600 hover:underline">Upload one</Link> to start matching.
        </p>
      )}
      {isSeeker(user) && <CampusSection />}
      <AccountSection />
    </div>
  );
}

function BiasSection() {
  const { candidate, setCandidate } = useCandidate();
  const bias = useMutation({ mutationFn: (v: boolean) => api.setBiasAware(candidate!.id, v), onSuccess: setCandidate });
  if (!candidate) return null;
  return (
    <section className="card p-5" aria-labelledby="bias-h">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 id="bias-h" className="font-semibold">Bias-aware matching</h2>
          <p className="mt-1 text-sm muted">
            Before matching, we hide your name, email, phone, profile links, gendered words and college name, so they can't
            influence your scores. Your skills and experience stay.
          </p>
        </div>
        <label className="flex shrink-0 items-center gap-2 text-sm font-medium">
          <input type="checkbox" role="switch" aria-checked={candidate.bias_aware} checked={candidate.bias_aware} disabled={bias.isPending} onChange={(e) => bias.mutate(e.target.checked)} />
          {candidate.bias_aware ? "On" : "Off"}
        </label>
      </div>
      {bias.isPending && <p className="mt-2 text-xs muted">Re-reading your resume</p>}
      {bias.error && <div className="mt-2"><ErrorNote error={bias.error} /></div>}
      {candidate.bias_aware && candidate.masked_text && (
        <details className="mt-4">
          <summary className="cursor-pointer text-sm text-brand-600">See exactly what the matcher reads</summary>
          <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap rounded-md bg-slate-50 p-3 text-xs dark:bg-slate-950">{candidate.masked_text}</pre>
        </details>
      )}
    </section>
  );
}

function CampusSection() {
  const { user, refreshUser } = useAuth();
  const qc = useQueryClient();
  const isStudent = user?.role === "student";
  const consent = useQuery({ queryKey: ["consent"], queryFn: api.consent, enabled: isStudent });
  const [code, setCode] = useState("");
  const [agree, setAgree] = useState(false);
  const after = () => {
    qc.invalidateQueries({ queryKey: ["consent"] });
    refreshUser();
  };
  const join = useMutation({ mutationFn: () => api.joinInstitution(code, agree), onSuccess: after });
  const withdraw = useMutation({ mutationFn: api.withdrawConsent, onSuccess: after });
  const give = useMutation({ mutationFn: api.giveConsent, onSuccess: after });

  if (!isStudent) {
    const submit = (e: FormEvent) => {
      e.preventDefault();
      join.mutate();
    };
    return (
      <section className="card p-5" aria-labelledby="campus-h">
        <h2 id="campus-h" className="font-semibold">Join your college</h2>
        <p className="mt-1 text-sm muted">Got an invite code from your placement office? Join to see campus drives too.</p>
        <form onSubmit={submit} className="mt-3 space-y-3">
          <input aria-label="Invite code" className="input max-w-xs uppercase" placeholder="Invite code" value={code} onChange={(e) => setCode(e.target.value)} required />
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-1" checked={agree} onChange={(e) => setAgree(e.target.checked)} />
            I agree to share my profile, resume, academic details and campus applications with my placement office.
          </label>
          <button className="btn-primary" disabled={!agree || join.isPending}>Join</button>
          {join.error && <ErrorNote error={join.error} />}
        </form>
      </section>
    );
  }

  const c = consent.data;
  return (
    <section className="card p-5" aria-labelledby="campus-h">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 id="campus-h" className="font-semibold">Sharing with {c?.institution_name ?? "your placement office"}</h2>
          <p className="mt-1 text-sm muted">
            {c?.consent ? "Your placement office can see:" : "Your placement office can't see your resume, and you're left out of campus shortlists."}
          </p>
        </div>
        {c && (c.consent ? <Chip tone="green">Sharing on</Chip> : <Chip tone="amber">Sharing off</Chip>)}
      </div>
      {c?.consent && (
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
          {c.tpo_can_see.map((s) => <li key={s}>{s}</li>)}
        </ul>
      )}
      <p className="mt-3 text-xs muted">Your match scores are never shown to other students, and peer ranks are never shown to you.</p>
      <div className="mt-4">
        {c?.consent ? (
          <button className="btn-danger" onClick={() => withdraw.mutate()} disabled={withdraw.isPending}>Withdraw consent</button>
        ) : (
          <button className="btn-primary" onClick={() => give.mutate()} disabled={give.isPending}>Share again</button>
        )}
      </div>
      {(withdraw.error || give.error) && <div className="mt-2"><ErrorNote error={withdraw.error ?? give.error} /></div>}
    </section>
  );
}

function AccountSection() {
  const { user } = useAuth();
  const { candidate, clear } = useCandidate();
  const navigate = useNavigate();
  const [confirm, setConfirm] = useState("");
  const delResume = useMutation({ mutationFn: () => api.deleteResume(candidate!.id), onSuccess: () => { clear(); navigate("/"); } });
  const delAccount = useMutation({
    mutationFn: api.deleteAccount,
    onSuccess: () => {
      setTokens(null);
      navigate("/", { replace: true });
    },
  });
  return (
    <section className="card border-rose-200 p-5 dark:border-rose-900" aria-labelledby="del-h">
      <h2 id="del-h" className="font-semibold">Delete my data</h2>
      <p className="mt-1 text-sm muted">Signed in as {user?.email}. Deleting cannot be undone.</p>
      {candidate && (
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <button className="btn-secondary" onClick={() => delResume.mutate()} disabled={delResume.isPending}>Delete my resume only</button>
          <span className="text-xs muted">Removes resume text, skills, matches, imports and tracker for it.</span>
        </div>
      )}
      <label className="label mt-5" htmlFor="confirm-del">Type DELETE to remove your whole account</label>
      <div className="flex max-w-sm gap-2">
        <input id="confirm-del" className="input" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="off" />
        <button className="btn-danger" disabled={confirm !== "DELETE" || delAccount.isPending} onClick={() => delAccount.mutate()}>Delete account</button>
      </div>
      {(delResume.error || delAccount.error) && <div className="mt-2"><ErrorNote error={delResume.error ?? delAccount.error} /></div>}
    </section>
  );
}
