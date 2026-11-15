import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Plus } from "lucide-react";
import { tpo, type Drive } from "../../lib/tpo";
import { DataTable, type Column } from "../../components/DataTable";
import { Chip, ErrorNote, Spinner } from "../../components/ui";

export const TYPE_LABEL: Record<Drive["job_type"], string> = { fte: "Full-time", internship: "Internship", "intern+ppo": "Internship + PPO" };
export const STATUS_TONE: Record<Drive["status"], "slate" | "green" | "amber" | "blue"> = { draft: "slate", open: "green", closed: "amber", completed: "blue" };

export function pay(d: Drive): string {
  const parts = [];
  if (d.ctc_lpa) parts.push(`${d.ctc_lpa} LPA`);
  if (d.stipend_month) parts.push(`Rs ${d.stipend_month.toLocaleString("en-IN")}/month`);
  return parts.join(" · ") || "-";
}

export function DrivesPage() {
  const drives = useQuery({ queryKey: ["tpo", "drives"], queryFn: tpo.drives });
  const cols: Column<Drive>[] = [
    { key: "company", header: "Company", render: (d) => <Link to={`/tpo/drives/${d.id}`} className="font-medium text-brand-700 hover:underline dark:text-brand-200">{d.company}</Link> },
    { key: "role", header: "Role" },
    { key: "job_type", header: "Type", render: (d) => TYPE_LABEL[d.job_type] },
    { key: "ctc_lpa", header: "Pay", align: "right", render: pay },
    { key: "category", header: "Category", render: (d) => (d.category === "dream" ? <Chip tone="blue">Dream</Chip> : "Regular") },
    { key: "status", header: "Status", render: (d) => <Chip tone={STATUS_TONE[d.status]}>{d.status}</Chip> },
    { key: "deadline", header: "Deadline", render: (d) => (d.deadline ? new Date(d.deadline).toLocaleDateString() : "-") },
    { key: "applied", header: "Applied", align: "right", sortValue: (d) => d.counts.applied ?? 0, render: (d) => d.counts.applied ?? 0 },
    { key: "shortlisted", header: "Shortlisted", align: "right", sortValue: (d) => d.counts.shortlisted ?? 0, render: (d) => d.counts.shortlisted ?? 0 },
  ];
  return (
    <div className="mx-auto max-w-7xl space-y-6 px-4 py-8">
      <div className="flex items-end justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">Campus drives</h1>
        <Link to="/tpo/drives/new" className="btn-primary"><Plus className="h-4 w-4" aria-hidden /> New drive</Link>
      </div>
      <section className="card overflow-hidden">
        {drives.isLoading && <div className="p-5"><Spinner /></div>}
        {drives.error && <div className="p-5"><ErrorNote error={drives.error} /></div>}
        {drives.data && <DataTable caption="Campus drives" rows={drives.data} columns={cols} rowKey={(d) => d.id} empty="No drives yet. Create your first one." />}
      </section>
    </div>
  );
}
