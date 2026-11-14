import { createContext, useCallback, useContext, useMemo, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "./api";
import { isSeeker, useAuth } from "./auth";
import type { Candidate } from "./types";

interface CandidateCtx {
  candidateId: string | null;
  candidate: Candidate | undefined;
  loading: boolean;
  setCandidate: (c: Candidate) => void;
  clear: () => void;
}

const Ctx = createContext<CandidateCtx | null>(null);

/** The signed-in student's / job seeker's latest resume (from the server, not the browser). */
export function CandidateProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const qc = useQueryClient();
  const enabled = isSeeker(user);

  const query = useQuery({
    queryKey: ["candidate", "me", user?.id],
    queryFn: async () => {
      try {
        return await api.myResume();
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) return null; // no resume yet
        throw e;
      }
    },
    enabled,
  });

  const setCandidate = useCallback(
    (c: Candidate) => {
      qc.setQueryData(["candidate", "me", user?.id], c);
      qc.invalidateQueries({ queryKey: ["match"] });
      qc.invalidateQueries({ queryKey: ["gap"] });
      qc.invalidateQueries({ queryKey: ["explain"] });
      qc.invalidateQueries({ queryKey: ["deeplinks"] });
    },
    [qc, user?.id],
  );

  const clear = useCallback(() => {
    qc.setQueryData(["candidate", "me", user?.id], null);
    qc.removeQueries({ queryKey: ["match"] });
    qc.removeQueries({ queryKey: ["applications"] });
  }, [qc, user?.id]);

  const candidate = enabled ? (query.data ?? undefined) : undefined;
  const value = useMemo(
    () => ({ candidateId: candidate?.id ?? null, candidate, loading: enabled && query.isLoading, setCandidate, clear }),
    [candidate, enabled, query.isLoading, setCandidate, clear],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useCandidate(): CandidateCtx {
  const v = useContext(Ctx);
  if (!v) throw new Error("useCandidate outside CandidateProvider");
  return v;
}
