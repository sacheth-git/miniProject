import type {
  Application,
  AppStatus,
  Candidate,
  DeepLinks,
  Explanation,
  GapResponse,
  ImportResult,
  JobDetail,
  JobFilters,
  JobPage,
  MatchResponse,
  Preferences,
} from "./types";

export const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const body = await res.json();
      msg = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, msg);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export function qs(params: Record<string, string | number | boolean | undefined | null>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : "";
}

export const apiGet = <T>(path: string) => request<T>(path);

export const api = {
  health: () => request<Health>("/health"),

  uploadResume: (file: File, biasAware: boolean) => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("bias_aware", String(biasAware));
    return request<Candidate>("/resume/upload", { method: "POST", body: fd });
  },
  getResume: (id: string) => request<Candidate>(`/resume/${id}`),
  editSkills: (id: string, add: string[], remove: string[]) =>
    request<Candidate>(`/resume/${id}/skills`, json("PUT", { add, remove })),
  setPreferences: (id: string, prefs: Preferences) => request<Candidate>(`/resume/${id}/preferences`, json("PUT", prefs)),
  setBiasAware: (id: string, bias_aware: boolean) =>
    request<Candidate>(`/resume/${id}/settings`, json("PUT", { bias_aware })),
  deleteResume: (id: string) => request<void>(`/resume/${id}`, { method: "DELETE" }),

  jobs: (f: JobFilters, limit: number, offset: number, candidateId?: string | null) =>
    request<JobPage>(`/jobs${qs({ ...f, limit, offset, candidate_id: candidateId })}`),
  job: (id: string) => request<JobDetail>(`/jobs/${id}`),

  match: (candidateId: string, f: JobFilters, limit: number, method = "ours") =>
    request<MatchResponse>(`/match/${candidateId}${qs({ ...f, limit, method })}`),
  explain: (candidateId: string, jobId: string) => request<Explanation>(`/match/${candidateId}/${jobId}/explain`),
  gap: (candidateId: string, f: JobFilters) => request<GapResponse>(`/gap/${candidateId}${qs({ ...f })}`),
  deeplinks: (candidateId: string) => request<DeepLinks>(`/deeplinks/${candidateId}`),

  importText: (body: { text: string; url?: string; title?: string; company?: string; location?: string; candidate_id?: string }) =>
    request<ImportResult>("/import/text", json("POST", body)),
  importEmail: (files: File[], candidateId?: string | null) => {
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    if (candidateId) fd.append("candidate_id", candidateId);
    return request<ImportResult>("/import/email", { method: "POST", body: fd });
  },

  applications: (candidateId: string) => request<Application[]>(`/applications${qs({ candidate_id: candidateId })}`),
  track: (body: { candidate_id: string; job_id: string; status: AppStatus; applied_via?: string; apply_url?: string }) =>
    request<Application>("/applications", json("POST", body)),
  updateApplication: (id: number, patch: { status?: AppStatus; notes?: string }) =>
    request<Application>(`/applications/${id}`, json("PATCH", patch)),
  deleteApplication: (id: number) => request<void>(`/applications/${id}`, { method: "DELETE" }),
};

export interface Health {
  status: string;
  version: string;
  database: string;
  sources_configured: Record<string, boolean>;
}
