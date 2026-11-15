import { API_BASE, ApiError } from "./api";
import { getTokens, refreshTokens } from "./session";

/** Authenticated fetch for the TPO API (JSON in/out). */
async function call<T>(path: string, init?: RequestInit, retried = false): Promise<T> {
  const headers = new Headers(init?.headers);
  const t = getTokens();
  if (t) headers.set("Authorization", `Bearer ${t.access_token}`);
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (res.status === 401 && !retried && t && (await refreshTokens(API_BASE))) return call<T>(path, init, true);
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const body = await res.json();
      msg = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      /* non-JSON */
    }
    throw new ApiError(res.status, msg);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

/** Download an authenticated file (exports, credentials) via a blob URL. */
export async function download(path: string, fallbackName: string): Promise<void> {
  const t = getTokens();
  const res = await fetch(`${API_BASE}${path}`, { headers: t ? { Authorization: `Bearer ${t.access_token}` } : {} });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      msg = (await res.json()).detail ?? msg;
    } catch {
      /* binary */
    }
    throw new ApiError(res.status, msg);
  }
  const name = /filename="([^"]+)"/.exec(res.headers.get("Content-Disposition") ?? "")?.[1] ?? fallbackName;
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export interface DriveSkill {
  skill_id: string;
  name: string;
  type: "required" | "preferred";
  weight: number;
  evidence?: string;
}

export interface Rules {
  allowed_branches: string[];
  batch_years: number[];
  min_cgpa: number | null;
  max_active_backlogs: number | null;
  max_history_backlogs: number | null;
  min_tenth: number | null;
  min_twelfth: number | null;
  custom_rules: { field: string; op: string; value: number | string; label?: string }[];
}

export interface Drive {
  id: string;
  company: string;
  role: string;
  job_type: "internship" | "fte" | "intern+ppo";
  jd_text: string;
  jd_filename: string | null;
  skills: DriveSkill[];
  ctc_lpa: number | null;
  stipend_month: number | null;
  location: string | null;
  rounds: string[];
  deadline: string | null;
  status: "draft" | "open" | "closed" | "completed";
  category: "regular" | "dream";
  rules: Rules;
  created_at: string;
  updated_at: string;
  counts: { applied?: number; shortlisted?: number };
}

export type DriveInput = Omit<Drive, "id" | "jd_filename" | "created_at" | "updated_at" | "counts">;

export interface EligibilityStudent {
  user_id: string;
  roll_no: string | null;
  name: string;
  branch: string | null;
  batch_year: number | null;
  cgpa: number | null;
  placed_status: string;
  has_resume: boolean;
  eligible: boolean;
  reasons: string[];
}

export interface EligibilityResult {
  rules: Rules;
  total: number;
  eligible: number;
  reason_counts: Record<string, number>;
  students: EligibilityStudent[];
}

export interface ShortlistRow {
  rank: number | null;
  user_id: string;
  roll_no: string | null;
  name: string | null;
  email: string | null;
  branch: string | null;
  batch_year: number | null;
  cgpa: number | null;
  match_percent: number | null;
  skill_percent: number | null;
  matched_skills: string[];
  missing_required: string[];
  placed_status: string;
  stage: string | null;
  applied: boolean;
  shortlisted: boolean;
  has_resume: boolean;
}

export interface Shortlist {
  drive_id: string;
  blind: boolean;
  note: string;
  rows: ShortlistRow[];
  shortlisted: number;
  changed?: number;
}

export interface StudentExplain {
  user_id: string;
  roll_no: string | null;
  name: string | null;
  eligible: boolean;
  reasons: string[];
  rank: number | null;
  has_resume: boolean;
  explanation?: import("./types").Explanation;
}

export interface ImportRow {
  line: number;
  roll_no: string;
  name: string;
  email: string;
  branch: string;
  batch: number | null;
  cgpa: number | null;
  has_resume: boolean;
  action: "create" | "update";
  status: "ok" | "warning" | "error";
  errors: string[];
  warnings: string[];
}

