import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { Check, CircleAlert, Clock, MapPin } from "lucide-react";
import { campus, type CampusDrive, type CampusDriveDetail } from "../lib/tpo";
import { Chip, EmptyState, ErrorNote, MatchRing, PageError, PageHeader, PageLoading, ScoreBar } from "../components/ui";

const TYPE: Record<string, string> = { fte: "Full-time", internship: "Internship", "intern+ppo": "Internship + PPO" };

function pay(d: CampusDrive): string {
  const parts = [];
  if (d.ctc_lpa) parts.push(`${d.ctc_lpa} LPA`);
  if (d.stipend_month) parts.push(`Rs ${d.stipend_month.toLocaleString("en-IN")}/month`);
  return parts.join(" · ") || "Pay not listed";
}

function deadlineText(d: CampusDrive): string {
  if (!d.deadline) return "No deadline";
  const dt = new Date(d.deadline);
  if (d.deadline_passed) return `Closed ${dt.toLocaleDateString()}`;
  const hours = (dt.getTime() - Date.now()) / 3_600_000;
  return hours < 48 ? `Closes in ${Math.max(1, Math.round(hours))} h` : `Apply by ${dt.toLocaleDateString()}`;
}

export function CampusDrivesPage() {
  const q = useQuery({ queryKey: ["campus", "drives"], queryFn: campus.drives });
  if (q.isLoading) return <PageLoading label="Loading campus drives" />;
  if (q.error) return <PageError error={q.error} />;
  const eligible = q.data!.filter((d) => d.eligible);
  const other = q.data!.filter((d) => !d.eligible);
  return (
    <div className="page-mid">
      <div>
        <h1 className="text-2xl font-semibold">Campus drives</h1>
        <p className="mt-1 text-sm muted">Drives from your placement office. Your match score is visible only to you and your placement office.</p>
      </div>
      {q.data!.length === 0 && <EmptyState title="No open drives right now">You'll get a notification when a drive you're eligible for opens.</EmptyState>}
      {eligible.length > 0 && (
        <section aria-labelledby="elig-h" className="space-y-3">
          <h2 id="elig-h" className="font-semibold">You're eligible ({eligible.length})</h2>
          {eligible.map((d) => <DriveCard key={d.id} d={d} />)}
        </section>
      )}
      {other.length > 0 && (
        <section aria-labelledby="inel-h" className="space-y-3">
          <h2 id="inel-h" className="font-semibold">Not eligible ({other.length})</h2>
          {other.map((d) => <DriveCard key={d.id} d={d} />)}
        </section>
      )}
    </div>
  );
}

function DriveCard({ d }: { d: CampusDrive }) {
  return (
    <article className={`card flex gap-4 p-4 ${d.eligible ? "" : "opacity-80"}`}>
      <div className="min-w-0 flex-1">
        <h3 className="font-semibold">
          <Link to={`/campus/${d.id}`} className="hover:link">{d.role}</Link>
        </h3>
        <p className="text-sm">{d.company}</p>
        <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs muted">
          <span>{TYPE[d.job_type]}</span><span>{pay(d)}</span>
          {d.location && <span className="inline-flex items-center gap-1"><MapPin className="h-3.5 w-3.5" aria-hidden />{d.location}</span>}
          <span className="inline-flex items-center gap-1"><Clock className="h-3.5 w-3.5" aria-hidden />{deadlineText(d)}</span>
          {d.category === "dream" && <Chip tone="blue">Dream</Chip>}
        </p>
        {d.eligible ? (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {d.matched_skills.slice(0, 3).map((s) => <Chip key={s} tone="green">{s}</Chip>)}
            {d.missing_required.slice(0, 3).map((s) => <Chip key={s} tone="red">{s}</Chip>)}
          </div>
        ) : (
          <ul className="mt-2 space-y-0.5 text-xs text-rose-700 dark:text-rose-300">
            {d.reasons.map((r) => <li key={r} className="flex gap-1"><CircleAlert className="h-3.5 w-3.5 shrink-0" aria-hidden />{r}</li>)}
          </ul>
        )}
      </div>
      <div className="flex flex-col items-end justify-between gap-2">
        {d.match_percent !== null && <MatchRing percent={d.match_percent} />}
        {d.offer ? <Chip tone="green">Offer {d.offer.status}</Chip> : d.stage ? <Chip tone="blue">{d.stage}</Chip> : null}
      </div>
    </article>
  );
}

