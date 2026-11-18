import { useEffect, useRef, useState, type DragEvent, type FormEvent } from "react";
import { useMutation } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { Check, FileUp, Loader2, Plus, X } from "lucide-react";
import { api } from "../lib/api";
import { useCandidate } from "../lib/candidate";
import type { Candidate, Preferences, ProcessingStep } from "../lib/types";
import { Chip, ErrorNote } from "../components/ui";

const STEPS: { key: string; label: string }[] = [
  { key: "extract_text", label: "Reading your PDF" },
  { key: "detect_sections", label: "Finding sections" },
  { key: "mask_pii", label: "Hiding personal details" },
  { key: "extract_skills", label: "Extracting skills" },
  { key: "profile", label: "Estimating experience and education" },
];
const MAX_BYTES = 5 * 1024 * 1024;

export function UploadPage() {
  const { candidate } = useCandidate();
  const [replacing, setReplacing] = useState(false);
  return (
    <div className="page-mid">
      {!candidate || replacing ? (
        <Uploader onDone={() => setReplacing(false)} onCancel={candidate ? () => setReplacing(false) : undefined} />
      ) : (
        <Profile candidate={candidate} onReplace={() => setReplacing(true)} />
      )}
    </div>
  );
}

function Uploader({ onDone, onCancel }: { onDone: () => void; onCancel?: () => void }) {
  const { setCandidate } = useCandidate();
  const [biasAware, setBiasAware] = useState(true);
  const [dragging, setDragging] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const [result, setResult] = useState<Candidate | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const upload = useMutation({
    mutationFn: (file: File) => api.uploadResume(file, biasAware),
    onSuccess: (c) => setResult(c),
  });

  const pick = (file: File | undefined) => {
    setLocalError(null);
    if (!file) return;
    if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
      setLocalError("Please upload a PDF file.");
      return;
    }
    if (file.size > MAX_BYTES) {
      setLocalError("That file is larger than 5 MB.");
      return;
    }
    upload.mutate(file);
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    pick(e.dataTransfer.files[0]);
  };

  return (
    <div>
      <h1 className="text-2xl font-semibold">Find jobs that match your skills</h1>
      <p className="mt-2 max-w-2xl muted">
        Upload your resume once. We read your skills and experience, rank open roles and internships from employer career
        sites and job boards, and show you why each one fits.
      </p>

      {!upload.isPending && !result && (
        <>
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            className={`mt-6 flex flex-col items-center rounded-xl border-2 border-dashed px-6 py-14 text-center transition-colors ${
              dragging
                ? "border-brand-500 bg-brand-50 dark:bg-slate-900"
                : "border-slate-300 bg-white dark:border-slate-700 dark:bg-slate-900"
            }`}
          >
            <FileUp className="h-10 w-10 text-brand-600" aria-hidden />
            <p className="mt-3 font-medium">Drag your resume here</p>
            <p className="text-sm muted">PDF, up to 5 MB</p>
            <button className="btn-primary mt-4" onClick={() => inputRef.current?.click()}>
              Choose file
            </button>
            <input
              ref={inputRef}
              type="file"
              accept="application/pdf,.pdf"
              className="sr-only"
              aria-label="Resume PDF"
              onChange={(e) => pick(e.target.files?.[0])}
            />
          </div>
          <label className="mt-4 flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-1" checked={biasAware} onChange={(e) => setBiasAware(e.target.checked)} />
            <span>
              <span className="font-medium">Bias-aware matching</span>
              <span className="block muted">
                Your name, contact details, gender words and college name are hidden before matching. Recommended.
              </span>
            </span>
          </label>
          {onCancel && (
            <button className="btn-ghost mt-3" onClick={onCancel}>
              Keep my current resume
            </button>
          )}
        </>
      )}

      {(upload.isPending || result) && (
        <Steps done={result?.steps ?? null} onContinue={() => {
          if (result) setCandidate(result);
          onDone();
        }} />
      )}
      {localError && <div className="mt-4"><ErrorNote error={localError} /></div>}
      {upload.error && (
        <div className="mt-4 space-y-2">
          <ErrorNote error={upload.error} />
          <button className="btn-secondary" onClick={() => upload.reset()}>
            Try another file
          </button>
        </div>
      )}
    </div>
  );
}