export interface ImportPreview {
  job_id: string;
  total: number;
  ok: number;
  warnings: number;
  errors: number;
  creates: number;
  updates: number;
  with_resume: number;
  rows: ImportRow[];
}

export interface ImportStatus {
  job_id: string;
  status: "preview" | "running" | "done" | "failed";
  total: number;
  done: number;
  created: number;
  updated: number;
  resumes_parsed: number;
  errors: { line: number; roll_no: string; error: string }[];
  message: string;
  credentials_available: boolean;
}

export interface AuditItem {
  id: number;
  actor_email: string;
  action: string;
  entity: string;
  entity_id: string | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  at: string;
}

export interface Policy {
  one_offer_rule: boolean;
  dream_multiplier: number;
  block_after_accept: boolean;
}

export const tpo = {
  drives: () => call<Drive[]>("/tpo/drives"),
  drive: (id: string) => call<Drive>(`/tpo/drives/${id}`),
  createDrive: (d: Partial<DriveInput>) => call<Drive>("/tpo/drives", json("POST", d)),
  updateDrive: (id: string, d: Partial<DriveInput> & { reextract_skills?: boolean }) => call<Drive>(`/tpo/drives/${id}`, json("PUT", d)),
  deleteDrive: (id: string) => call<void>(`/tpo/drives/${id}`, { method: "DELETE" }),
  extractJd: (file: File | null, text: string | null) => {
    const fd = new FormData();
    if (file) fd.append("file", file);
    if (text) fd.append("text", text);
    return call<{ text: string; skills: DriveSkill[]; filename: string | null }>("/tpo/drives/extract-jd", { method: "POST", body: fd });
  },
  eligibility: (id: string) => call<EligibilityResult>(`/tpo/drives/${id}/eligibility`),
  setRules: (id: string, r: Rules) => call<EligibilityResult>(`/tpo/drives/${id}/eligibility`, json("PUT", r)),
  shortlist: (id: string, blind: boolean) => call<Shortlist>(`/tpo/drives/${id}/shortlist?blind=${blind}`),
  select: (id: string, body: { mode: "top" | "threshold" | "manual"; n?: number; min_score?: number; add?: string[]; remove?: string[]; replace?: boolean }) =>
    call<Shortlist>(`/tpo/drives/${id}/shortlist`, json("POST", body)),
  explain: (id: string, uid: string, blind: boolean) => call<StudentExplain>(`/tpo/drives/${id}/students/${uid}/explain?blind=${blind}`),
  importPreview: (csv: File, zip: File | null) => {
    const fd = new FormData();
    fd.append("csv_file", csv);
    if (zip) fd.append("resumes_zip", zip);
    return call<ImportPreview>("/tpo/students/import/preview", { method: "POST", body: fd });
  },
  importCommit: (jobId: string) => call<ImportStatus>(`/tpo/students/import/${jobId}/commit`, { method: "POST" }),
  importStatus: (jobId: string) => call<ImportStatus>(`/tpo/students/import/${jobId}`),
  audit: (q: Record<string, string | number>) =>
    call<{ total: number; items: AuditItem[] }>(`/tpo/audit?${new URLSearchParams(Object.entries(q).filter(([, v]) => v !== "").map(([k, v]) => [k, String(v)]))}`),
  policy: () => call<Policy>("/tpo/settings/policy"),
  setPolicy: (p: Policy) => call<Policy>("/tpo/settings/policy", json("PUT", p)),
};

// ---------------- rounds & offers (TPO) ----------------
export interface StageCard {
  application_id: number;
  student_id: string;
  roll_no: string | null;
  name: string | null;
  branch: string | null;
  cgpa: number | null;
  stage: string;
  source: string;
  match_percent: number | null;
  history: { stage: string; at: string; by: string; note?: string }[];
  notes: string;
}

export interface StageBoard {
  stages: string[];
  columns: Record<string, StageCard[]>;
  moved?: number;
}

