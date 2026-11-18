import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { Plus, Trash2 } from "lucide-react";
import { tpo, type DriveInput, type DriveSkill, type Rules } from "../../lib/tpo";
import { ErrorNote, PageLoading } from "../../components/ui";

const BRANCHES = ["CSE", "IT", "ECE", "EEE", "MECH", "CIVIL", "AIML", "ISE"];
const STEPS = ["Job description", "Skills", "Eligibility", "Rounds and dates"] as const;
const EMPTY_RULES: Rules = {
  allowed_branches: [], batch_years: [], min_cgpa: null, max_active_backlogs: null, max_history_backlogs: null,
  min_tenth: null, min_twelfth: null, custom_rules: [],
};
const BLANK: DriveInput = {
  company: "", role: "", job_type: "fte", jd_text: "", skills: [], ctc_lpa: null, stipend_month: null, location: "",
  rounds: ["Online test", "Technical interview", "HR interview"], deadline: null, status: "draft", category: "regular",
  rules: EMPTY_RULES,
};

const num = (v: string): number | null => (v.trim() === "" ? null : Number(v));

export function DriveEditorPage() {
  const { id } = useParams();
  const editing = !!id;
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [step, setStep] = useState(0);
  const [d, setD] = useState<DriveInput>(BLANK);
  const [jdFile, setJdFile] = useState<File | null>(null);
  const [newSkill, setNewSkill] = useState("");

  const existing = useQuery({ queryKey: ["tpo", "drive", id], queryFn: () => tpo.drive(id!), enabled: editing });
  useEffect(() => {
    if (existing.data) {
      const { id: _i, jd_filename: _f, created_at: _c, updated_at: _u, counts: _n, ...rest } = existing.data;
      setD(rest);
    }
  }, [existing.data]);

  const extract = useMutation({
    mutationFn: () => tpo.extractJd(jdFile, jdFile ? null : d.jd_text),
    onSuccess: (r) => {
      setD((x) => ({ ...x, jd_text: r.text, skills: r.skills }));
      setStep(1);
    },
  });
  const save = useMutation({
    mutationFn: async () => {
      const body = { ...d, deadline: d.deadline || null, location: d.location || null };
      // No skills chosen yet: let the server extract them from the JD.
      if (!editing) return tpo.createDrive(d.skills.length ? body : { ...body, skills: undefined });
      const { rules, ...rest } = body;
      await tpo.setRules(id!, rules);
      return tpo.updateDrive(id!, rest);
    },
    onSuccess: (saved) => {
      qc.invalidateQueries({ queryKey: ["tpo"] });
      navigate(`/tpo/drives/${saved.id}`);
    },
  });

  if (editing && existing.isLoading) return <PageLoading />;
  const set = (patch: Partial<DriveInput>) => setD((x) => ({ ...x, ...patch }));
  const setRules = (patch: Partial<Rules>) => setD((x) => ({ ...x, rules: { ...x.rules, ...patch } }));
  const setSkill = (i: number, patch: Partial<DriveSkill>) => set({ skills: d.skills.map((s, j) => (j === i ? { ...s, ...patch } : s)) });
  const canNext = step === 0 ? d.company.trim() && d.role.trim() : true;

  return (
    <div className="page-mid">
      <h1 className="text-2xl font-semibold">{editing ? `Edit ${d.company || "drive"}` : "New campus drive"}</h1>
      <ol className="mt-5 flex flex-wrap gap-2 text-sm" aria-label="Steps">
        {STEPS.map((s, i) => (
          <li key={s}>
            <button
              className={`rounded-full px-3 py-1 ${i === step ? "bg-brand-600 text-white" : "bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-300"}`}
              aria-current={i === step ? "step" : undefined}
              onClick={() => (i <= step || editing) && setStep(i)}
            >
              {i + 1}. {s}
            </button>
          </li>
        ))}
      </ol>

      <div className="card mt-5 space-y-4 p-5">
        {step === 0 && (
          <>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Company" id="company"><input id="company" className="input" required value={d.company} onChange={(e) => set({ company: e.target.value })} /></Field>
              <Field label="Role" id="role"><input id="role" className="input" required value={d.role} onChange={(e) => set({ role: e.target.value })} /></Field>
              <Field label="Type" id="jt">
                <select id="jt" className="input" value={d.job_type} onChange={(e) => set({ job_type: e.target.value as DriveInput["job_type"] })}>
                  <option value="fte">Full-time</option><option value="internship">Internship</option><option value="intern+ppo">Internship + PPO</option>
                </select>
              </Field>
              <Field label="Location" id="loc"><input id="loc" className="input" value={d.location ?? ""} onChange={(e) => set({ location: e.target.value })} /></Field>
              <Field label="CTC (lakh per annum)" id="ctc"><input id="ctc" type="number" step="0.1" min="0" className="input" value={d.ctc_lpa ?? ""} onChange={(e) => set({ ctc_lpa: num(e.target.value) })} /></Field>
              <Field label="Stipend (Rs per month, internships)" id="stip"><input id="stip" type="number" min="0" className="input" value={d.stipend_month ?? ""} onChange={(e) => set({ stipend_month: num(e.target.value) })} /></Field>
              <Field label="Category" id="cat">
                <select id="cat" className="input" value={d.category} onChange={(e) => set({ category: e.target.value as DriveInput["category"] })}>
                  <option value="regular">Regular</option><option value="dream">Dream (placed students may apply under the dream rule)</option>
                </select>
              </Field>
            </div>
            <Field label="Job description (paste it, or upload a PDF / text file below)" id="jd">
              <textarea id="jd" className="input min-h-56" value={d.jd_text} onChange={(e) => set({ jd_text: e.target.value })} />
            </Field>
            <input type="file" accept=".pdf,.txt,application/pdf,text/plain" aria-label="JD file" className="block text-sm" onChange={(e) => setJdFile(e.target.files?.[0] ?? null)} />
            <div className="flex gap-2">
              <button className="btn-primary" disabled={!canNext || (!jdFile && d.jd_text.trim().length < 30) || extract.isPending} onClick={() => extract.mutate()}>
                {extract.isPending ? "Reading JD" : "Extract skills"}
              </button>
              {editing && <button className="btn-secondary" onClick={() => setStep(1)}>Keep current skills</button>}
            </div>
            {extract.error && <ErrorNote error={extract.error} />}
          </>
        )}

        {step === 1 && (
          <>
            <p className="text-sm muted">
              We found these skills in the JD. Mark each as required or preferred and adjust its weight (default: required 1.0,
              preferred 0.5, scaled by how rare the skill is). Changes re-rank students immediately and are recorded in the audit log.
            </p>
            <table className="w-full text-sm">
              <caption className="sr-only">Drive skills</caption>
              <thead className="text-left text-xs muted"><tr><th className="py-1">Skill</th><th>Type</th><th>Weight</th><th /></tr></thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {d.skills.map((s, i) => (
                  <tr key={s.skill_id}>
                    <td className="py-1.5">{s.name}</td>
                    <td>
                      <select aria-label={`${s.name} type`} className="input w-auto py-1" value={s.type} onChange={(e) => setSkill(i, { type: e.target.value as DriveSkill["type"] })}>
                        <option value="required">Required</option><option value="preferred">Preferred</option>
                      </select>
                    </td>
                    <td className="flex items-center gap-2 py-1.5">
                      <input aria-label={`${s.name} weight`} type="range" min={0} max={2} step={0.05} value={s.weight} onChange={(e) => setSkill(i, { weight: Number(e.target.value) })} />
                      <span className="w-10 tabular-nums">{s.weight.toFixed(2)}</span>
                    </td>
                    <td><button className="btn-ghost h-8 w-8 p-0" aria-label={`Remove ${s.name}`} onClick={() => set({ skills: d.skills.filter((_, j) => j !== i) })}><Trash2 className="h-4 w-4" /></button></td>
                  </tr>
                ))}
              </tbody>
            </table>
            <form className="flex max-w-sm gap-2" onSubmit={(e) => {
              e.preventDefault();
              const n = newSkill.trim();
              if (n) set({ skills: [...d.skills, { skill_id: n.toLowerCase().replace(/[^a-z0-9]+/g, "-"), name: n, type: "required", weight: 1 }] });
              setNewSkill("");
            }}>
              <input aria-label="Add skill" className="input" placeholder="Add a skill" value={newSkill} onChange={(e) => setNewSkill(e.target.value)} />
              <button className="btn-secondary"><Plus className="h-4 w-4" aria-hidden /> Add</button>
            </form>
          </>
        )}

        {step === 2 && (
          <>
            <fieldset>
              <legend className="label">Allowed branches (none ticked = all)</legend>
              <div className="flex flex-wrap gap-2">
                {BRANCHES.map((b) => {
                  const on = d.rules.allowed_branches.includes(b);
                  return (
                    <label key={b} className={`btn-secondary h-8 cursor-pointer ${on ? "border-brand-500 text-brand-700 dark:text-brand-200" : ""}`}>
                      <input type="checkbox" className="sr-only" checked={on} onChange={() => setRules({ allowed_branches: on ? d.rules.allowed_branches.filter((x) => x !== b) : [...d.rules.allowed_branches, b] })} />
                      {b}
                    </label>
                  );
                })}
              </div>
            </fieldset>
            <div className="grid gap-4 sm:grid-cols-3">
              <Field label="Batch years (comma-separated)" id="batches">
                <input id="batches" className="input" value={d.rules.batch_years.join(", ")} onChange={(e) => setRules({ batch_years: e.target.value.split(",").map((x) => parseInt(x.trim(), 10)).filter((x) => !Number.isNaN(x)) })} />
              </Field>
              <Field label="Minimum CGPA" id="cgpa"><input id="cgpa" type="number" step="0.01" min="0" max="10" className="input" value={d.rules.min_cgpa ?? ""} onChange={(e) => setRules({ min_cgpa: num(e.target.value) })} /></Field>
              <Field label="Max active backlogs" id="ab"><input id="ab" type="number" min="0" className="input" value={d.rules.max_active_backlogs ?? ""} onChange={(e) => setRules({ max_active_backlogs: num(e.target.value) })} /></Field>
              <Field label="Max backlog history" id="hb"><input id="hb" type="number" min="0" className="input" value={d.rules.max_history_backlogs ?? ""} onChange={(e) => setRules({ max_history_backlogs: num(e.target.value) })} /></Field>
              <Field label="Minimum 10th %" id="t10"><input id="t10" type="number" min="0" max="100" className="input" value={d.rules.min_tenth ?? ""} onChange={(e) => setRules({ min_tenth: num(e.target.value) })} /></Field>
              <Field label="Minimum 12th / diploma %" id="t12"><input id="t12" type="number" min="0" max="100" className="input" value={d.rules.min_twelfth ?? ""} onChange={(e) => setRules({ min_twelfth: num(e.target.value) })} /></Field>
            </div>
            <p className="text-xs muted">Placement policy (one-offer and dream rules) is applied on top of these rules. Gender is never a filter.</p>
          </>
        )}

        {step === 3 && (
          <>
            <Field label="Rounds, in order (one per line)" id="rounds">
              <textarea id="rounds" className="input min-h-28" value={d.rounds.join("\n")} onChange={(e) => set({ rounds: e.target.value.split("\n").map((x) => x.trim()).filter(Boolean) })} />
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Application deadline" id="dl">
                <input id="dl" type="datetime-local" className="input" value={d.deadline ? d.deadline.slice(0, 16) : ""} onChange={(e) => set({ deadline: e.target.value ? new Date(e.target.value).toISOString() : null })} />
              </Field>
              <Field label="Status" id="st">
                <select id="st" className="input" value={d.status} onChange={(e) => set({ status: e.target.value as DriveInput["status"] })}>
                  <option value="draft">Draft (not visible to students)</option><option value="open">Open</option><option value="closed">Closed</option><option value="completed">Completed</option>
                </select>
              </Field>
            </div>
          </>
        )}

        <div className="flex justify-between border-t border-slate-200 pt-4 dark:border-slate-800">
          <button className="btn-ghost" disabled={step === 0} onClick={() => setStep((s) => s - 1)}>Back</button>
          {step < STEPS.length - 1 ? (
            <button className="btn-primary" disabled={!canNext} onClick={() => setStep((s) => s + 1)}>Next</button>
          ) : (
            <button className="btn-primary" disabled={save.isPending || !d.company || !d.role} onClick={() => save.mutate()}>
              {save.isPending ? "Saving" : editing ? "Save changes" : "Create drive"}
            </button>
          )}
        </div>
        {save.error && <ErrorNote error={save.error} />}
      </div>
    </div>
  );
}

function Field({ label, id, children }: { label: string; id: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="label" htmlFor={id}>{label}</label>
      {children}
    </div>
  );
}
