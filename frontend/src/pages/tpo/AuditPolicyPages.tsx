import { useEffect, useState } from "react";
import { keepPreviousData, useMutation, useQuery } from "@tanstack/react-query";
import { tpo, type AuditItem, type Policy } from "../../lib/tpo";
import { DataTable, type Column } from "../../components/DataTable";
import { Chip, ErrorNote, PageHeader, PageLoading, Spinner } from "../../components/ui";

const ACTIONS = ["", "shortlist", "drive", "students", "policy"];

function summary(a: AuditItem): string {
  const after = a.after ?? {};
  if (a.action.startsWith("shortlist.") && "student_id" in after) {
    return `${a.before?.["stage"] ?? "-"} → ${after["stage"]}${after["match_percent"] != null ? ` (${after["match_percent"]}% match)` : ""}`;
  }
  if (a.action === "shortlist.export") return `${after["format"]} · ${after["rows"]} rows · ${after["blind"] ? "blind" : "named"}`;
  return Object.keys(after).slice(0, 4).join(", ");
}

export function AuditPage() {
  const [action, setAction] = useState("");
  const [actor, setActor] = useState("");
  const [offset, setOffset] = useState(0);
  const [open, setOpen] = useState<AuditItem | null>(null);
  const limit = 100;
  const q = useQuery({ queryKey: ["tpo", "audit", action, actor, offset], queryFn: () => tpo.audit({ action, actor, limit, offset }), placeholderData: keepPreviousData });
  const cols: Column<AuditItem>[] = [
    { key: "at", header: "When", render: (a) => new Date(a.at).toLocaleString() },
    { key: "actor_email", header: "Who" },
    { key: "action", header: "Action", render: (a) => <Chip tone="blue">{a.action}</Chip> },
    { key: "entity", header: "On", render: (a) => `${a.entity}${a.entity_id ? ` ${a.entity_id.slice(0, 8)}` : ""}` },
    { key: "summary", header: "Change", sortable: false, render: summary },
  ];
  return (
    <div className="page">
      <PageHeader title="Audit log" description="Every shortlist edit, rule change, skill-weight change, import and export, with before and after values" />
      <div className="card flex flex-wrap gap-3 p-4">
        <label className="text-sm">
          <span className="label">Action</span>
          <select className="input w-auto py-1.5" value={action} onChange={(e) => { setAction(e.target.value); setOffset(0); }}>
            {ACTIONS.map((a) => <option key={a} value={a}>{a || "All actions"}</option>)}
          </select>
        </label>
        <label className="text-sm">
          <span className="label">Who (email contains)</span>
          <input className="input py-1.5" value={actor} onChange={(e) => { setActor(e.target.value); setOffset(0); }} />
        </label>
        <span className="ml-auto self-end text-sm muted">{q.data?.total ?? 0} entries</span>
      </div>
      <section className="card overflow-hidden">
        {q.isLoading && <div className="p-5"><Spinner /></div>}
        {q.error && <div className="p-5"><ErrorNote error={q.error} /></div>}
        {q.data && <DataTable caption="Audit log" rows={q.data.items} columns={cols} rowKey={(a) => String(a.id)} pageSize={limit} onRowClick={setOpen} />}
        {q.data && q.data.total > limit && (
          <div className="flex justify-between border-t border-slate-200 px-3 py-2 text-sm dark:border-slate-800">
            <button className="btn-ghost" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - limit))}>Newer</button>
            <button className="btn-ghost" disabled={offset + limit >= q.data.total} onClick={() => setOffset(offset + limit)}>Older</button>
          </div>
        )}
      </section>
      {open && (
        <div className="card p-4" aria-live="polite">
          <div className="flex justify-between"><h2 className="font-semibold">{open.action} #{open.id}</h2><button className="btn-ghost h-8 px-2 text-xs" onClick={() => setOpen(null)}>Close</button></div>
          <div className="mt-2 grid gap-3 md:grid-cols-2">
            <pre className="max-h-64 overflow-auto rounded bg-slate-50 p-2 text-xs dark:bg-slate-950">Before: {JSON.stringify(open.before, null, 2)}</pre>
            <pre className="max-h-64 overflow-auto rounded bg-slate-50 p-2 text-xs dark:bg-slate-950">After: {JSON.stringify(open.after, null, 2)}</pre>
          </div>
        </div>
      )}
    </div>
  );
}

export function PolicyPage() {
  const pol = useQuery({ queryKey: ["tpo", "policy"], queryFn: tpo.policy });
  const [p, setP] = useState<Policy | null>(null);
  useEffect(() => { if (pol.data) setP(pol.data); }, [pol.data]);
  const save = useMutation({ mutationFn: (x: Policy) => tpo.setPolicy(x), onSuccess: () => pol.refetch() });
  if (!p) return <PageLoading />;
  return (
    <div className="page-narrow">
      <h1 className="text-2xl font-semibold">Placement policy</h1>
      <div className="card space-y-5 p-5">
        <label className="flex items-start gap-3">
          <input type="checkbox" className="mt-1" checked={p.one_offer_rule} onChange={(e) => setP({ ...p, one_offer_rule: e.target.checked })} />
          <span><span className="font-medium">One-offer rule</span><span className="block text-sm muted">A student holding an offer can only apply to dream drives that clear the dream bar.</span></span>
        </label>
        <div>
          <label className="font-medium" htmlFor="mult">Dream rule multiplier</label>
          <p className="text-sm muted">A placed student may apply to a dream drive only if its CTC is at least this many times their current offer.</p>
          <input id="mult" type="number" min={1} max={5} step={0.1} className="input mt-2 w-28" value={p.dream_multiplier} onChange={(e) => setP({ ...p, dream_multiplier: Number(e.target.value) })} />
        </div>
        <label className="flex items-start gap-3">
          <input type="checkbox" className="mt-1" checked={p.block_after_accept} onChange={(e) => setP({ ...p, block_after_accept: e.target.checked })} />
          <span><span className="font-medium">Block after accepting an offer</span><span className="block text-sm muted">Students who accept an offer can't apply to further drives.</span></span>
        </label>
        <button className="btn-primary" disabled={save.isPending} onClick={() => save.mutate(p)}>Save policy</button>
        {save.isSuccess && <p className="text-sm text-emerald-700 dark:text-emerald-300">Saved. Eligibility updates immediately.</p>}
        {save.error && <ErrorNote error={save.error} />}
      </div>
    </div>
  );
}