/** While the upload runs, steps advance on a timer; real timings replace them when it finishes. */
function Steps({ done, onContinue }: { done: ProcessingStep[] | null; onContinue: () => void }) {
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (done) return;
    const t = setInterval(() => setTick((n) => Math.min(n + 1, STEPS.length - 1)), 700);
    return () => clearInterval(t);
  }, [done]);
  const timing = new Map(done?.map((s) => [s.name, s]) ?? []);

  return (
    <div className="card mt-6 p-5" aria-live="polite">
      <h2 className="font-semibold">{done ? "Your resume is ready" : "Processing your resume"}</h2>
      <ol className="mt-3 space-y-2">
        {STEPS.filter((s) => !done || timing.has(s.key)).map((s, i) => {
          const finished = done ? true : i < tick;
          const active = !done && i === tick;
          const t = timing.get(s.key);
          return (
            <li key={s.key} className="flex items-center gap-2 text-sm">
              {finished ? (
                <Check className="h-4 w-4 text-emerald-600" aria-hidden />
              ) : active ? (
                <Loader2 className="h-4 w-4 animate-spin text-brand-600" aria-hidden />
              ) : (
                <span className="h-4 w-4 rounded-full border border-slate-300 dark:border-slate-600" aria-hidden />
              )}
              <span className={finished || active ? "" : "muted"}>{s.label}</span>
              {t && <span className="ml-auto text-xs muted">{t.detail} · {Math.round(t.ms)} ms</span>}
            </li>
          );
        })}
      </ol>
      {done && (
        <button className="btn-primary mt-4" onClick={onContinue}>
          Review my profile
        </button>
      )}
    </div>
  );
}

