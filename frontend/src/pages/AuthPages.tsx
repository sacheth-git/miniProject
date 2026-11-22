import { useState, type FormEvent, type InputHTMLAttributes, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { ArrowRight, Briefcase, Building2, Eye, EyeOff, GraduationCap, Lock, Mail, UserRound } from "lucide-react";
import { api } from "../lib/api";
import { homeFor, useAuth } from "../lib/auth";
import { ErrorNote } from "../components/ui";
import { AuthBackdrop } from "../components/AuthBackdrop";

const fmt = (n: number) => n.toLocaleString("en-IN");

/** Split screen: live matching backdrop with real job counts on the left, the form on the right.
 *  On phones the backdrop runs behind the form card. */
function AuthLayout({ children }: { children: ReactNode }) {
  const stats = useQuery({ queryKey: ["jobs", "stats"], queryFn: api.jobStats, staleTime: 300_000 });
  const s = stats.data;
  return (
    <div className="relative grid min-h-[calc(100vh-3.5rem)] overflow-hidden bg-ink-950 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
      <AuthBackdrop />
      <div className="relative hidden flex-col justify-center p-12 text-white lg:flex">
        <div className="max-w-md rounded-2xl bg-ink-950/70 p-6 backdrop-blur-sm">
          <h2 className="text-3xl font-semibold leading-tight">Your skills, matched to real jobs</h2>
          <p className="mt-3 text-slate-300">
            Every opening from company career sites and job boards, ranked by how well you fit and explained skill by skill.
          </p>
          {s && (
            <dl className="mt-6 grid grid-cols-3 gap-4 border-t border-white/10 pt-5">
              {[["Open jobs", s.total], ["Companies", s.companies], ["In India", s.india]].map(([l, v]) => (
                <div key={l as string}>
                  <dt className="text-xs text-slate-400">{l}</dt>
                  <dd className="mt-1 text-xl font-semibold tabular-nums">{fmt(v as number)}</dd>
                </div>
              ))}
            </dl>
          )}
        </div>
      </div>
      <div className="relative flex items-center justify-center px-4 py-10 sm:px-8">
        <div className="w-full max-w-md animate-enter">{children}</div>
      </div>
    </div>
  );
}

function Shell({ title, subtitle, children }: { title: string; subtitle?: ReactNode; children: ReactNode }) {
  return (
    <AuthLayout>
      <div className="card p-6 shadow-2xl shadow-black/40 sm:p-8">
        <h1 className="text-2xl font-semibold">{title}</h1>
        {subtitle && <p className="mt-1 text-sm muted">{subtitle}</p>}
        <div className="mt-6">{children}</div>
      </div>
    </AuthLayout>
  );
}

/** Text input with a leading icon; password fields get a show/hide toggle. */
function Field({ id, label, icon, hint, type = "text", ...rest }: { id: string; label: string; icon: ReactNode; hint?: string } & InputHTMLAttributes<HTMLInputElement>) {
  const [show, setShow] = useState(false);
  const isPw = type === "password";
  return (
    <div>
      <label className="label" htmlFor={id}>{label}</label>
      <div className="relative">
        <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400">{icon}</span>
        <input id={id} type={isPw && show ? "text" : type} className={`input h-11 pl-10 ${isPw ? "pr-11" : ""}`} {...rest} />
        {isPw && (
          <button type="button" onClick={() => setShow((v) => !v)} aria-label={show ? "Hide password" : "Show password"}
            className="absolute right-1.5 top-1/2 grid h-8 w-8 -translate-y-1/2 place-items-center rounded-md text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-200">
            {show ? <EyeOff className="h-4 w-4" aria-hidden /> : <Eye className="h-4 w-4" aria-hidden />}
          </button>
        )}
      </div>
      {hint && <p className="mt-1 text-xs muted">{hint}</p>}
    </div>
  );
}

export function LoginPage() {
  const { login, user } = useAuth();
  const navigate = useNavigate();
  const from = (useLocation().state as { from?: string } | null)?.from;
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to={from ?? homeFor(user)} replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const u = await login(email, password);
      navigate(u.must_reset_password ? "/change-password" : (from ?? homeFor(u)), { replace: true });
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Shell title="Welcome back" subtitle={<>New to HireX? <Link to="/register" className="link">Create an account</Link></>}>
      <form onSubmit={submit} className="space-y-4">
        <Field id="email" label="Email" icon={<Mail className="h-4 w-4" />} type="email" autoComplete="email" required placeholder="you@example.com" value={email} onChange={(e) => setEmail(e.target.value)} />
        <Field id="password" label="Password" icon={<Lock className="h-4 w-4" />} type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
        {error !== null && <ErrorNote error={error} />}
        <button className="btn-primary h-11 w-full text-base" disabled={busy}>
          {busy ? "Signing in" : <>Sign in <ArrowRight className="h-4 w-4" aria-hidden /></>}
        </button>
      </form>
    </Shell>
  );
}

type Path = "seeker" | "student" | "tpo";

