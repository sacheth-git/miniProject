import { useState, type DragEvent, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Upload } from "lucide-react";
import { rounds, type StageCard } from "../../lib/tpo";
import { Chip, ErrorNote, Spinner } from "../../components/ui";

const LOCKED = new Set(["Offer", "Accepted", "Withdrawn"]); // reached via offers / the student

export function RoundsTab({ id }: { id: string }) {
  const qc = useQueryClient();
  const board = useQuery({ queryKey: ["tpo", "stages", id], queryFn: () => rounds.board(id) });
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [target, setTarget] = useState("");
  const [over, setOver] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [roundName, setRoundName] = useState("");
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["tpo", "stages", id] });
    qc.invalidateQueries({ queryKey: ["tpo", "shortlist", id] });
    qc.invalidateQueries({ queryKey: ["tpo", "drive", id] });
  };
  const move = useMutation({
    mutationFn: (v: { ids: string[]; stage: string }) => rounds.move(id, v.ids, v.stage),
    onSuccess: () => {
      setSel(new Set());
      refresh();
    },
  });
  const results = useMutation({ mutationFn: () => rounds.results(id, roundName, file!), onSuccess: refresh });

  if (board.isLoading) return <Spinner />;
  if (board.error) return <ErrorNote error={board.error} />;
  const { stages, columns } = board.data!;
  const roundStages = stages.filter((s) => !["Applied", "Offer", "Accepted", "Rejected", "Withdrawn"].includes(s));
  const movable = stages.filter((s) => !LOCKED.has(s));
  const toggle = (sid: string) => setSel((s) => { const n = new Set(s); if (n.has(sid)) n.delete(sid); else n.add(sid); return n; });
  const drop = (stage: string) => (e: DragEvent) => {
    e.preventDefault();
    setOver(null);
    const sid = e.dataTransfer.getData("text/plain");
    if (sid && !LOCKED.has(stage)) move.mutate({ ids: [sid], stage });
  };
  const submitResults = (e: FormEvent) => {
    e.preventDefault();
    results.mutate();
  };

  return (
    <div className="space-y-4">
      <div className="card flex flex-wrap items-end gap-4 p-4">
        <div className="flex items-end gap-2">
          <div>
            <label className="label" htmlFor="mv">Move {sel.size} selected to</label>
            <select id="mv" className="input w-auto py-1.5" value={target} onChange={(e) => setTarget(e.target.value)}>
              <option value="">Choose stage</option>
              {movable.map((s) => <option key={s}>{s}</option>)}
            </select>
          </div>
          <button className="btn-primary h-8" disabled={!sel.size || !target || move.isPending} onClick={() => move.mutate({ ids: [...sel], stage: target })}>Move</button>
        </div>
        <form onSubmit={submitResults} className="flex flex-wrap items-end gap-2">
          <div>
            <label className="label" htmlFor="rr">Upload results for round</label>
            <select id="rr" className="input w-auto py-1.5" value={roundName} onChange={(e) => setRoundName(e.target.value)} required>
              <option value="">Choose round</option>
              {roundStages.map((s) => <option key={s}>{s}</option>)}
            </select>
          </div>
          <input type="file" accept=".csv,text/csv" aria-label="Results CSV (roll_no, result)" className="text-sm" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          <button className="btn-secondary h-8" disabled={!file || !roundName || results.isPending}><Upload className="h-4 w-4" aria-hidden /> Apply results</button>
        </form>
        <p className="w-full text-xs muted">
          Results CSV: columns <span className="font-mono">roll_no,result</span> with pass / fail. Passed students move to the next round; the rest are rejected. Students are notified of every move.
        </p>
      </div>
      {move.error && <ErrorNote error={move.error} />}
      {results.error && <ErrorNote error={results.error} />}
      {results.data && (
        <p className="rounded-md bg-emerald-50 px-3 py-2 text-sm dark:bg-emerald-950">
          {results.data.round}: {results.data.passed} passed (to {results.data.next_stage}), {results.data.failed} rejected.
          {results.data.problems.length > 0 && <span className="block text-xs">{results.data.problems.join(" · ")}</span>}
        </p>
      )}
      <div className="grid gap-3 overflow-x-auto pb-3" style={{ gridTemplateColumns: `repeat(${stages.length}, minmax(13rem, 1fr))` }}>
        {stages.map((s) => (
          <section key={s} aria-label={`${s} (${columns[s].length})`}
            onDragOver={(e) => { if (!LOCKED.has(s)) { e.preventDefault(); setOver(s); } }}
            onDragLeave={() => setOver((o) => (o === s ? null : o))} onDrop={drop(s)}
            className={`min-h-48 rounded-lg border bg-slate-50 p-2 dark:bg-slate-900/50 ${over === s ? "border-brand-500" : "border-slate-200 dark:border-slate-800"}`}>
            <h3 className="flex items-center justify-between px-1 pb-2 text-sm font-semibold">
              {s}<span className="rounded-full bg-slate-200 px-2 text-xs dark:bg-slate-700">{columns[s].length}</span>
            </h3>
            <div className="space-y-2">
              {columns[s].map((c) => <Card key={c.student_id} c={c} selected={sel.has(c.student_id)} onToggle={() => toggle(c.student_id)} />)}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}

function Card({ c, selected, onToggle }: { c: StageCard; selected: boolean; onToggle: () => void }) {
  const locked = LOCKED.has(c.stage);
  return (
    <article draggable={!locked} onDragStart={(e) => e.dataTransfer.setData("text/plain", c.student_id)}
      className={`card p-2.5 text-sm ${locked ? "" : "cursor-grab"} ${selected ? "ring-2 ring-brand-500" : ""}`}>
      <label className="flex items-start gap-2">
        <input type="checkbox" className="mt-1" checked={selected} onChange={onToggle} disabled={locked} aria-label={`Select ${c.roll_no}`} />
        <span>
          <span className="font-mono text-xs">{c.roll_no}</span>
          <span className="block">{c.name}</span>
          <span className="text-xs muted">{c.branch} · CGPA {c.cgpa?.toFixed(2) ?? "-"}{c.match_percent != null ? ` · ${c.match_percent}%` : ""}</span>
        </span>
      </label>
    </article>
  );
}

export function OffersTab({ id, defaultCtc }: { id: string; defaultCtc: number | null }) {
  const qc = useQueryClient();
  const offers = useQuery({ queryKey: ["tpo", "offers", id], queryFn: () => rounds.offers(id) });
  const board = useQuery({ queryKey: ["tpo", "stages", id], queryFn: () => rounds.board(id) });
  const [student, setStudent] = useState("");
  const [ctc, setCtc] = useState<string>(defaultCtc ? String(defaultCtc) : "");
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["tpo", "offers", id] });
    qc.invalidateQueries({ queryKey: ["tpo", "stages", id] });
    qc.invalidateQueries({ queryKey: ["tpo", "students"] });
  };
  const create = useMutation({ mutationFn: () => rounds.offer(id, student, ctc ? Number(ctc) : undefined), onSuccess: () => { setStudent(""); refresh(); } });
  const decide = useMutation({ mutationFn: (v: { id: number; status: "accepted" | "declined" }) => rounds.decide(v.id, v.status), onSuccess: refresh });

  const candidates = board.data
    ? board.data.stages.filter((s) => !["Applied", "Offer", "Accepted", "Rejected", "Withdrawn"].includes(s)).flatMap((s) => board.data!.columns[s])
    : [];
  return (
    <div className="space-y-4">
      <form className="card flex flex-wrap items-end gap-3 p-4" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
        <div>
          <label className="label" htmlFor="os">Record an offer for</label>
          <select id="os" className="input w-auto py-1.5" value={student} onChange={(e) => setStudent(e.target.value)} required>
            <option value="">Choose a student still in the process</option>
            {candidates.map((c) => <option key={c.student_id} value={c.student_id}>{c.roll_no} {c.name ?? ""} ({c.stage})</option>)}
          </select>
        </div>
        <div>
          <label className="label" htmlFor="oc">CTC (LPA)</label>
          <input id="oc" type="number" step="0.1" min="0" className="input w-28 py-1.5" value={ctc} onChange={(e) => setCtc(e.target.value)} />
        </div>
        <button className="btn-primary h-8" disabled={!student || create.isPending}>Record offer</button>
        <p className="w-full text-xs muted">Placement policy is checked: a student who has accepted an offer, or holds one and this drive doesn't clear the dream bar, can't receive another.</p>
      </form>
      {create.error && <ErrorNote error={create.error} />}
      {decide.error && <ErrorNote error={decide.error} />}
      <section className="card overflow-hidden">
        <table className="w-full text-sm">
          <caption className="sr-only">Offers</caption>
          <thead className="bg-slate-50 text-left text-xs muted dark:bg-slate-900">
            <tr><th className="px-3 py-2">Roll no.</th><th className="px-3 py-2">Name</th><th className="px-3 py-2 text-right">CTC</th><th className="px-3 py-2">Status</th><th className="px-3 py-2">Recorded</th><th className="px-3 py-2" /></tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {(offers.data ?? []).map((o) => (
              <tr key={o.id}>
                <td className="px-3 py-2 font-mono text-xs">{o.roll_no}</td>
                <td className="px-3 py-2">{o.name}</td>
                <td className="px-3 py-2 text-right tabular-nums">{o.ctc_lpa} LPA</td>
                <td className="px-3 py-2"><Chip tone={o.status === "accepted" ? "green" : o.status === "declined" ? "slate" : "amber"}>{o.status}</Chip></td>
                <td className="px-3 py-2 text-xs muted">{new Date(o.created_at).toLocaleDateString()}</td>
                <td className="px-3 py-2 text-right">
                  {o.status === "pending" && (
                    <span className="flex justify-end gap-1">
                      <button className="btn-ghost h-8 px-2 text-xs" onClick={() => decide.mutate({ id: o.id, status: "accepted" })}>Mark accepted</button>
                      <button className="btn-ghost h-8 px-2 text-xs" onClick={() => decide.mutate({ id: o.id, status: "declined" })}>Mark declined</button>
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {offers.data && offers.data.length === 0 && <p className="p-5 text-center text-sm muted">No offers yet for this drive.</p>}
      </section>
    </div>
  );
}