export function CampusDrivePage() {
  const { id = "" } = useParams();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["campus", "drive", id], queryFn: () => campus.drive(id) });
  const done = (d: CampusDriveDetail) => {
    qc.setQueryData(["campus", "drive", id], d);
    qc.invalidateQueries({ queryKey: ["campus", "drives"] });
    qc.invalidateQueries({ queryKey: ["tracker"] });
    qc.invalidateQueries({ queryKey: ["notifications"] });
  };
  const apply = useMutation({ mutationFn: () => campus.apply(id), onSuccess: done });
  const withdraw = useMutation({ mutationFn: () => campus.withdraw(id), onSuccess: done });
  const decide = useMutation({ mutationFn: (v: "accept" | "decline") => campus.decide(q.data!.offer!.id, v), onSuccess: done });

  if (q.isLoading) return <PageLoading />;
  if (q.error) return <PageError error={q.error} />;
  const d = q.data!;
  const reached = new Set(d.timeline.map((t) => t.stage));
  const canWithdraw = d.applied && !d.deadline_passed && ["Applied", "Shortlisted"].includes(d.stage ?? "");
  const canApply = d.eligible && d.status === "open" && !d.deadline_passed && !d.applied && !d.offer && d.stage !== "Rejected";
  const e = d.explanation;

  return (
    <div className="page-mid">
      <PageHeader
        back={{ to: "/campus", label: "Campus drives" }}
        eyebrow={d.company}
        title={d.role}
        description={`${TYPE[d.job_type]} · ${pay(d)} · ${d.location ?? "Location TBD"} · ${deadlineText(d)}`}
        actions={d.match_percent !== null ? <MatchRing percent={d.match_percent} size={64} /> : undefined}
      />

      {d.offer && d.offer.status === "pending" && (
        <section className="card border-emerald-300 p-5 dark:border-emerald-800" aria-labelledby="offer-h">
          <h2 id="offer-h" className="text-lg font-semibold">You have an offer: {d.offer.ctc_lpa} LPA</h2>
          <p className="mt-1 text-sm muted">Accepting ends your other campus applications under your college's placement policy.</p>
          <div className="mt-3 flex gap-2">
            <button className="btn-primary" disabled={decide.isPending} onClick={() => decide.mutate("accept")}>Accept offer</button>
            <button className="btn-secondary" disabled={decide.isPending} onClick={() => decide.mutate("decline")}>Decline</button>
          </div>
          {decide.error && <div className="mt-2"><ErrorNote error={decide.error} /></div>}
        </section>
      )}
      {d.offer && d.offer.status !== "pending" && <Chip tone={d.offer.status === "accepted" ? "green" : "slate"}>Offer {d.offer.status}</Chip>}

      {!d.eligible && (
        <section className="card border-rose-200 p-4 dark:border-rose-900">
          <h2 className="text-sm font-semibold">Why you can't apply</h2>
          <ul className="mt-1 list-disc pl-5 text-sm">{d.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
        </section>
      )}

      <div className="flex flex-wrap gap-2">
        {canApply && <button className="btn-primary" disabled={apply.isPending} onClick={() => apply.mutate()}>{apply.isPending ? "Applying" : "Apply to this drive"}</button>}
        {canWithdraw && <button className="btn-secondary" disabled={withdraw.isPending} onClick={() => withdraw.mutate()}>Withdraw application</button>}
      </div>
      {(apply.error || withdraw.error) && <ErrorNote error={apply.error ?? withdraw.error} />}

      {(d.timeline.length > 0 || d.applied) && (
        <section className="card p-5" aria-labelledby="tl-h">
          <h2 id="tl-h" className="font-semibold">Your progress</h2>
          <ol className="mt-4 flex flex-wrap items-center gap-2 text-sm">
            {d.stages.map((s, i) => {
              const done = reached.has(s);
              const current = d.stage === s;
              return (
                <li key={s} className="flex items-center gap-2">
                  <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 ${current ? "bg-brand-600 text-white" : done ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200" : "bg-slate-100 muted dark:bg-slate-800"}`} aria-current={current ? "step" : undefined}>
                    {done && !current && <Check className="h-3.5 w-3.5" aria-hidden />}{s}
                  </span>
                  {i < d.stages.length - 1 && <span className="muted" aria-hidden>→</span>}
                </li>
              );
            })}
          </ol>
          {(d.stage === "Rejected" || d.stage === "Withdrawn") && <p className="mt-3 text-sm">Status: <b>{d.stage}</b></p>}
          <ul className="mt-4 space-y-1 text-xs muted">
            {d.timeline.map((t, i) => <li key={i}>{new Date(t.at).toLocaleString()}: {t.stage}{t.note ? ` (${t.note})` : ""}</li>)}
          </ul>
        </section>
      )}

      {e && (
        <section className="card p-5" aria-labelledby="fit-h">
          <h2 id="fit-h" className="font-semibold">How you match</h2>
          <p className="mt-1 text-sm">{e.summary}</p>
          <div className="mt-3 grid gap-3 sm:grid-cols-3">
            <ScoreBar label="Skills" value={e.skill} /><ScoreBar label="Relevance" value={e.sem} /><ScoreBar label="Fit" value={e.context} />
          </div>
          {d.missing_required.length > 0 && (
            <p className="mt-3 text-sm">Skills this drive requires that your resume doesn't show: {d.missing_required.map((s) => <Chip key={s} tone="red">{s}</Chip>)}</p>
          )}
        </section>
      )}

      <section className="card p-5">
        <h2 className="font-semibold">Job description</h2>
        <div className="mt-2 whitespace-pre-line text-sm text-slate-700 dark:text-slate-300">{d.jd_text || "Not provided."}</div>
        <p className="mt-3 text-xs muted">Rounds: {d.rounds.join(" → ") || "-"}</p>
      </section>
    </div>
  );
}

export function ReadinessPage() {
  const q = useQuery({ queryKey: ["campus", "readiness"], queryFn: campus.readiness });
  if (q.isLoading) return <PageLoading label="Checking your readiness" />;
  if (q.error) return <PageError error={q.error} />;
  const r = q.data!;
  const pct = Math.round(r.score * 100);
  return (
    <div className="page-mid">
      <h1 className="text-2xl font-semibold">Placement readiness</h1>
      <div className="card flex flex-wrap items-center gap-6 p-6">
        <MatchRing percent={pct} size={96} />
        <div className="min-w-60 flex-1 space-y-2">
          <ScoreBar label={`Match with open drives${r.drives_considered ? ` (${r.drives_considered})` : ""}`} value={r.match ?? 0} hint="Average of your best 5 eligible drives" />
          <ScoreBar label="Profile completeness" value={r.completeness} />
          <ScoreBar label="Resume ATS-friendliness" value={r.ats} />
          {r.match === null && <p className="text-xs muted">No open drives you're eligible for right now, so the score uses profile and resume only.</p>}
        </div>
      </div>
      <section className="card p-5" aria-labelledby="act-h">
        <h2 id="act-h" className="font-semibold">Top 3 things to do next</h2>
        <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm">{r.actions.map((a) => <li key={a.text}>{a.text}</li>)}</ol>
        {r.actions.length === 0 && <p className="mt-2 text-sm muted">Nothing urgent. Keep your resume current.</p>}
      </section>
      <div className="grid gap-4 md:grid-cols-2">
        {(["profile", "resume"] as const).map((k) => (
          <section key={k} className="card p-5">
            <h2 className="font-semibold">{k === "profile" ? "Profile checklist" : "Resume checklist"}</h2>
            <ul className="mt-3 space-y-1.5 text-sm">
              {r.checks[k].map((c) => (
                <li key={c.label} className="flex gap-2">
                  {c.ok ? <Check className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" aria-hidden /> : <CircleAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" aria-hidden />}
                  <span>{c.label}{!c.ok && <span className="block text-xs muted">{c.fix}</span>}</span>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
}
