import { useState, type DragEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ExternalLink, Trash2 } from "lucide-react";
import { api } from "../lib/api";
import { useCandidate } from "../lib/candidate";
import { timeAgo } from "../lib/format";
import { APP_STATUSES, type Application, type AppStatus } from "../lib/types";
import { EmptyState, ErrorNote, Spinner } from "../components/ui";

const COLUMN_HINT: Record<AppStatus, string> = {
  Saved: "Jobs you bookmarked",
  Ready: "Opened, not yet submitted",
  Applied: "Application sent",
  Interview: "In the interview process",
  Offer: "Offer received",
  Rejected: "Closed",
};

export function TrackerPage() {
  const { candidateId } = useCandidate();
  const qc = useQueryClient();
  const key = ["applications", candidateId];
  const apps = useQuery({ queryKey: key, queryFn: () => api.applications(candidateId!), enabled: !!candidateId });
  const [dragId, setDragId] = useState<number | null>(null);
  const [over, setOver] = useState<AppStatus | null>(null);

  const move = useMutation({
    mutationFn: (v: { id: number; status?: AppStatus; notes?: string }) => api.updateApplication(v.id, { status: v.status, notes: v.notes }),
    onMutate: async (v) => {
      await qc.cancelQueries({ queryKey: key });
      const prev = qc.getQueryData<Application[]>(key);
      qc.setQueryData<Application[]>(key, (old) => old?.map((a) => (a.id === v.id ? { ...a, ...(v.status ? { status: v.status } : {}), ...(v.notes !== undefined ? { notes: v.notes } : {}) } : a)));
      return { prev };
    },
    onError: (_e, _v, ctx) => ctx?.prev && qc.setQueryData(key, ctx.prev),
    onSettled: () => qc.invalidateQueries({ queryKey: key }),
  });
  const remove = useMutation({
    mutationFn: (id: number) => api.deleteApplication(id),
    onSettled: () => qc.invalidateQueries({ queryKey: key }),
  });

  if (!candidateId) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-8">
        <EmptyState title="Upload your resume to start tracking" action={<Link to="/" className="btn-primary">Upload resume</Link>} />
      </div>
    );
  }

  const onDrop = (status: AppStatus) => (e: DragEvent) => {
    e.preventDefault();
    setOver(null);
    const id = Number(e.dataTransfer.getData("text/plain"));
    if (id) move.mutate({ id, status });
    setDragId(null);
  };

  const list = apps.data ?? [];
  return (
    <div className="mx-auto max-w-[96rem] px-4 py-6">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">My applications</h1>
        <p className="text-sm muted">Drag cards between columns, or use the status menu on each card.</p>
      </div>
      {apps.isLoading && <div className="mt-6"><Spinner /></div>}
      {apps.error && <div className="mt-6"><ErrorNote error={apps.error} /></div>}
      {apps.data && list.length === 0 && (
        <div className="mt-6">
          <EmptyState title="Nothing tracked yet" action={<Link to="/jobs" className="btn-primary">Browse matched jobs</Link>}>
            Save a job or apply from the results page and it shows up here.
          </EmptyState>
        </div>
      )}
      {list.length > 0 && (
        <div className="mt-5 grid gap-3 overflow-x-auto pb-4 [grid-template-columns:repeat(6,minmax(15rem,1fr))]">
          {APP_STATUSES.map((s) => {
            const items = list.filter((a) => a.status === s);
            return (
              <section
                key={s}
                aria-label={`${s} (${items.length})`}
                onDragOver={(e) => {
                  e.preventDefault();
                  setOver(s);
                }}
                onDragLeave={() => setOver((o) => (o === s ? null : o))}
                onDrop={onDrop(s)}
                className={`flex min-h-64 flex-col rounded-lg border bg-slate-50 p-2 dark:bg-slate-900/50 ${
                  over === s ? "border-brand-500 bg-brand-50 dark:bg-slate-800" : "border-slate-200 dark:border-slate-800"
                }`}
              >
                <header className="px-1 pb-2">
                  <h2 className="flex items-center justify-between text-sm font-semibold">
                    {s}
                    <span className="rounded-full bg-slate-200 px-2 text-xs font-medium dark:bg-slate-700">{items.length}</span>
                  </h2>
                  <p className="text-xs muted">{COLUMN_HINT[s]}</p>
                </header>
                <div className="space-y-2">
                  {items.map((a) => (
                    <TrackerCard
                      key={a.id}
                      a={a}
                      dragging={dragId === a.id}
                      onDragStart={(e) => {
                        e.dataTransfer.setData("text/plain", String(a.id));
                        e.dataTransfer.effectAllowed = "move";
                        setDragId(a.id);
                      }}
                      onStatus={(status) => move.mutate({ id: a.id, status })}
                      onNotes={(notes) => move.mutate({ id: a.id, notes })}
                      onDelete={() => remove.mutate(a.id)}
                    />
                  ))}
                </div>
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}

function TrackerCard({
  a,
  dragging,
  onDragStart,
  onStatus,
  onNotes,
  onDelete,
}: {
  a: Application;
  dragging: boolean;
  onDragStart: (e: DragEvent) => void;
  onStatus: (s: AppStatus) => void;
  onNotes: (n: string) => void;
  onDelete: () => void;
}) {
  const [notes, setNotes] = useState(a.notes);
  const [open, setOpen] = useState(false);
  return (
    <article draggable onDragStart={onDragStart} className={`card cursor-grab p-3 text-sm active:cursor-grabbing ${dragging ? "opacity-50" : ""}`}>
      <h3 className="font-medium leading-snug">
        {a.job_id ? (
          <Link to={`/jobs?job=${a.job_id}`} className="hover:text-brand-600 hover:underline">
            {a.title}
          </Link>
        ) : (
          a.title
        )}
      </h3>
      <p className="text-xs muted">
        {a.company}
        {a.location ? ` · ${a.location}` : ""}
      </p>
      <p className="mt-1 text-xs muted">
        {a.applied_at ? `Applied ${timeAgo(a.applied_at).toLowerCase()}` : `Added ${timeAgo(a.created_at).toLowerCase()}`}
        {a.applied_via ? ` via ${a.applied_via}` : ""}
        {a.match_score !== null ? ` · ${Math.round(a.match_score * 100)}% match` : ""}
      </p>
      {!a.job_active && <p className="mt-1 text-xs text-amber-700 dark:text-amber-300">Posting closed</p>}
      <div className="mt-2 flex items-center gap-1">
        <label className="sr-only" htmlFor={`st-${a.id}`}>
          Status
        </label>
        <select id={`st-${a.id}`} className="input w-auto py-1 text-xs" value={a.status} onChange={(e) => onStatus(e.target.value as AppStatus)}>
          {APP_STATUSES.map((s) => (
            <option key={s}>{s}</option>
          ))}
        </select>
        {a.apply_url && (
          <a href={a.apply_url} target="_blank" rel="noopener noreferrer" className="btn-ghost p-1.5" aria-label="Open application page">
            <ExternalLink className="h-3.5 w-3.5" />
          </a>
        )}
        <button className="btn-ghost p-1.5 text-xs" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
          Notes{a.notes ? " ·" : ""}
        </button>
        <button className="btn-ghost ml-auto p-1.5" onClick={onDelete} aria-label={`Remove ${a.title} from tracker`}>
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>
      {open && (
        <textarea
          className="input mt-2 min-h-20 text-xs"
          aria-label="Notes"
          placeholder="Interview dates, contacts, follow-ups"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          onBlur={() => notes !== a.notes && onNotes(notes)}
        />
      )}
    </article>
  );
}
