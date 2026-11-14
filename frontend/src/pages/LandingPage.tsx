import { Link } from "react-router-dom";
import { CheckCircle2 } from "lucide-react";

const POINTS = [
  "Upload your resume once; we pull out your skills and experience",
  "Jobs and internships ranked by how well your skills fit, not just keywords",
  "See why each job matches and which skills you're missing",
  "Apply on the employer's or job board's own page, then track it here",
];

export function LandingPage() {
  return (
    <div className="mx-auto grid max-w-6xl gap-10 px-4 py-12 md:grid-cols-[1.2fr_1fr] md:py-20">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Find jobs that match your skills</h1>
        <p className="mt-3 text-lg muted">
          One resume, one place to discover, compare and track jobs and internships from company career sites and job
          boards.
        </p>
        <ul className="mt-6 space-y-2">
          {POINTS.map((p) => (
            <li key={p} className="flex gap-2 text-sm">
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" aria-hidden />
              {p}
            </li>
          ))}
        </ul>
        <div className="mt-8 flex flex-wrap gap-3">
          <Link to="/register" className="btn-primary px-5 py-2.5">Join now</Link>
          <Link to="/login" className="btn-secondary px-5 py-2.5">Sign in</Link>
          <Link to="/jobs" className="btn-ghost px-5 py-2.5">Browse jobs</Link>
        </div>
      </div>
      <div className="card self-start p-6">
        <h2 className="font-semibold">For colleges</h2>
        <p className="mt-1 text-sm muted">
          Placement offices run campus drives here: bulk-import students, check eligibility, get a ranked and explainable
          shortlist, and track every round.
        </p>
        <Link to="/register" className="mt-4 inline-block text-sm text-brand-600 hover:underline">Set up your placement office</Link>
      </div>
    </div>
  );
}
