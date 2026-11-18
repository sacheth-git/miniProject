import { useState, type FormEvent, type ReactNode } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { GraduationCap, Briefcase, Building2 } from "lucide-react";
import { api } from "../lib/api";
import { homeFor, useAuth } from "../lib/auth";
import { ErrorNote } from "../components/ui";

function Shell({ title, subtitle, children }: { title: string; subtitle?: ReactNode; children: ReactNode }) {
  return (
    <div className="mx-auto flex max-w-md flex-col px-4 py-10 sm:py-16">
      <h1 className="text-2xl font-semibold">{title}</h1>
      {subtitle && <p className="mt-1 text-sm muted">{subtitle}</p>}
      <div className="card mt-6 p-6">{children}</div>
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
    <Shell title="Sign in" subtitle={<>New to SkillMatch? <Link to="/register" className="link">Create an account</Link></>}>
      <form onSubmit={submit} className="space-y-4">
        <div>
          <label className="label" htmlFor="email">Email</label>
          <input id="email" type="email" autoComplete="email" required className="input" value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div>
          <label className="label" htmlFor="password">Password</label>
          <input id="password" type="password" autoComplete="current-password" required className="input" value={password} onChange={(e) => setPassword(e.target.value)} />
        </div>
        {error !== null && <ErrorNote error={error} />}
        <button className="btn-primary w-full" disabled={busy}>{busy ? "Signing in" : "Sign in"}</button>
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
      <button onClick={() => setPath(p)} className="card flex w-full items-start gap-3 p-4 text-left hover:border-brand-500">
        <span className="mt-0.5 text-brand-600">{icon}</span>
        <span>
          <span className="block font-medium">{title}</span>
          <span className="block text-sm muted">{text}</span>
        </span>
      </button>
    );
    return (
      <div className="mx-auto max-w-md px-4 py-10 sm:py-16">
        <h1 className="text-2xl font-semibold">Are you a campus student?</h1>
        <p className="mt-1 text-sm muted">
          Already have an account? <Link to="/login" className="link">Sign in</Link>
        </p>
        <div className="mt-6 space-y-3">
          <Option p="student" icon={<GraduationCap className="h-5 w-5" />} title="Yes, I'm a student" text="Join your college with the invite code from your placement office. You also get every open-market job." />
          <Option p="seeker" icon={<Briefcase className="h-5 w-5" />} title="No, I'm looking for jobs on my own" text="Upload your resume and get ranked jobs and internships." />
        </div>
        <button className="mt-6 inline-flex items-center gap-1.5 text-sm link" onClick={() => setPath("tpo")}>
          <Building2 className="h-4 w-4" /> I'm a placement officer (TPO)
        </button>
      </div>
    );
  }

  const title = path === "student" ? "Join as a student" : path === "tpo" ? "Set up your placement office" : "Create your account";
  return (
    <Shell title={title} subtitle={<button className="link" onClick={() => setPath(null)}>Back</button>}>
      <form onSubmit={submit} className="space-y-4">
        <div>
          <label className="label" htmlFor="name">Full name</label>
          <input id="name" required autoComplete="name" className="input" value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} />
        </div>
        <div>
          <label className="label" htmlFor="r-email">Email</label>
          <input id="r-email" type="email" required autoComplete="email" className="input" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} />
        </div>
        <div>
          <label className="label" htmlFor="r-pw">Password</label>
          <input id="r-pw" type="password" required minLength={8} autoComplete="new-password" className="input" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} />
          <p className="mt-1 text-xs muted">At least 8 characters, with a letter and a number.</p>
        </div>
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
        <button className="btn-primary w-full" disabled={busy || (path === "student" && !consent)}>
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
        <div>
          <label className="label" htmlFor="cur">Current password</label>
          <input id="cur" type="password" required className="input" value={cur} onChange={(e) => setCur(e.target.value)} autoComplete="current-password" />
        </div>
        <div>
          <label className="label" htmlFor="new">New password</label>
          <input id="new" type="password" required minLength={8} className="input" value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" />
        </div>
        {error !== null && <ErrorNote error={error} />}
        <button className="btn-primary w-full">Save password</button>
      </form>
    </Shell>
  );
}
