import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { analytics } from "../../lib/tpo";
import { ChartCard, HBars, SimpleTable, StatTile } from "../../components/charts";
import { ErrorNote, Spinner } from "../../components/ui";

const lpa = (x: number | null) => (x === null ? "-" : `${x} LPA`);

export function DashboardPage() {
  const q = useQuery({ queryKey: ["tpo", "summary"], queryFn: analytics.summary });
  if (q.isLoading) return <div className="p-8"><Spinner label="Loading placement numbers" /></div>;
  if (q.error) return <div className="mx-auto max-w-3xl p-8"><ErrorNote error={q.error} /></div>;
  const s = q.data!;
  const f = s.funnel.total;
  const funnel = [
    { label: "Eligible", value: f.eligible },
    { label: "Applied", value: f.applied },
    { label: "Shortlisted", value: f.shortlisted },
    { label: "Offered", value: f.offered },
    { label: "Accepted", value: f.accepted },
  ];
  return (
    <div className="mx-auto max-w-7xl space-y-5 px-4 py-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Placement dashboard</h1>
        <Link to="/tpo/analytics" className="text-sm text-brand-600 hover:underline">Skill gaps, fairness and unplaced students</Link>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <StatTile label="Placed" value={`${s.placed_pct}%`} hint={`${s.placed} of ${s.students} students accepted an offer`} />
        <StatTile label="Holding an offer" value={s.offered} hint="Offer made, not yet accepted" />
        <StatTile label="Highest CTC" value={lpa(s.ctc.highest)} hint={`${s.ctc.count} accepted offers`} />
        <StatTile label="Median CTC" value={lpa(s.ctc.median)} />
        <StatTile label="Average CTC" value={lpa(s.ctc.average)} hint={`${s.drives.open} open of ${s.drives.total} drives`} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <ChartCard
          title="Placed by branch"
          subtitle="Share of students who accepted an offer"
          chart={<HBars data={s.by_branch.map((r) => ({ label: String(r.branch), value: r.placed_pct, detail: `${r.placed} of ${r.students}` }))} unit="%" max={100} />}
          table={<SimpleTable head={["Branch", "Students", "Placed", "Holding offer", "Placed %"]} rows={s.by_branch.map((r) => [String(r.branch), r.students, r.placed, r.offered, `${r.placed_pct}%`])} />}
        />
        <ChartCard
          title="Placement funnel"
          subtitle="All drives this season"
          chart={<HBars data={funnel} />}
          table={<SimpleTable head={["Stage", "Students"]} rows={funnel.map((x) => [x.label, x.value])} />}
        />
        <ChartCard
          title="Offers by company"
          subtitle="Offers made (accepted in brackets)"
          chart={<HBars data={s.companies.map((c) => ({ label: c.company, value: c.offers, detail: `${c.accepted} accepted, avg ${c.avg_ctc} LPA` }))} />}
          table={<SimpleTable head={["Company", "Offers", "Accepted", "Avg CTC"]} rows={s.companies.map((c) => [c.company, c.offers, c.accepted, `${c.avg_ctc} LPA`])} />}
        />
        <ChartCard
          title="Placed by batch"
          chart={<HBars data={s.by_batch.map((r) => ({ label: String(r.batch_year), value: r.placed_pct, detail: `${r.placed} of ${r.students}` }))} unit="%" max={100} />}
          table={<SimpleTable head={["Batch", "Students", "Placed", "Placed %"]} rows={s.by_batch.map((r) => [String(r.batch_year), r.students, r.placed, `${r.placed_pct}%`])} />}
        />
      </div>

      <section className="card overflow-hidden" aria-labelledby="df-h">
        <h2 id="df-h" className="border-b border-slate-200 px-4 py-3 text-sm font-semibold dark:border-slate-800">Funnel by drive</h2>
        <div className="overflow-x-auto px-4 py-2">
          <SimpleTable head={["Drive", "Eligible", "Applied", "Shortlisted", "Offered", "Accepted"]}
            rows={s.funnel.drives.map((d) => [`${d.company}: ${d.role}`, d.eligible, d.applied, d.shortlisted, d.offered, d.accepted])} />
        </div>
      </section>
    </div>
  );
}
