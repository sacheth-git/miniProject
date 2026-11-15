import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { ErrorNote, Spinner } from "../components/ui";

/** First sign-in for a student created by their placement office: explicit consent. */
export function ConsentPage() {
  const { refreshUser, logout } = useAuth();
  const navigate = useNavigate();
  const c = useQuery({ queryKey: ["consent"], queryFn: api.consent });
  const give = useMutation({
    mutationFn: api.giveConsent,
    onSuccess: async () => {
      await refreshUser();
      navigate("/", { replace: true });
    },
  });
  return (
    <div className="mx-auto max-w-lg px-4 py-12">
      <h1 className="text-2xl font-semibold tracking-tight">Share your profile with your placement office?</h1>
      {c.isLoading && <Spinner />}
      {c.data && (
        <div className="card mt-6 space-y-4 p-6">
          <p className="text-sm">
            {c.data.institution_name ?? "Your college"} created your account so you can take part in campus drives. If you agree, your
            placement office can see:
          </p>
          <ul className="list-disc space-y-1 pl-5 text-sm">
            <li>Name, email, roll number, branch and batch</li>
            <li>CGPA, backlogs, 10th / 12th / diploma marks</li>
            <li>Your resume, extracted skills and experience</li>
            <li>Your match score and skill gap for campus drives, and your drive applications</li>
          </ul>
          <p className="text-xs muted">
            Your scores are never shown to other students. You can withdraw consent any time in Settings; you will then be left out
            of campus shortlists. You can still use every open-market job feature either way.
          </p>
          <div className="flex gap-2">
            <button className="btn-primary" onClick={() => give.mutate()} disabled={give.isPending}>I agree</button>
            <button className="btn-secondary" onClick={() => logout().then(() => navigate("/"))}>Not now, sign out</button>
          </div>
          {give.error && <ErrorNote error={give.error} />}
        </div>
      )}
    </div>
  );
}
