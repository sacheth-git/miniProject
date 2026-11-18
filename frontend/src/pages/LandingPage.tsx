import { useEffect, useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { ArrowRight, Building2, Clock, GraduationCap, MapPin, Search } from "lucide-react";
import { api } from "../lib/api";
import { SOURCE_LABELS } from "../lib/format";
import { Chip, MatchRing, ScoreBar } from "../components/ui";

const POPULAR: [string, Record<string, string>][] = [
  ["Software engineer", { role: "software engineer" }],
  ["Data analyst", { role: "data analyst" }],
  ["Internships", { type: "internship" }],
  ["Remote", { remote: "true" }],
  ["Jobs in India", { location: "india" }],
];

const STEPS = [
  ["Upload your resume", "HireX reads your skills, projects and experience. Personal details are hidden before matching."],
  ["Get one ranked list", "Every job from every source, scored by how well your skills fit, with the reasons and the skills you're missing."],
  ["Apply where it's posted", "Open the exact application page on the employer's site or job board, then track it on your board."],
];

const CAMPUS = [
  ["Bulk-import students", "From a spreadsheet, with invite codes for self sign-up"],
  ["Eligibility with reasons", "CGPA, branch, backlogs and batch checked for every drive"],
  ["Ranked, explainable shortlists", "Blind mode hides names; every change is audit-logged"],
];

const fmt = (n: number) => n.toLocaleString("en-IN");

function HeroSearch() {
  const navigate = useNavigate();
  const [role, setRole] = useState("");
  const [location, setLocation] = useState("");
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const q = new URLSearchParams();
    if (role.trim()) q.set("role", role.trim());
    if (location.trim()) q.set("location", location.trim());
    navigate(`/jobs${q.toString() ? `?${q}` : ""}`);
  };
  return (
    <form onSubmit={submit} className="flex flex-col gap-2 rounded-xl bg-white p-2 shadow-lg sm:flex-row" role="search" aria-label="Search jobs">
      <label className="relative flex-1">
        <span className="sr-only">Role or keyword</span>
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" aria-hidden />
        <input className="h-11 w-full rounded-lg pl-9 pr-3 text-sm text-slate-900 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-brand-200" placeholder="Role, skill or company" value={role} onChange={(e) => setRole(e.target.value)} />
      </label>
      <label className="relative sm:w-48">
        <span className="sr-only">Location</span>
        <MapPin className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" aria-hidden />
        <input className="h-11 w-full rounded-lg pl-9 pr-3 text-sm text-slate-900 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-brand-200 sm:border-l sm:border-slate-200 sm:rounded-l-none" placeholder="City or country" value={location} onChange={(e) => setLocation(e.target.value)} />
      </label>
      <button type="submit" className="btn-primary h-11 px-6">Search jobs</button>
    </form>
  );
}

