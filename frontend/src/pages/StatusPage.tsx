import { useQuery } from "@tanstack/react-query";
import { apiGet, type Health } from "../lib/api";

export function StatusPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["health"],
    queryFn: () => apiGet<Health>("/health"),
  });

  return (
    <section className="page-narrow">
      <h1 className="text-2xl font-semibold">System status</h1>
      <div className="card p-5">
        {isLoading && <p className="text-sm muted">Checking backend...</p>}
        {error && (
          <p role="alert" className="text-sm text-red-600">
            Backend unreachable. Start it with the command in README.
          </p>
        )}
        {data && (
          <dl className="grid grid-cols-2 gap-y-2 text-sm">
            <dt className="text-slate-500">API</dt>
            <dd data-testid="api-status">{data.status}</dd>
            <dt className="text-slate-500">Version</dt>
            <dd>{data.version}</dd>
            <dt className="text-slate-500">Database</dt>
            <dd>{data.database}</dd>
            {Object.entries(data.sources_configured).map(([k, v]) => (
              <div key={k} className="contents">
                <dt className="text-slate-500">Source: {k}</dt>
                <dd className={v ? "text-emerald-600" : "text-amber-600"}>{v ? "configured" : "no key (skipped)"}</dd>
              </div>
            ))}
          </dl>
        )}
      </div>
    </section>
  );
}
