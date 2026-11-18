import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Bell } from "lucide-react";
import { campus } from "../lib/tpo";
import { timeAgo } from "../lib/format";

export function NotificationBell() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const q = useQuery({ queryKey: ["notifications"], queryFn: campus.notifications, refetchInterval: 60_000 });
  const read = useMutation({ mutationFn: (ids?: number[]) => campus.markRead(ids), onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }) });

  useEffect(() => {
    if (!open) return;
    const on = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    const key = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", on);
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("mousedown", on);
      document.removeEventListener("keydown", key);
    };
  }, [open]);

  const unread = q.data?.unread ?? 0;
  return (
    <div className="relative" ref={ref}>
      <button className="btn-ghost relative w-9 p-0" aria-label={`Notifications${unread ? `, ${unread} unread` : ""}`} aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <Bell className="h-4 w-4" />
        {unread > 0 && <span className="absolute right-1 top-1 grid h-4 min-w-4 place-items-center rounded-full bg-rose-600 px-1 text-[10px] font-semibold text-white">{unread > 9 ? "9+" : unread}</span>}
      </button>
      {open && (
        <div className="card absolute right-0 z-40 mt-1 w-80 shadow-lg" role="dialog" aria-label="Notifications">
          <div className="flex items-center justify-between border-b border-slate-100 px-3 py-2 dark:border-slate-800">
            <span className="text-sm font-semibold">Notifications</span>
            {unread > 0 && <button className="text-xs link" onClick={() => read.mutate(undefined)}>Mark all read</button>}
          </div>
          <ul className="max-h-96 divide-y divide-slate-100 overflow-y-auto dark:divide-slate-800">
            {(q.data?.items ?? []).map((n) => (
              <li key={n.id}>
                <button
                  className={`block w-full px-3 py-2 text-left text-sm hover:bg-slate-50 dark:hover:bg-slate-800 ${n.read ? "" : "bg-brand-50/60 dark:bg-slate-800/60"}`}
                  onClick={() => {
                    if (!n.read) read.mutate([n.id]);
                    setOpen(false);
                    if (n.link) navigate(n.link);
                  }}
                >
                  <span className={n.read ? "" : "font-medium"}>{n.title}</span>
                  <span className="mt-0.5 block text-xs muted">{n.body}</span>
                  <span className="mt-0.5 block text-[11px] muted">{timeAgo(n.created_at)}</span>
                </button>
              </li>
            ))}
            {q.data && q.data.items.length === 0 && <li className="px-3 py-6 text-center text-sm muted">No notifications yet</li>}
          </ul>
        </div>
      )}
    </div>
  );
}