/** A worked example of the match view, built from the components the app uses. */
function MatchPreview() {
  return (
    <div className="card relative p-5 text-slate-900 shadow-2xl shadow-black/40 sm:p-6 dark:text-slate-100" aria-label="Example of a job match">
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

const SHORTLIST: [string, string, string, number | null, string][] = [
  ["21CS045", "CSE", "8.9", 91, "Shortlisted"],
  ["21IT012", "IT", "8.4", 87, "Shortlisted"],
  ["21CS101", "CSE", "7.9", 84, "Applied"],
  ["21EC033", "ECE", "8.1", 78, "Applied"],
  ["21ME007", "ME", "7.2", null, "Not eligible: branch"],
];

/** An example of the TPO's ranked, blind shortlist, drawn like the real drive page. */
function ShortlistPreview() {
  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200 bg-slate-50 shadow-xl shadow-slate-900/10 dark:border-slate-800 dark:bg-slate-950" aria-label="Example of a campus drive shortlist">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 bg-ink-950 px-5 py-4 text-white dark:border-slate-800">
        <div>
          <p className="text-xs text-slate-400">Campus drive · example</p>
          <p className="font-semibold">Kaveri Systems: Software Engineer</p>
        </div>
        <p className="text-sm text-slate-300">12 LPA · Bengaluru</p>
      </div>
      <dl className="grid grid-cols-3 divide-x divide-slate-200 border-b border-slate-200 bg-white dark:divide-slate-800 dark:border-slate-800 dark:bg-slate-900">
        {[["Eligible", "142"], ["Applied", "96"], ["Shortlisted", "24"]].map(([l, v]) => (
          <div key={l} className="px-5 py-3">
            <dt className="text-xs muted">{l}</dt>
            <dd className="text-xl font-semibold tabular-nums">{v}</dd>
          </div>
        ))}
      </dl>
      <table className="w-full text-sm">
        <caption className="sr-only">Ranked shortlist, names hidden</caption>
        <thead>
          <tr className="text-left text-xs muted">
            <th className="px-5 py-2 font-medium">Roll no.</th>
            <th className="px-2 py-2 font-medium">Branch</th>
            <th className="px-2 py-2 text-right font-medium">CGPA</th>
            <th className="px-2 py-2 text-right font-medium">Match</th>
            <th className="px-5 py-2 font-medium">Stage</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-200 bg-white dark:divide-slate-800 dark:bg-slate-900">
          {SHORTLIST.map(([roll, br, cg, m, stage]) => (
            <tr key={roll} className={m === null ? "text-slate-400" : ""}>
              <td className="px-5 py-2.5 font-mono text-xs">{roll}</td>
              <td className="px-2 py-2.5">{br}</td>
              <td className="px-2 py-2.5 text-right tabular-nums">{cg}</td>
              <td className="px-2 py-2.5 text-right font-medium tabular-nums">{m === null ? "–" : `${m}%`}</td>
              <td className="px-5 py-2.5">
                {stage === "Shortlisted" ? <Chip tone="green">{stage}</Chip> : m === null ? <span className="text-xs">{stage}</span> : <Chip>{stage}</Chip>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="border-t border-slate-200 px-5 py-3 text-xs muted dark:border-slate-800">Blind mode on: names hidden, ranked by skill match</p>
    </div>
  );
}

export function LandingPage() {
  const stats = useQuery({ queryKey: ["jobs", "stats"], queryFn: api.jobStats, staleTime: 300_000 });
  const s = stats.data;
  const { hash } = useLocation();
  useEffect(() => {
    if (hash) document.getElementById(hash.slice(1))?.scrollIntoView({ behavior: "smooth" });
  }, [hash]);
  return (
    <div>
      {/* Hero: continues the ink header */}
      <section className="bg-ink-950 text-white">
        <div className="mx-auto grid w-full max-w-7xl items-center gap-12 px-4 pb-20 pt-12 sm:px-6 lg:grid-cols-[1fr_minmax(0,26rem)] lg:pb-24 lg:pt-20">
          <div className="animate-enter">
            {s && (
              <p className="inline-flex items-center gap-2 rounded-full border border-white/15 px-3 py-1 text-sm text-slate-300">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" aria-hidden />
                <span className="tabular-nums">{fmt(s.total)}</span> open jobs from {fmt(s.companies)} companies
              </p>
            )}
            <h1 className="mt-6 max-w-2xl text-4xl font-semibold leading-tight sm:text-5xl sm:leading-tight">
              Jobs from across the web, <span className="text-brand-500">ranked by your skills</span>
            </h1>
            <p className="mt-4 max-w-xl text-lg text-slate-300">
              HireX brings openings from company career sites and job boards into one place, reads your resume and shows
              which jobs you actually fit, and why.
            </p>
            <div className="mt-8 max-w-2xl">
              <HeroSearch />
            </div>
            <div className="mt-4 flex flex-wrap items-center gap-2 text-sm">
              <span className="text-slate-400">Popular</span>
              {POPULAR.map(([label, q]) => (
                <Link key={label} to={`/jobs?${new URLSearchParams(q)}`} className="rounded-full border border-white/15 px-3 py-1 text-slate-200 transition-colors hover:border-white/40 hover:text-white">
                  {label}
                </Link>
              ))}
            </div>
            <a href="#colleges" className="mt-8 inline-flex items-center gap-2 text-sm text-slate-300 hover:text-white">
              <GraduationCap className="h-4 w-4 text-brand-500" aria-hidden />
              Placement officer? Run your campus drives on HireX
              <ArrowRight className="h-4 w-4" aria-hidden />
            </a>
          </div>
          <div className="lg:translate-y-6">
            <MatchPreview />
          </div>
        </div>
      </section>

      {/* Placement officers: the second audience, shown right after the hero */}
      <section id="colleges" aria-labelledby="colleges-h" className="scroll-mt-16 border-b border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
        <div className="mx-auto grid w-full max-w-7xl items-center gap-12 px-4 py-16 sm:px-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)] lg:py-20">
          <div>
            <p className="inline-flex items-center gap-2 rounded-full bg-brand-50 px-3 py-1 text-sm font-medium text-brand-700 dark:bg-brand-500/15 dark:text-brand-200">
              <GraduationCap className="h-4 w-4" aria-hidden />
              For placement officers (TPO)
            </p>
            <h2 id="colleges-h" className="mt-4 text-3xl font-semibold leading-tight sm:text-4xl sm:leading-tight">
              Run every campus drive from one dashboard
            </h2>
            <p className="mt-4 max-w-xl text-lg muted">
              Import your students, set the eligibility rules, and get a ranked, explainable shortlist for each company,
              then track rounds and offers until students accept.
            </p>
            <dl className="mt-8 grid gap-6 sm:grid-cols-3">
              {CAMPUS.map(([t, d]) => (
                <div key={t} className="border-t-2 border-brand-500 pt-3">
                  <dt className="text-sm font-semibold">{t}</dt>
                  <dd className="mt-1 text-sm muted">{d}</dd>
                </div>
              ))}
            </dl>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link to="/register" className="btn-primary h-11 px-6 text-base">Set up your placement office</Link>
              <a href="#how-h" className="btn-secondary h-11 px-6 text-base">How it works</a>
            </div>
          </div>
          <ShortlistPreview />
        </div>
      </section>

      {/* Live numbers and where they come from */}
      <section aria-labelledby="sources-h" className="border-b border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
        <div className="mx-auto grid w-full max-w-7xl gap-8 px-4 py-10 sm:px-6 lg:grid-cols-[1fr_1.4fr]">
          <dl className="grid grid-cols-2 gap-6 sm:grid-cols-4 lg:grid-cols-2">
            {[
              ["Open jobs", s?.total],
              ["In India", s?.india],
              ["Remote", s?.remote],
              ["Internships", s?.internships],
            ].map(([label, v]) => (
              <div key={label as string}>
                <dt className="text-sm muted">{label}</dt>
                <dd className="mt-1 text-2xl font-semibold tabular-nums">{v === undefined ? "–" : fmt(v as number)}</dd>
              </div>
            ))}
          </dl>
          <div>
            <h2 id="sources-h" className="section-title">Where the jobs come from</h2>
            <p className="mt-1 text-sm muted">
              Official APIs only. LinkedIn, Naukri and Indeed listings arrive through Google for Jobs, and you can import any
              listing or alert email yourself.
            </p>
            <ul className="mt-4 grid gap-2 sm:grid-cols-2">
              {(s?.by_source ?? []).map((b) => (
                <li key={b.source} className="flex items-center justify-between rounded-lg border border-slate-200 px-3 py-2 text-sm dark:border-slate-800">
                  <span>{["greenhouse", "lever", "ashby"].includes(b.source) ? `Company career sites (${SOURCE_LABELS[b.source]})` : SOURCE_LABELS[b.source] ?? b.source}</span>
                  <span className="tabular-nums muted">{fmt(b.count)}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      {/* How it works */}
      <section aria-labelledby="how-h" className="mx-auto w-full max-w-7xl px-4 py-16 sm:px-6">
        <h2 id="how-h" className="text-2xl font-semibold">How it works</h2>
        <ol className="mt-8 grid gap-8 md:grid-cols-3">
          {STEPS.map(([t, d], i) => (
            <li key={t} className="border-t-2 border-slate-900 pt-4 dark:border-slate-100">
              <span className="font-mono text-sm text-brand-600 dark:text-brand-300">0{i + 1}</span>
              <h3 className="mt-2 text-lg font-semibold">{t}</h3>
              <p className="mt-2 text-sm muted">{d}</p>
            </li>
          ))}
        </ol>
        <div className="mt-10 flex flex-wrap gap-3">
          <Link to="/register" className="btn-primary h-10 px-5">Create a free account</Link>
          <Link to="/jobs" className="btn-secondary h-10 px-5">Browse all jobs <ArrowRight className="h-4 w-4" aria-hidden /></Link>
        </div>
      </section>

    </div>
  );
}