function Profile({ candidate, onReplace }: { candidate: Candidate; onReplace: () => void }) {
  const navigate = useNavigate();
  const { setCandidate } = useCandidate();
  const [newSkill, setNewSkill] = useState("");
  const edit = useMutation({
    mutationFn: (v: { add: string[]; remove: string[] }) => api.editSkills(candidate.id, v.add, v.remove),
    onSuccess: setCandidate,
  });
  const p = candidate.preferences ?? {};
  const [prefs, setPrefs] = useState<Preferences>({
    target_role: p.target_role ?? "",
    locations: p.locations ?? [],
    remote_ok: p.remote_ok ?? true,
    job_types: p.job_types ?? [],
  });
  const [locText, setLocText] = useState((p.locations ?? []).join(", "));
  const savePrefs = useMutation({
    mutationFn: (pr: Preferences) => api.setPreferences(candidate.id, pr),
    onSuccess: (c) => {
      setCandidate(c);
      navigate("/jobs");
    },
  });

  const addSkill = (e: FormEvent) => {
    e.preventDefault();
    const s = newSkill.trim();
    if (s) edit.mutate({ add: [s], remove: [] });
    setNewSkill("");
  };
  const submitPrefs = (e: FormEvent) => {
    e.preventDefault();
    savePrefs.mutate({
      ...prefs,
      target_role: prefs.target_role?.trim() || null,
      locations: locText.split(",").map((s) => s.trim()).filter(Boolean),
    });
  };
  const toggleType = (t: string) =>
    setPrefs((pr) => ({ ...pr, job_types: pr.job_types.includes(t) ? pr.job_types.filter((x) => x !== t) : [...pr.job_types, t] }));

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Your profile</h1>
          <p className="mt-1 text-sm muted">
            From {candidate.filename ?? "your resume"} · {candidate.years_experience} years of experience ·{" "}
            {candidate.education_level === "unknown" ? "education not detected" : candidate.education_level.replace("_", " ")}
          </p>
        </div>
        <div className="flex gap-2">
          <button className="btn-secondary" onClick={onReplace}>
            Upload a new resume
          </button>
          <Link to="/jobs" className="btn-primary">
            See matching jobs
          </Link>
        </div>
      </div>

      <section className="card p-5" aria-labelledby="skills-h">
        <h2 id="skills-h" className="font-semibold">
          Skills we found <span className="font-normal muted">({candidate.skills.length})</span>
        </h2>
        <p className="mt-1 text-sm muted">Remove anything wrong and add what we missed. Your matches update right away.</p>
        <ul className="mt-3 flex flex-wrap gap-2">
          {candidate.skills.map((s) => (
            <li key={s.skill_id}>
              <span
                className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-slate-50 py-1 pl-3 pr-1 text-sm dark:border-slate-700 dark:bg-slate-800"
                title={s.evidence}
              >
                {s.name}
                {s.method === "user" && <span className="text-xs muted">added</span>}
                <button
                  className="rounded-full p-0.5 hover:bg-slate-200 dark:hover:bg-slate-700"
                  aria-label={`Remove ${s.name}`}
                  onClick={() => edit.mutate({ add: [], remove: [s.skill_id] })}
                  disabled={edit.isPending}
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </span>
            </li>
          ))}
        </ul>
        <form onSubmit={addSkill} className="mt-3 flex max-w-sm gap-2">
          <label htmlFor="add-skill" className="sr-only">
            Add a skill
          </label>
          <input id="add-skill" className="input" placeholder="Add a skill, e.g. Docker" value={newSkill} onChange={(e) => setNewSkill(e.target.value)} />
          <button className="btn-secondary" type="submit" disabled={edit.isPending}>
            <Plus className="h-4 w-4" aria-hidden />
            Add
          </button>
        </form>
        {edit.error && <div className="mt-2"><ErrorNote error={edit.error} /></div>}
      </section>

      <form onSubmit={submitPrefs} className="card space-y-4 p-5" aria-labelledby="prefs-h">
        <h2 id="prefs-h" className="font-semibold">
          What are you looking for?
        </h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="label" htmlFor="role">
              Target role
            </label>
            <input id="role" className="input" placeholder="e.g. Machine Learning Engineer" value={prefs.target_role ?? ""} onChange={(e) => setPrefs({ ...prefs, target_role: e.target.value })} />
          </div>
          <div>
            <label className="label" htmlFor="locs">
              Preferred locations
            </label>
            <input id="locs" className="input" placeholder="e.g. Bengaluru, Pune" value={locText} onChange={(e) => setLocText(e.target.value)} />
          </div>
        </div>
        <fieldset>
          <legend className="label">Job type</legend>
          <div className="flex flex-wrap gap-2">
            {["internship", "full-time", "contract"].map((t) => (
              <label key={t} className={`btn-secondary h-8 cursor-pointer ${prefs.job_types.includes(t) ? "border-brand-500 text-brand-700 dark:text-brand-200" : ""}`}>
                <input type="checkbox" className="sr-only" checked={prefs.job_types.includes(t)} onChange={() => toggleType(t)} />
                {t === "full-time" ? "Full-time" : t[0].toUpperCase() + t.slice(1)}
              </label>
            ))}
          </div>
        </fieldset>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={prefs.remote_ok} onChange={(e) => setPrefs({ ...prefs, remote_ok: e.target.checked })} />
          Open to remote roles
        </label>
        <div className="flex items-center gap-3">
          <button className="btn-primary" type="submit" disabled={savePrefs.isPending}>
            Save and see jobs
          </button>
          <span className="text-xs muted">Preferences tune the fit score; they don't hide jobs.</span>
        </div>
        {savePrefs.error && <ErrorNote error={savePrefs.error} />}
      </form>

      <section className="card p-5">
        <h2 className="font-semibold">How sure we are</h2>
        <p className="mt-1 text-sm muted">Hover a skill above to see the line in your resume it came from.</p>
        <div className="mt-3 flex flex-wrap gap-1.5">
          {candidate.skills.slice(0, 12).map((s) => (
            <Chip key={s.skill_id} tone={s.confidence >= 0.9 ? "green" : s.confidence >= 0.75 ? "blue" : "amber"} title={s.evidence}>
              {s.name} · {Math.round(s.confidence * 100)}%
            </Chip>
          ))}
        </div>
      </section>
    </div>
  );
}
