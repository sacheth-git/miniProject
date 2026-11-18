import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, Link2 } from "lucide-react";
import { analytics, type ShareLinkInfo } from "../../lib/tpo";
import { Chip, ErrorNote } from "../../components/ui";

export function ShareLinks({ driveId }: { driveId: string }) {
  const qc = useQueryClient();
  const links = useQuery({ queryKey: ["tpo", "shares", driveId], queryFn: () => analytics.shareLinks(driveId) });
  const [days, setDays] = useState(7);
  const [blind, setBlind] = useState(true);
  const [label, setLabel] = useState("");
  const [fresh, setFresh] = useState<ShareLinkInfo | null>(null);
  const [copied, setCopied] = useState(false);
  const create = useMutation({
    mutationFn: () => analytics.createShare(driveId, { expires_in_days: days, blind, label }),
    onSuccess: (l) => {
      setFresh(l);
      setCopied(false);
      qc.invalidateQueries({ queryKey: ["tpo", "shares", driveId] });
    },
  });
  const revoke = useMutation({ mutationFn: analytics.revokeShare, onSuccess: () => qc.invalidateQueries({ queryKey: ["tpo", "shares", driveId] }) });
  const url = fresh?.path ? `${window.location.origin}${fresh.path}` : "";
  const now = Date.now();

  return (
    <section className="card space-y-4 p-5" aria-labelledby="share-h">
      <div>
        <h2 id="share-h" className="flex items-center gap-2 font-semibold"><Link2 className="h-4 w-4" aria-hidden /> Recruiter share link</h2>
        <p className="mt-1 text-sm muted">A read-only page of this drive's shortlist for the recruiter. No sign-in needed; it expires, and you can revoke it.</p>
      </div>
      <div className="flex flex-wrap items-end gap-3">
        <div><label className="label" htmlFor="sl-label">Label</label><input id="sl-label" className="input w-48 py-1.5" placeholder="e.g. Acme HR" value={label} onChange={(e) => setLabel(e.target.value)} /></div>
        <div><label className="label" htmlFor="sl-days">Expires after (days)</label><input id="sl-days" type="number" min={1} max={60} className="input w-24 py-1.5" value={days} onChange={(e) => setDays(Number(e.target.value))} /></div>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={blind} onChange={(e) => setBlind(e.target.checked)} /> Hide names and emails</label>
        <button className="btn-primary h-8" disabled={create.isPending} onClick={() => create.mutate()}>Create link</button>
      </div>
      {create.error && <ErrorNote error={create.error} />}
      {fresh && (
        <div className="rounded-md bg-emerald-50 p-3 text-sm dark:bg-emerald-950" aria-live="polite">
          <p>Copy this link now; it won't be shown again.</p>
          <div className="mt-2 flex gap-2">
            <input readOnly aria-label="Share link" className="input font-mono text-xs" value={url} onFocus={(e) => e.target.select()} />
            <button className="btn-secondary" onClick={() => navigator.clipboard?.writeText(url).then(() => setCopied(true))}><Copy className="h-4 w-4" aria-hidden /> {copied ? "Copied" : "Copy"}</button>
          </div>
        </div>
      )}
      {links.data && links.data.length > 0 && (
        <table className="w-full text-sm">
          <caption className="sr-only">Share links</caption>
          <thead className="text-left text-xs muted"><tr><th className="py-1">Link</th><th>Names</th><th>Expires</th><th className="text-right">Views</th><th /></tr></thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {links.data.map((l) => {
              const expired = new Date(l.expires_at).getTime() < now;
              return (
                <tr key={l.id}>
                  <td className="py-1.5">{l.label || "Untitled"} <span className="font-mono text-xs muted">…{l.token_hint}</span></td>
                  <td>{l.blind ? "Hidden" : "Shown"}</td>
                  <td>{l.revoked_at ? <Chip tone="slate">Revoked</Chip> : expired ? <Chip tone="amber">Expired</Chip> : new Date(l.expires_at).toLocaleDateString()}</td>
                  <td className="text-right tabular-nums">{l.views}</td>
                  <td className="text-right">{!l.revoked_at && !expired && <button className="btn-ghost h-8 px-2 text-xs" onClick={() => revoke.mutate(l.id)}>Revoke</button>}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </section>
  );
}