export interface OfferRow {
  id: number;
  drive_id: string;
  company: string;
  role: string;
  student_id: string;
  roll_no: string | null;
  name: string;
  branch: string | null;
  ctc_lpa: number;
  status: "pending" | "accepted" | "declined";
  note: string;
  created_at: string;
  decided_at: string | null;
}

export const rounds = {
  board: (id: string) => call<StageBoard>(`/tpo/drives/${id}/stages`),
  move: (id: string, student_ids: string[], stage: string, note = "") =>
    call<StageBoard>(`/tpo/drives/${id}/stages`, json("POST", { student_ids, stage, note })),
  results: (id: string, round_name: string, file: File) => {
    const fd = new FormData();
    fd.append("round_name", round_name);
    fd.append("file", file);
    return call<{ round: string; next_stage: string; passed: number; failed: number; problems: string[] }>(`/tpo/drives/${id}/stages/results`, { method: "POST", body: fd });
  },
  offers: (driveId?: string) => call<OfferRow[]>(`/tpo/offers${driveId ? `?drive_id=${driveId}` : ""}`),
  offer: (drive_id: string, student_id: string, ctc_lpa?: number) => call<OfferRow>("/tpo/offers", json("POST", { drive_id, student_id, ctc_lpa })),
  decide: (offerId: number, status: "accepted" | "declined") => call<OfferRow>(`/tpo/offers/${offerId}`, json("PATCH", { status })),
};

// ---------------- student campus ----------------
export interface CampusDrive {
  id: string;
  company: string;
  role: string;
  job_type: Drive["job_type"];
  ctc_lpa: number | null;
  stipend_month: number | null;
  location: string | null;
  category: "regular" | "dream";
  status: Drive["status"];
  deadline: string | null;
  deadline_passed: boolean;
  rounds: string[];
  eligible: boolean;
  reasons: string[];
  match_percent: number | null;
  matched_skills: string[];
  missing_required: string[];
  missing_preferred: string[];
  stage: string | null;
  applied: boolean;
  offer: { id: number; ctc_lpa: number; status: "pending" | "accepted" | "declined" } | null;
}

export interface CampusDriveDetail extends CampusDrive {
  jd_text: string;
  stages: string[];
  timeline: { stage: string; at: string; by: string; note?: string }[];
  explanation: import("./types").Explanation | null;
}

export interface Readiness {
  score: number;
  match: number | null;
  completeness: number;
  ats: number;
  drives_considered: number;
  checks: { profile: { label: string; ok: boolean; fix: string }[]; resume: { label: string; ok: boolean; fix: string }[] };
  actions: { kind: string; text: string }[];
  weights: Record<string, number>;
}

export interface NotificationItem {
  id: number;
  kind: string;
  title: string;
  body: string;
  link: string | null;
  read: boolean;
  created_at: string;
}

export interface TrackerItem {
  kind: "campus" | "open_market";
  source_label: string;
  id: string;
  title: string;
  company: string;
  stage: string;
  updated_at: string;
  link: string | null;
  apply_url: string | null;
  final: boolean;
}

export const campus = {
  drives: () => call<CampusDrive[]>("/student/drives"),
  drive: (id: string) => call<CampusDriveDetail>(`/student/drives/${id}`),
  apply: (id: string) => call<CampusDriveDetail>(`/student/drives/${id}/apply`, { method: "POST" }),
  withdraw: (id: string) => call<CampusDriveDetail>(`/student/drives/${id}/withdraw`, { method: "POST" }),
  decide: (offerId: number, decision: "accept" | "decline") => call<CampusDriveDetail>(`/student/offers/${offerId}/${decision}`, { method: "POST" }),
  readiness: () => call<Readiness>("/student/readiness"),
  notifications: () => call<{ unread: number; items: NotificationItem[] }>("/student/notifications"),
  markRead: (ids?: number[]) => call<{ marked: number }>("/student/notifications/read", json("POST", ids ?? [])),
  tracker: () => call<TrackerItem[]>("/student/tracker"),
};
