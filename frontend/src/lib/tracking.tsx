import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import { useCandidate } from "./candidate";
import type { Application, AppStatus, ApplyOption, JobSummary } from "./types";

interface Pending {
  job: JobSummary;
  option: ApplyOption;
}

interface TrackingCtx {
  statusOf: (jobId: string) => AppStatus | undefined;
  applications: Application[];
  track: (job: JobSummary, status: AppStatus, option?: ApplyOption) => void;
  openApply: (job: JobSummary, option: ApplyOption) => void;
}

const Ctx = createContext<TrackingCtx | null>(null);

export function TrackingProvider({ children }: { children: ReactNode }) {
  const { candidateId } = useCandidate();
  const qc = useQueryClient();
  const [pending, setPending] = useState<Pending | null>(null);
  const [asking, setAsking] = useState(false);
  const leftAt = useRef<number>(0);

  const apps = useQuery({
    queryKey: ["applications", candidateId],
    queryFn: () => api.applications(candidateId!),
    enabled: !!candidateId,
  });

  const mut = useMutation({
    mutationFn: (v: { job: JobSummary; status: AppStatus; option?: ApplyOption }) =>
      api.track({
        candidate_id: candidateId!,
        job_id: v.job.id,
        status: v.status,
        applied_via: v.option?.publisher,
        apply_url: v.option?.url,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["applications", candidateId] }),
  });

  const byJob = useMemo(() => {
    const m = new Map<string, AppStatus>();
    for (const a of apps.data ?? []) if (a.job_id) m.set(a.job_id, a.status);
    return m;
  }, [apps.data]);

  const track = useCallback(
    (job: JobSummary, status: AppStatus, option?: ApplyOption) => {
      if (candidateId) mut.mutate({ job, status, option });
    },
    [candidateId, mut],
  );

  const openApply = useCallback(
    (job: JobSummary, option: ApplyOption) => {
      window.open(option.url, "_blank", "noopener,noreferrer");
      if (!candidateId) return;
      leftAt.current = Date.now();
      setPending({ job, option });
    },
    [candidateId],
  );

  // When the user comes back to this tab after opening an application, ask once.
  useEffect(() => {
    if (!pending) return;
    const onFocus = () => {
      if (Date.now() - leftAt.current > 1500) setAsking(true);
    };
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [pending]);

  const close = () => {
    setAsking(false);
    setPending(null);
  };

  const value = useMemo(
    () => ({ statusOf: (id: string) => byJob.get(id), applications: apps.data ?? [], track, openApply }),
    [byJob, apps.data, track, openApply],
  );

  return (
    <Ctx.Provider value={value}>
      {children}
      {asking && pending && (
        <div
          role="dialog"
          aria-modal="false"
          aria-labelledby="applied-q"
          className="card fixed bottom-4 right-4 z-50 w-[min(24rem,calc(100vw-2rem))] p-4 shadow-lg"
        >
          <p id="applied-q" className="text-sm font-semibold">
            Did you apply?
          </p>
          <p className="mt-1 text-sm muted">
            {pending.job.title} at {pending.job.company}, via {pending.option.publisher}
          </p>
          <div className="mt-3 flex gap-2">
            <button
              className="btn-primary"
              onClick={() => {
                track(pending.job, "Applied", pending.option);
                close();
              }}
            >
              Yes, mark applied
            </button>
            <button
              className="btn-secondary"
              onClick={() => {
                track(pending.job, "Ready", pending.option);
                close();
              }}
            >
              Not yet
            </button>
            <button className="btn-ghost ml-auto" onClick={close}>
              Dismiss
            </button>
          </div>
        </div>
      )}
    </Ctx.Provider>
  );
}

export function useTracking(): TrackingCtx {
  const v = useContext(Ctx);
  if (!v) throw new Error("useTracking outside TrackingProvider");
  return v;
}
