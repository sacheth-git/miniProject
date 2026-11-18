import { Link } from "react-router-dom";
import { Building2, Check, Clock, MapPin } from "lucide-react";
import { Chip, MatchRing, ScoreBar } from "../components/ui";

const POINTS = [
  "Upload your resume once; we pull out your skills and experience",
  "Jobs and internships ranked by how well your skills fit, not just keywords",
  "See why each job matches and which skills you're missing",
  "Apply on the employer's or job board's own page, then track it here",
];

const CAMPUS = [
  ["Bulk-import students", "From a spreadsheet, with invite codes for self sign-up"],
  ["Eligibility with reasons", "CGPA, branch, backlogs and batch checked for every drive"],
  ["Ranked, explainable shortlists", "Blind mode hides names; every change is audit-logged"],
];

/** A worked example of the match view, built from the same components the app uses. */
function MatchPreview() {
  return (
    <div className="card p-5 shadow-sm sm:p-6" aria-label="Example of a job match">
      <div className="flex items-start gap-4">
        <div className="min-w-0 flex-1">
          <p className="text-xs muted">Example match</p>
          <h2 className="mt-1 text-lg font-semibold leading-snug">Machine Learning Engineer</h2>
          <p className="mt-1 flex items-center gap-1 text-sm text-slate-700 dark:text-slate-300">
            <Building2 className="h-4 w-4 muted" aria-hidden />
            Kaveri Systems
          </p>
          <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs muted">
            <span className="inline-flex items-center gap-1"><MapPin className="h-3.5 w-3.5" aria-hidden />Bengaluru</span>
            <span>Full-time</span>
            <span>0-2 years</span>
            <span className="inline-flex items-center gap-1"><Clock className="h-3.5 w-3.5" aria-hidden />2 days ago</span>
          </p>
        </div>
        <MatchRing percent={82} size={80} />
      </div>

      <div className="mt-6 space-y-3">
        <ScoreBar label="Experience and projects" value={0.78} />
        <ScoreBar label="Skills the job asks for" value={0.86} />
        <ScoreBar label="Location, level and job type" value={0.75} />
      </div>

      <div className="mt-6 border-t border-slate-100 pt-4 dark:border-slate-800">
        <p className="text-xs muted">Matched from your resume</p>
        <div className="mt-2 flex flex-wrap gap-1.5">
          <Chip tone="green">Python</Chip>
          <Chip tone="green">PyTorch</Chip>
          <Chip tone="green" title="You have: scikit-learn">Machine learning</Chip>
          <Chip tone="green">SQL</Chip>
        </div>
        <p className="mt-4 text-xs muted">Required, not on your resume</p>
        <div className="mt-2 flex flex-wrap gap-1.5">
          <Chip tone="red">Docker</Chip>
          <Chip tone="red">Kubernetes</Chip>
        </div>
      </div>
    </div>
  );
}

export function LandingPage() {
  return (
    <div className="animate-enter">
      <section className="mx-auto grid w-full max-w-6xl items-center gap-12 px-4 py-16 sm:px-6 md:grid-cols-[1fr_minmax(0,28rem)] md:py-24">
        <div>
          <h1 className="text-3xl font-semibold text-slate-900 sm:text-4xl sm:leading-tight dark:text-white">
            Find jobs that match your skills
          </h1>
          <p className="mt-4 max-w-xl text-lg muted">
            One resume, one place to discover, compare and track jobs and internships from company career sites and job
            boards.
          </p>
          <ul className="mt-8 space-y-3">
            {POINTS.map((p) => (
              <li key={p} className="flex gap-3 text-sm text-slate-700 dark:text-slate-300">
                <Check className="mt-0.5 h-4 w-4 shrink-0 text-brand-600 dark:text-brand-200" aria-hidden />
                {p}
              </li>
            ))}
          </ul>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link to="/register" className="btn-primary h-10 px-5">Join now</Link>
            <Link to="/jobs" className="btn-secondary h-10 px-5">Browse jobs</Link>
          </div>
        </div>
        <MatchPreview />
      </section>

      <section className="border-t border-slate-200 dark:border-slate-800" aria-labelledby="colleges-h">
        <div className="mx-auto grid w-full max-w-6xl gap-8 px-4 py-12 sm:px-6 md:grid-cols-[1fr_2fr]">
          <div>
            <h2 id="colleges-h" className="text-xl font-semibold">For colleges</h2>
            <p className="mt-2 text-sm muted">
              Placement offices run campus drives here and track every round, from eligibility to accepted offers.
            </p>
            <Link to="/register" className="link mt-4 inline-block text-sm">Set up your placement office</Link>
          </div>
          <dl className="grid gap-6 sm:grid-cols-3">
            {CAMPUS.map(([t, d]) => (
              <div key={t}>
                <dt className="text-sm font-medium">{t}</dt>
                <dd className="mt-1 text-sm muted">{d}</dd>
              </div>
            ))}
          </dl>
        </div>
      </section>
    </div>
  );
}
