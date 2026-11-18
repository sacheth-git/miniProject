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
import { getTokens, refreshTokens, type Tokens } from "./session";

export const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

function withAuth(init?: RequestInit): RequestInit {
  const t = getTokens();
  if (!t) return init ?? {};
  const headers = new Headers(init?.headers);
  headers.set("Authorization", `Bearer ${t.access_token}`);
  return { ...init, headers };
}

async function request<T>(path: string, init?: RequestInit, retried = false): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, withAuth(init));
  // Expired access token: refresh once and retry.
  if (res.status === 401 && !retried && getTokens() && !path.startsWith("/auth/")) {
    if (await refreshTokens(API_BASE)) return request<T>(path, init, true);
  }
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

export interface JobStats {
  total: number;
  india: number;
  remote: number;
  internships: number;
  companies: number;
  by_source: { source: string; count: number }[];
}

export const api = {
  health: () => request<Health>("/health"),

  register: (body: RegisterBody) => request<TokenResponse>("/auth/register", json("POST", body)),
  login: (email: string, password: string) => request<TokenResponse>("/auth/login", json("POST", { email, password })),
  me: () => request<User>("/auth/me"),
  logout: () => request<void>("/auth/logout", { method: "POST" }),
  changePassword: (current_password: string, new_password: string) =>
    request<TokenResponse>("/auth/change-password", json("POST", { current_password, new_password })),
  joinInstitution: (invite_code: string, consent: boolean, roll_no?: string) =>
    request<User>("/auth/join-institution", json("POST", { invite_code, consent, roll_no })),
  deleteAccount: () => request<void>("/auth/me", { method: "DELETE" }),
  consent: () => request<Consent>("/student/consent"),
  giveConsent: () => request<Consent>("/student/consent", { method: "POST" }),
  withdrawConsent: () => request<Consent>("/student/consent", { method: "DELETE" }),

  tpoInstitution: () => request<InstitutionInfo>("/tpo/institution"),
  tpoStudents: () => request<StudentRow[]>("/tpo/students"),
  myResume: () => request<Candidate>("/resume/me"),

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

  jobs: (f: JobFilters, limit: number, offset: number, candidateId?: string | null, sort: "mixed" | "recent" = "mixed") =>
    request<JobPage>(`/jobs${qs({ ...f, limit, offset, candidate_id: candidateId, sort })}`),
  jobStats: () => request<JobStats>("/jobs/stats"),
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

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: "student" | "job_seeker" | "tpo" | "recruiter_view";
  is_admin: boolean;
  must_reset_password: boolean;
  institution_id: string | null;
  institution_name: string | null;
  consent: boolean | null;
  consent_status: "pending" | "given" | "withdrawn" | null;
  candidate_id: string | null;
}

export interface TokenResponse extends Tokens {
  token_type: string;
  user: User;
}

export interface RegisterBody {
  email: string;
  password: string;
  full_name: string;
  role: "student" | "job_seeker" | "tpo";
  institution_name?: string;
  invite_code?: string;
  consent?: boolean;
}

export interface Consent {
  institution_name: string | null;
  consent: boolean;
  consent_given_at: string | null;
  consent_withdrawn_at: string | null;
  tpo_can_see: string[];
}

export interface InstitutionInfo {
  id: string;
  name: string;
  code: string;
  invite_code: string;
  settings: Record<string, unknown>;
}

export interface StudentRow {
  user_id: string;
  full_name: string;
  email: string;
  roll_no: string | null;
  branch: string | null;
  batch_year: number | null;
  cgpa: number | null;
  placed_status: string;
  consent: boolean;
  consent_status: "pending" | "given" | "withdrawn";
  active_backlogs: number;
  must_reset_password: boolean;
  has_resume: boolean;
}

export interface Health {
  status: string;
  version: string;
  database: string;
  sources_configured: Record<string, boolean>;
}