export function RegisterPage() {
  const { register, user } = useAuth();
  const navigate = useNavigate();
  const [path, setPath] = useState<Path | null>(null);
  const [f, setF] = useState({ full_name: "", email: "", password: "", invite_code: "", institution_name: "" });
  const [consent, setConsent] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to={homeFor(user)} replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const u = await register({
        email: f.email,
        password: f.password,
        full_name: f.full_name,
        role: path === "tpo" ? "tpo" : path === "student" ? "student" : "job_seeker",
        institution_name: path === "tpo" ? f.institution_name : undefined,
        invite_code: path === "student" ? f.invite_code.trim() : undefined,
        consent: path === "student" ? consent : undefined,
      });
      navigate(homeFor(u), { replace: true });
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  if (path === null) {
    const Option = ({ p, icon, title, text }: { p: Path; icon: ReactNode; title: string; text: string }) => (
      <button onClick={() => setPath(p)} className="group flex w-full items-start gap-3 rounded-xl border border-slate-200 p-4 text-left transition-colors hover:border-brand-500 hover:bg-brand-50/60 dark:border-slate-700 dark:hover:bg-brand-500/10">
        <span className="mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-brand-50 text-brand-600 dark:bg-brand-500/15 dark:text-brand-300">{icon}</span>
        <span>
          <span className="block font-medium">{title}</span>
          <span className="block text-sm muted">{text}</span>
        </span>
      </button>
    );
    return (
      <Shell title="Are you a campus student?" subtitle={<>Already have an account? <Link to="/login" className="link">Sign in</Link></>}>
        <div className="space-y-3">
          <Option p="student" icon={<GraduationCap className="h-5 w-5" />} title="Yes, I'm a student" text="Join your college with the invite code from your placement office. You also get every open-market job." />
          <Option p="seeker" icon={<Briefcase className="h-5 w-5" />} title="No, I'm looking for jobs on my own" text="Upload your resume and get ranked jobs and internships." />
        </div>
        <button className="mt-6 inline-flex items-center gap-1.5 text-sm link" onClick={() => setPath("tpo")}>
          <Building2 className="h-4 w-4" /> I'm a placement officer (TPO)
        </button>
      </Shell>
    );
  }

  const title = path === "student" ? "Join as a student" : path === "tpo" ? "Set up your placement office" : "Create your account";
  return (
    <Shell title={title} subtitle={<button className="link" onClick={() => setPath(null)}>Back</button>}>
      <form onSubmit={submit} className="space-y-4">
        <Field id="name" label="Full name" icon={<UserRound className="h-4 w-4" />} required autoComplete="name" value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} />
        <Field id="r-email" label="Email" icon={<Mail className="h-4 w-4" />} type="email" required autoComplete="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} />
        <Field id="r-pw" label="Password" icon={<Lock className="h-4 w-4" />} type="password" required minLength={8} autoComplete="new-password" hint="At least 8 characters, with a letter and a number" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} />
        {path === "tpo" && (
          <div>
            <label className="label" htmlFor="inst">Institution name</label>
            <input id="inst" required className="input" placeholder="e.g. Sahyadri Institute of Technology" value={f.institution_name} onChange={(e) => setF({ ...f, institution_name: e.target.value })} />
          </div>
        )}
        {path === "student" && (
          <>
            <div>
              <label className="label" htmlFor="invite">Invite code from your placement office</label>
              <input id="invite" required className="input uppercase" value={f.invite_code} onChange={(e) => setF({ ...f, invite_code: e.target.value })} />
            </div>
            <label className="flex items-start gap-2 rounded-md bg-slate-50 p-3 text-sm dark:bg-slate-800">
              <input type="checkbox" className="mt-1" checked={consent} onChange={(e) => setConsent(e.target.checked)} required />
              <span>
                I agree to share my profile, resume, academic details and campus applications with my college's placement office.
                I can withdraw this later in Settings.
              </span>
            </label>
          </>
        )}
        {error !== null && <ErrorNote error={error} />}
        <button className="btn-primary h-11 w-full text-base" disabled={busy || (path === "student" && !consent)}>
          {busy ? "Creating account" : "Create account"}
        </button>
      </form>
    </Shell>
  );
}

export function ChangePasswordPage() {
  const { acceptTokens, user } = useAuth();
  const navigate = useNavigate();
  const [cur, setCur] = useState("");
  const [next, setNext] = useState("");
  const [error, setError] = useState<unknown>(null);
  if (!user) return <Navigate to="/login" replace />;
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      const t = await api.changePassword(cur, next);
      acceptTokens(t);
      navigate(homeFor(t.user), { replace: true });
    } catch (err) {
      setError(err);
    }
  };
  return (
    <Shell title="Set a new password" subtitle={user.must_reset_password ? "Your account was created with a temporary password. Choose your own to continue." : undefined}>
      <form onSubmit={submit} className="space-y-4">
        <Field id="cur" label="Current password" icon={<Lock className="h-4 w-4" />} type="password" required value={cur} onChange={(e) => setCur(e.target.value)} autoComplete="current-password" />
        <Field id="new" label="New password" icon={<Lock className="h-4 w-4" />} type="password" required minLength={8} value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" />
        {error !== null && <ErrorNote error={error} />}
        <button className="btn-primary h-11 w-full text-base">Save password</button>
      </form>
    </Shell>
  );
}
