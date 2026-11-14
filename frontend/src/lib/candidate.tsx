import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "./api";
import type { Candidate } from "./types";

const KEY = "skillmatch.candidateId";

function readId(): string | null {
  try {
    return localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

function writeId(id: string | null): void {
  try {
    if (id) localStorage.setItem(KEY, id);
    else localStorage.removeItem(KEY);
  } catch {
    /* storage unavailable: the session still works in memory */
  }
}

interface CandidateCtx {
  candidateId: string | null;
  candidate: Candidate | undefined;
  loading: boolean;
  setCandidate: (c: Candidate) => void;
  clear: () => void;
}

const Ctx = createContext<CandidateCtx | null>(null);

export function CandidateProvider({ children }: { children: ReactNode }) {
  const [candidateId, setId] = useState<string | null>(readId);
  const qc = useQueryClient();

  const query = useQuery({
    queryKey: ["candidate", candidateId],
    queryFn: () => api.getResume(candidateId!),
    enabled: !!candidateId,
    retry: (n, err) => !(err instanceof ApiError && err.status === 404) && n < 1,
  });

  // A stored id whose resume was deleted elsewhere: forget it.
  const gone = query.error instanceof ApiError && query.error.status === 404;
  useEffect(() => {
    if (gone) {
      writeId(null);
      setId(null);
    }
  }, [gone]);

  const setCandidate = useCallback(
    (c: Candidate) => {
      writeId(c.id);
      setId(c.id);
      qc.setQueryData(["candidate", c.id], c);
      qc.invalidateQueries({ queryKey: ["match"] });
      qc.invalidateQueries({ queryKey: ["gap"] });
    },
    [qc],
  );

  const clear = useCallback(() => {
    writeId(null);
    setId(null);
    qc.clear();
  }, [qc]);

  const value = useMemo(
    () => ({ candidateId, candidate: query.data, loading: query.isLoading, setCandidate, clear }),
    [candidateId, query.data, query.isLoading, setCandidate, clear],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useCandidate(): CandidateCtx {
  const v = useContext(Ctx);
  if (!v) throw new Error("useCandidate outside CandidateProvider");
  return v;
}
