import type { ReactElement } from "react";
import { render } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { CandidateProvider } from "../lib/candidate";
import { TrackingProvider } from "../lib/tracking";
import type { JobSummary, MatchItem } from "../lib/types";

export function renderApp(ui: ReactElement, route = "/") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[route]}>
        <CandidateProvider>
          <TrackingProvider>{ui}</TrackingProvider>
        </CandidateProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

export const job = (over: Partial<JobSummary> = {}): JobSummary => ({
  id: "j1",
  source: "jsearch",
  title: "Machine Learning Engineer",
  company: "Nimbus",
  location: "Bengaluru, India",
  country: "India",
  remote: false,
  job_type: "full-time",
  experience_min: 1,
  experience_max: 3,
  posted_at: new Date(Date.now() - 3 * 86_400_000).toISOString(),
  apply_url: "https://www.linkedin.com/jobs/view/1/",
  apply_options: [
    { publisher: "LinkedIn", url: "https://www.linkedin.com/jobs/view/1/", is_direct: false },
    { publisher: "Naukri", url: "https://www.naukri.com/job-listings-1", is_direct: false },
    { publisher: "Nimbus careers (Greenhouse)", url: "https://boards.greenhouse.io/nimbus/jobs/1", is_direct: true },
  ],
  required_skills: [{ skill_id: "python", name: "Python", type: "required", evidence: "" }],
  preferred_skills: [],
  is_active: true,
  dedup_group_id: null,
  ...over,
});

export const matchItem = (j: JobSummary = job()): MatchItem => ({
  rank: 1,
  match_percent: 82,
  method_score: 0.82,
  job: j,
  breakdown: { score: 0.82, sem: 0.7, sem_section: 0.7, sem_full: 0.7, skill: 0.9, context: 1, context_parts: {}, penalty: 0 },
  matched_skills: [
    { skill_id: "python", name: "Python", type: "required", weight: 1, similarity: 1, resume_skill: "Python", resume_evidence: "", jd_evidence: "" },
    { skill_id: "pytorch", name: "PyTorch", type: "required", weight: 1, similarity: 1, resume_skill: "PyTorch", resume_evidence: "", jd_evidence: "" },
  ],
  missing_required: [
    { skill_id: "kubernetes", name: "Kubernetes", type: "required", weight: 1, similarity: 0, resume_skill: null, resume_evidence: "", jd_evidence: "" },
  ],
  missing_preferred: [],
});
