import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { Download, Info, Pencil, X } from "lucide-react";
import { download, tpo, type EligibilityStudent, type ShortlistRow } from "../../lib/tpo";
import { DataTable, type Column } from "../../components/DataTable";
import { Chip, ErrorNote, PageError, PageHeader, PageLoading, ScoreBar, Spinner } from "../../components/ui";
import { pay, STATUS_TONE, TYPE_LABEL } from "./DrivesPage";
import { OffersTab, RoundsTab } from "./RoundsOffers";
import { ShareLinks } from "./ShareLinks";

const TABS = ["Shortlist", "Rounds", "Offers", "Eligibility", "Export"] as const;
type Tab = (typeof TABS)[number];

export function DriveDetailPage() {
  const { id = "" } = useParams();
  const drive = useQuery({ queryKey: ["tpo", "drive", id], queryFn: () => tpo.drive(id) });
  const [tab, setTab] = useState<Tab>("Shortlist");
  if (drive.isLoading) return <PageLoading />;
  if (drive.error) return <PageError error={drive.error} />;
  const d = drive.data!;
  return (
    <div className="page">
      <PageHeader
        back={{ to: "/tpo/drives", label: "Drives" }}
        title={`${d.company}: ${d.role}`}
        actions={<Link to={`/tpo/drives/${d.id}/edit`} className="btn-secondary"><Pencil className="h-4 w-4" aria-hidden /> Edit drive</Link>}
      >
        <p className="mt-2 flex flex-wrap items-center gap-2 text-sm muted">
          <Chip tone={STATUS_TONE[d.status]}>{d.status}</Chip>
          {d.category === "dream" && <Chip tone="blue">Dream</Chip>}
          <span>{TYPE_LABEL[d.job_type]}</span>·<span>{pay(d)}</span>·<span>{d.location ?? "Location TBD"}</span>
          {d.deadline && <>·<span>Apply by {new Date(d.deadline).toLocaleDateString()}</span></>}
        </p>
        <p className="mt-1 text-sm muted">Rounds: {d.rounds.join(" → ") || "-"}</p>
      </PageHeader>
      <div role="tablist" className="flex gap-1 border-b border-slate-200 dark:border-slate-800">
        {TABS.map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium ${tab === t ? "border-brand-600 text-brand-700 dark:text-brand-200" : "border-transparent muted hover:text-slate-900 dark:hover:text-white"}`}>
            {t}
          </button>
        ))}
      </div>
      {tab === "Shortlist" && <ShortlistTab id={d.id} />}
      {tab === "Rounds" && <RoundsTab id={d.id} />}
      {tab === "Offers" && <OffersTab id={d.id} defaultCtc={d.ctc_lpa} />}
      {tab === "Eligibility" && <EligibilityTab id={d.id} />}
      {tab === "Export" && (
        <div className="space-y-5">
          <ExportTab id={d.id} />
          <ShareLinks driveId={d.id} />
        </div>
      )}
    </div>
  );
}

function ShortlistTab({ id }: { id: string }) {
  const qc = useQueryClient();
  const [blind, setBlind] = useState(true);
  const [n, setN] = useState(10);
  const [threshold, setThreshold] = useState(60);
  const [replace, setReplace] = useState(false);
  const [q, setQ] = useState("");
  const [why, setWhy] = useState<string | null>(null);
  const key = ["tpo", "shortlist", id, blind];
  const sl = useQuery({ queryKey: key, queryFn: () => tpo.shortlist(id, blind) });
  const select = useMutation({
    mutationFn: (body: Parameters<typeof tpo.select>[1]) => tpo.select(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tpo", "shortlist", id] });
      qc.invalidateQueries({ queryKey: ["tpo", "drive", id] });
    },
  });

  const cols: Column<ShortlistRow>[] = useMemo(() => [
    {
      key: "shortlisted", header: "Shortlist", sortValue: (r) => (r.shortlisted ? 1 : 0),
      render: (r) => (
        <input type="checkbox" aria-label={`Shortlist ${r.roll_no}`} checked={r.shortlisted} disabled={select.isPending || !!r.stage && !["Shortlisted", "Applied", "Eligible"].includes(r.stage)}
          onClick={(e) => e.stopPropagation()}
          onChange={() => select.mutate({ mode: "manual", add: r.shortlisted ? [] : [r.user_id], remove: r.shortlisted ? [r.user_id] : [] })} />
      ),
    },
    { key: "rank", header: "Rank", align: "right", render: (r) => r.rank ?? <span className="muted">-</span> },
    { key: "roll_no", header: "Roll no.", render: (r) => <span className="font-mono text-xs">{r.roll_no}</span> },
    ...(blind ? [] : [{ key: "name", header: "Name" } as Column<ShortlistRow>]),
    { key: "branch", header: "Branch" },
    { key: "cgpa", header: "CGPA", align: "right", render: (r) => r.cgpa?.toFixed(2) ?? "-" },
    { key: "match_percent", header: "Match", align: "right", render: (r) => (r.match_percent === null ? <span className="muted">No resume</span> : `${r.match_percent}%`) },
    { key: "matched_skills", header: "Top matched skills", sortable: false, render: (r) => <span className="flex flex-wrap gap-1">{r.matched_skills.map((s) => <Chip key={s} tone="green">{s}</Chip>)}</span> },
    { key: "missing_required", header: "Missing required", sortable: false, render: (r) => <span className="flex flex-wrap gap-1">{r.missing_required.slice(0, 3).map((s) => <Chip key={s} tone="red">{s}</Chip>)}{r.missing_required.length > 3 && <span className="text-xs muted">+{r.missing_required.length - 3}</span>}</span> },
    { key: "placed_status", header: "Placed", render: (r) => (r.placed_status === "unplaced" ? "-" : r.placed_status === "placed" ? "Placed" : "Has offer") },
    { key: "stage", header: "Stage", render: (r) => r.stage ?? (r.applied ? "Applied" : "-") },
    { key: "why", header: "", sortable: false, render: (r) => <button className="btn-ghost h-8 px-2 text-xs" onClick={(e) => { e.stopPropagation(); setWhy(r.user_id); }} disabled={r.rank === null}><Info className="h-3.5 w-3.5" aria-hidden /> Why</button> },
  ], [blind, select]);

  return (
    <div className="space-y-4">
      <p className="flex gap-2 rounded-md border border-brand-200 bg-brand-50 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900">
        <Info className="mt-0.5 h-4 w-4 shrink-0 text-brand-600" aria-hidden />
        {sl.data?.note ?? "HireX recommends; the placement officer makes every shortlist decision."}
      </p>
      <div className="card flex flex-wrap items-end gap-4 p-4">
        <label className="flex items-center gap-2 text-sm font-medium">
          <input type="checkbox" role="switch" aria-checked={blind} checked={blind} onChange={(e) => setBlind(e.target.checked)} />
          Blind review (hide names)
        </label>
        <div className="flex items-end gap-2">
          <div><label className="label" htmlFor="topn">Top N</label><input id="topn" type="number" min={1} className="input w-20 py-1.5" value={n} onChange={(e) => setN(Number(e.target.value))} /></div>
          <button className="btn-secondary h-8" onClick={() => select.mutate({ mode: "top", n, replace })} disabled={select.isPending}>Shortlist top {n}</button>
        </div>
        <div className="flex items-end gap-2">
          <div><label className="label" htmlFor="thr">Match at least</label><input id="thr" type="number" min={0} max={100} className="input w-20 py-1.5" value={threshold} onChange={(e) => setThreshold(Number(e.target.value))} /></div>
          <button className="btn-secondary h-8" onClick={() => select.mutate({ mode: "threshold", min_score: threshold, replace })} disabled={select.isPending}>Shortlist {threshold}%+</button>
        </div>
        <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={replace} onChange={(e) => setReplace(e.target.checked)} /> Replace current shortlist</label>
        <span className="ml-auto text-sm"><b>{sl.data?.shortlisted ?? 0}</b> shortlisted</span>
      </div>
      {select.error && <ErrorNote error={select.error} />}
      <section className="card overflow-hidden">
        <header className="flex items-center justify-between border-b border-slate-200 px-4 py-2 dark:border-slate-800">
          <h2 className="text-sm font-semibold">Eligible students, ranked by match</h2>
          <input aria-label="Filter shortlist" className="input w-56 py-1" placeholder="Filter by roll no., branch, skill" value={q} onChange={(e) => setQ(e.target.value)} />
        </header>
        {sl.isLoading && <div className="p-5"><Spinner label="Ranking students" /></div>}
        {sl.error && <div className="p-5"><ErrorNote error={sl.error} /></div>}
        {sl.data && (
          <DataTable caption="Ranked shortlist" rows={sl.data.rows} columns={cols} rowKey={(r) => r.user_id} pageSize={30}
            filter={q} filterText={(r) => `${r.roll_no} ${r.branch} ${r.name ?? ""} ${r.matched_skills.join(" ")} ${r.missing_required.join(" ")}`}
            rowClassName={(r) => (r.shortlisted ? "bg-emerald-50/60 dark:bg-emerald-950/30" : "")} onRowClick={(r) => r.rank !== null && setWhy(r.user_id)}
            empty="No eligible students for this drive. Check the Eligibility tab." />
        )}
      </section>
      {why && <WhyDrawer driveId={id} uid={why} blind={blind} onClose={() => setWhy(null)} />}
    </div>
  );
}

function WhyDrawer({ driveId, uid, blind, onClose }: { driveId: string; uid: string; blind: boolean; onClose: () => void }) {
  const ex = useQuery({ queryKey: ["tpo", "explain", driveId, uid, blind], queryFn: () => tpo.explain(driveId, uid, blind) });
  const e = ex.data?.explanation;
  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-slate-900/30" onClick={onClose} role="presentation">
      <aside className="h-full w-full max-w-lg overflow-y-auto bg-white p-5 shadow-xl dark:bg-slate-900" role="dialog" aria-modal="true" aria-label="Why ranked here" onClick={(ev) => ev.stopPropagation()}>
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-lg font-semibold">Why ranked here</h2>
            {ex.data && <p className="text-sm muted">{ex.data.roll_no}{ex.data.name ? ` · ${ex.data.name}` : ""} · rank {ex.data.rank ?? "-"}</p>}
          </div>
          <button className="btn-ghost h-8 w-8 p-0" onClick={onClose} aria-label="Close"><X className="h-5 w-5" /></button>
        </div>
        {ex.isLoading && <Spinner />}
        {ex.error && <ErrorNote error={ex.error} />}
        {e && (
          <div className="mt-4 space-y-4">
            <p className="text-sm">{e.summary}</p>
            <div className="space-y-2">
              <ScoreBar label="Overall match" value={e.score} />
              <ScoreBar label="Skills (weighted by this drive)" value={e.skill} />
              <ScoreBar label="Relevance of projects and experience" value={e.sem} />
              <ScoreBar label="Fit (experience level, type, location, education)" value={e.context} />
            </div>
            {[["Matched", e.matched, "green"], ["Missing required", e.missing_required, "red"], ["Missing preferred", e.missing_preferred, "slate"]].map(([title, list, tone]) =>
              (list as typeof e.matched).length ? (
                <div key={title as string}>
                  <h3 className="text-sm font-semibold">{title as string}</h3>
                  <ul className="mt-1 space-y-1.5">
                    {(list as typeof e.matched).map((m) => (
                      <li key={m.skill_id} className="text-sm">
                        <Chip tone={tone as "green" | "red" | "slate"}>{m.name}</Chip> <span className="text-xs muted">weight {m.weight.toFixed(2)}</span>
                        {m.resume_evidence && <p className="mt-0.5 text-xs muted">Resume: {m.resume_evidence}</p>}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null,
            )}
            <p className="text-xs muted">Name, gender, photo and college are never used in this score.</p>
          </div>
        )}
      </aside>
    </div>
  );
}

function EligibilityTab({ id }: { id: string }) {
  const el = useQuery({ queryKey: ["tpo", "eligibility", id], queryFn: () => tpo.eligibility(id) });
  const [show, setShow] = useState<"all" | "eligible" | "ineligible">("ineligible");
  const [q, setQ] = useState("");
  if (el.isLoading) return <Spinner />;
  if (el.error) return <ErrorNote error={el.error} />;
  const data = el.data!;
  const rows = data.students.filter((s) => show === "all" || (show === "eligible") === s.eligible);
  const cols: Column<EligibilityStudent>[] = [
    { key: "roll_no", header: "Roll no.", render: (s) => <span className="font-mono text-xs">{s.roll_no}</span> },
    { key: "name", header: "Name" },
    { key: "branch", header: "Branch" },
    { key: "batch_year", header: "Batch", align: "right" },
    { key: "cgpa", header: "CGPA", align: "right", render: (s) => s.cgpa?.toFixed(2) ?? "-" },
    { key: "eligible", header: "Eligible", sortValue: (s) => (s.eligible ? 1 : 0), render: (s) => (s.eligible ? <Chip tone="green">Yes</Chip> : <Chip tone="red">No</Chip>) },
    { key: "reasons", header: "Reasons", sortable: false, render: (s) => <ul className="text-xs">{s.reasons.map((r) => <li key={r}>{r}</li>)}</ul> },
  ];
  return (
    <div className="space-y-4">
      <div className="card p-4">
        <p className="text-sm"><b>{data.eligible}</b> of {data.total} students are eligible.</p>
        <div className="mt-2 flex flex-wrap gap-2">
          {Object.entries(data.reason_counts).map(([k, v]) => <Chip key={k} tone="amber">{k}: {v}</Chip>)}
        </div>
      </div>
      <section className="card overflow-hidden">
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 px-4 py-2 dark:border-slate-800">
          <div role="radiogroup" aria-label="Show" className="flex gap-1 text-sm">
            {(["ineligible", "eligible", "all"] as const).map((v) => (
              <button key={v} role="radio" aria-checked={show === v} onClick={() => setShow(v)} className={`rounded px-2 py-1 ${show === v ? "bg-slate-200 font-medium dark:bg-slate-700" : "muted"}`}>
                {v[0].toUpperCase() + v.slice(1)}
              </button>
            ))}
          </div>
          <input aria-label="Filter students" className="input w-56 py-1" placeholder="Filter" value={q} onChange={(e) => setQ(e.target.value)} />
        </header>
        <DataTable caption="Eligibility" rows={rows} columns={cols} rowKey={(s) => s.user_id} filter={q}
          filterText={(s) => `${s.roll_no} ${s.name} ${s.branch} ${s.reasons.join(" ")}`} />
      </section>
    </div>
  );
}

const EXPORT_COLS: [string, string][] = [
  ["rank", "Rank"], ["roll_no", "Roll no."], ["name", "Name"], ["email", "Email"], ["branch", "Branch"],
  ["batch_year", "Batch"], ["cgpa", "CGPA"], ["match_percent", "Match %"], ["matched_skills", "Top matched skills"],
  ["missing_required", "Missing required"], ["placed_status", "Placed status"], ["stage", "Stage"],
];

function ExportTab({ id }: { id: string }) {
  const [cols, setCols] = useState(["rank", "roll_no", "name", "branch", "cgpa", "match_percent", "matched_skills", "missing_required"]);
  const [blind, setBlind] = useState(false);
  const [scope, setScope] = useState<"shortlisted" | "ranked">("shortlisted");
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const go = async (format: string) => {
    setErr(null);
    setBusy(format);
    const qs = new URLSearchParams({ format, blind: String(blind), scope, columns: cols.join(",") });
    try {
      await download(`/tpo/drives/${id}/shortlist/export?${qs}`, `shortlist.${format}`);
    } catch (e) {
      setErr(e);
    } finally {
      setBusy(null);
    }
  };
  return (
    <div className="card space-y-4 p-5">
      <fieldset>
        <legend className="label">Columns</legend>
        <div className="flex flex-wrap gap-3 text-sm">
          {EXPORT_COLS.map(([k, label]) => (
            <label key={k} className="flex items-center gap-1.5">
              <input type="checkbox" checked={cols.includes(k)} onChange={() => setCols((c) => (c.includes(k) ? c.filter((x) => x !== k) : [...c, k]))} />
              {label}
            </label>
          ))}
        </div>
      </fieldset>
      <div className="flex flex-wrap gap-4 text-sm">
        <label className="flex items-center gap-2"><input type="checkbox" checked={blind} onChange={(e) => setBlind(e.target.checked)} /> Blind (drop name and email)</label>
        <label className="flex items-center gap-2">
          Students:
          <select className="input w-auto py-1" value={scope} onChange={(e) => setScope(e.target.value as typeof scope)}>
            <option value="shortlisted">Shortlisted only</option><option value="ranked">All eligible, ranked</option>
          </select>
        </label>
      </div>
      <div className="flex flex-wrap gap-2">
        {[["xlsx", "Excel"], ["csv", "CSV"], ["pdf", "PDF summary"], ["zip", "Resumes (ZIP)"]].map(([f, label]) => (
          <button key={f} className="btn-secondary" disabled={!!busy} onClick={() => go(f)}>
            <Download className="h-4 w-4" aria-hidden /> {busy === f ? "Preparing" : label}
          </button>
        ))}
      </div>
      <p className="text-xs muted">Every export is recorded in the audit log.</p>
      {err !== null && <ErrorNote error={err} />}
    </div>
  );
}
