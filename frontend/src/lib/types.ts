export interface Skill {
  skill_id: string;
  name: string;
  esco_uri?: string | null;
  confidence: number;
  evidence: string;
  section: string;
  method: string;
  mentions: number;
}

export interface Preferences {
  target_role?: string | null;
  locations: string[];
  remote_ok: boolean;
  job_types: string[];
}

export interface ProcessingStep {
  name: string;
  ms: number;
  detail: string;
}

export interface Candidate {
  id: string;
  filename: string | null;
  sections: Record<string, string>;
  skills: Skill[];
  years_experience: number;
  education_level: string;
  bias_aware: boolean;
  preferences: Partial<Preferences>;
  pages: number;
  masked_text: string | null;
  created_at: string;
  steps?: ProcessingStep[];
}

export interface ApplyOption {
  publisher: string;
  url: string;
  is_direct: boolean;
}

export interface JDSkill {
  skill_id: string;
  name: string;
  type: "required" | "preferred";
  evidence: string;
}

export interface JobSummary {
  id: string;
  source: string;
  title: string;
  company: string;
  location: string | null;
  country: string | null;
  remote: boolean;
  job_type: string;
  experience_min: number | null;
  experience_max: number | null;
  posted_at: string | null;
  apply_url: string;
  apply_options: ApplyOption[];
  required_skills: JDSkill[];
  preferred_skills: JDSkill[];
  is_active: boolean;
  dedup_group_id: string | null;
}

export interface JobDetail extends JobSummary {
  description: string;
  responsibilities: string;
  source_url: string | null;
  first_seen_at: string;
  last_checked_at: string | null;
}

export interface JobPage {
  total: number;
  limit: number;
  offset: number;
  items: JobSummary[];
}

export interface SkillMatch {
  skill_id: string;
  name: string;
  type: "required" | "preferred";
  weight: number;
  similarity: number;
  resume_skill: string | null;
  resume_evidence: string;
  jd_evidence: string;
}

export interface Breakdown {
  score: number;
  sem: number;
  sem_section: number;
  sem_full: number;
  skill: number;
  context: number;
  context_parts: Record<string, number>;
  penalty: number;
}

export interface MatchItem {
  rank: number;
  match_percent: number;
  method_score: number;
  job: JobSummary;
  breakdown: Breakdown;
  matched_skills: SkillMatch[];
  missing_required: SkillMatch[];
  missing_preferred: SkillMatch[];
}

export interface MatchResponse {
  candidate_id: string;
  method: string;
  retrieved: number;
  returned: number;
  timings_ms: Record<string, number>;
  items: MatchItem[];
}

export interface Explanation extends Breakdown {
  job_id: string;
  matched: SkillMatch[];
  missing_required: SkillMatch[];
  missing_preferred: SkillMatch[];
  weights: Record<string, number>;
  contributions: Record<string, number>;
  summary: string;
}

export interface GapSkill {
  skill_id: string;
  name: string;
  jobs_improved: number;
  avg_gain: number;
  total_gain: number;
  message: string;
  example_jobs: { id: string; title: string; company: string }[];
}

export interface GapResponse {
  jobs_considered: number;
  by_total_gain: GapSkill[];
  by_jobs_improved: GapSkill[];
}

export interface DeepLinks {
  role: string;
  location: string | null;
  internship: boolean;
  keywords: string[];
  links: { platform: string; label: string; url: string }[];
}

export const APP_STATUSES = ["Saved", "Ready", "Applied", "Interview", "Offer", "Rejected"] as const;
export type AppStatus = (typeof APP_STATUSES)[number];

export interface Application {
  id: number;
  candidate_id: string;
  job_id: string | null;
  status: AppStatus;
  title: string;
  company: string;
  location: string | null;
  source: string;
  apply_url: string;
  applied_via: string | null;
  match_score: number | null;
  notes: string;
  status_history: { status: string; at: string }[];
  applied_at: string | null;
  created_at: string;
  updated_at: string;
  job_active: boolean;
}

export interface ImportResult {
  created: number;
  updated: number;
  jobs: JobSummary[];
  skipped_files: string[];
}

export interface JobFilters {
  role?: string;
  location?: string;
  remote?: "true" | "false";
  type?: string;
  source?: string;
  min_exp?: string;
  max_exp?: string;
  posted_within?: string;
}
