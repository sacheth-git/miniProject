import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ExternalLink } from "lucide-react";
import { api } from "../lib/api";
import { useCandidate } from "../lib/candidate";
import { EmptyState, ErrorNote, Spinner } from "../components/ui";

const ABOUT: Record<string, string> = {
  LinkedIn: "Large professional network. Some jobs use Easy Apply; others send you to the company site.",
  Naukri: "India's largest job board, strong for experienced and fresher roles alike.",
  Indeed: "Broad aggregator with many company and staffing-agency listings.",
};

export function ElsewherePage() {
  const { candidateId } = useCandidate();
  const q = useQuery({ queryKey: ["deeplinks", candidateId], queryFn: () => api.deeplinks(candidateId!), enabled: !!candidateId });

  if (!candidateId) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-8">
        <EmptyState title="Upload your resume first" action={<Link to="/" className="btn-primary">Upload resume</Link>}>
          We build searches for LinkedIn, Naukri and Indeed from your skills and target role.
        </EmptyState>
      </div>
    );
  }
  const platforms = ["LinkedIn", "Naukri", "Indeed"];
  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <h1 className="text-2xl font-semibold tracking-tight">Search other job sites</h1>
      <p className="mt-1 muted">
        These open each site's own search with your role and skills filled in. We don't copy listings from these sites.
        To see their jobs ranked here, import a listing or an alert email.
      </p>
      {q.isLoading && <div className="mt-6"><Spinner /></div>}
      {q.error && <div className="mt-6"><ErrorNote error={q.error} /></div>}
      {q.data && (
        <>
          <p className="mt-4 text-sm">
            Searching for <span className="font-medium">{q.data.role}</span>
            {q.data.location && <> in <span className="font-medium">{q.data.location}</span></>}
            {q.data.internship && <> (internships)</>}.{" "}
            <Link to="/" className="text-brand-600 hover:underline">Change target role or location</Link>
          </p>
          <div className="mt-5 grid gap-4 md:grid-cols-3">
            {platforms.map((p) => (
              <section key={p} className="card flex flex-col p-5">
                <h2 className="font-semibold">{p}</h2>
                <p className="mt-1 flex-1 text-sm muted">{ABOUT[p]}</p>
                <div className="mt-4 space-y-2">
                  {q.data.links
                    .filter((l) => l.platform === p)
                    .map((l) => (
                      <a key={l.url} href={l.url} target="_blank" rel="noopener noreferrer" className="btn-secondary w-full justify-between">
                        <span className="truncate">{l.label}</span>
                        <ExternalLink className="h-3.5 w-3.5 shrink-0" aria-hidden />
                      </a>
                    ))}
                </div>
              </section>
            ))}
          </div>
          <p className="mt-6 text-sm">
            Found something good? <Link to="/import" className="text-brand-600 hover:underline">Import it</Link> to see your match score and track it.
          </p>
        </>
      )}
    </div>
  );
}
