import { useEffect, useState, type ReactNode } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

/** Reference palette (dataviz skill): one series = categorical slot 1, stepped per mode. */
const SERIES_1 = { light: "#2a78d6", dark: "#3987e5" };
const INK = {
  light: { primary: "#0b0b0b", secondary: "#52514e", grid: "#e4e3df", surface: "#fcfcfb" },
  dark: { primary: "#f0efec", secondary: "#c3c2b7", grid: "#34332f", surface: "#1a1a19" },
};
/** Sequential blue ramp 100 -> 700 (light = near zero). */
export const SEQ = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"];

export function useIsDark(): boolean {
  const [dark, setDark] = useState(() => document.documentElement.classList.contains("dark"));
  useEffect(() => {
    const obs = new MutationObserver(() => setDark(document.documentElement.classList.contains("dark")));
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => obs.disconnect();
  }, []);
  return dark;
}

export function useChartTheme() {
  const dark = useIsDark();
  return { series: dark ? SERIES_1.dark : SERIES_1.light, ink: dark ? INK.dark : INK.light };
}

/** A chart with an always-available table view (identity and values never depend on color alone). */
export function ChartCard({ title, subtitle, chart, table }: { title: string; subtitle?: string; chart: ReactNode; table: ReactNode }) {
  const [view, setView] = useState<"chart" | "table">("chart");
  return (
    <section className="card p-4" aria-label={title}>
      <header className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold">{title}</h2>
          {subtitle && <p className="text-xs muted">{subtitle}</p>}
        </div>
        <div role="tablist" aria-label={`${title} view`} className="flex rounded-md border border-slate-200 text-xs dark:border-slate-700">
          {(["chart", "table"] as const).map((v) => (
            <button key={v} role="tab" aria-selected={view === v} onClick={() => setView(v)}
              className={`px-2 py-1 ${view === v ? "bg-slate-100 font-medium dark:bg-slate-800" : "muted"}`}>
              {v === "chart" ? "Chart" : "Table"}
            </button>
          ))}
        </div>
      </header>
      <div className="mt-3">{view === "chart" ? chart : <div className="overflow-x-auto">{table}</div>}</div>
    </section>
  );
}

interface BarDatum {
  label: string;
  value: number;
  detail?: string;
}

/** Single-series horizontal bars: thin marks, 4px rounded data ends, recessive grid, hover tooltip. */
export function HBars({ data, unit = "", max }: { data: BarDatum[]; unit?: string; max?: number }) {
  const { series, ink } = useChartTheme();
  const height = Math.max(120, data.length * 34 + 30);
  return (
    <div style={{ height }} role="img" aria-label={data.map((d) => `${d.label}: ${d.value}${unit}`).join("; ")}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 48, bottom: 4, left: 8 }} barCategoryGap={8}>
          <CartesianGrid horizontal={false} stroke={ink.grid} />
          <XAxis type="number" domain={[0, max ?? "auto"]} tick={{ fill: ink.secondary, fontSize: 11 }} axisLine={false} tickLine={false} unit={unit} />
          <YAxis type="category" dataKey="label" width={130} tick={{ fill: ink.primary, fontSize: 12 }} axisLine={false} tickLine={false} />
          <Tooltip
            cursor={{ fill: ink.grid, opacity: 0.4 }}
            contentStyle={{ background: ink.surface, border: `1px solid ${ink.grid}`, borderRadius: 6, fontSize: 12, color: ink.primary }}
            formatter={(v: number, _n, p) => [`${v}${unit}${(p.payload as BarDatum).detail ? ` (${(p.payload as BarDatum).detail})` : ""}`, ""]}
            separator=""
          />
          <Bar dataKey="value" fill={series} radius={[0, 4, 4, 0]} maxBarSize={18}
            label={{ position: "right", fill: ink.secondary, fontSize: 11, formatter: (v: number) => `${v}${unit}` }} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function StatTile({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <div className="card p-4">
      <p className="text-xs muted">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
      {hint && <p className="mt-0.5 text-xs muted">{hint}</p>}
    </div>
  );
}

export function SimpleTable({ head, rows }: { head: string[]; rows: (string | number | null)[][] }) {
  return (
    <table className="w-full text-sm">
      <thead className="text-left text-xs muted">
        <tr>{head.map((h, i) => <th key={h} scope="col" className={`py-1 pr-3 font-medium ${i > 0 ? "text-right" : ""}`}>{h}</th>)}</tr>
      </thead>
      <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
        {rows.map((r, i) => (
          <tr key={i}>{r.map((c, j) => <td key={j} className={`py-1 pr-3 ${j > 0 ? "text-right tabular-nums" : ""}`}>{c ?? "-"}</td>)}</tr>
        ))}
      </tbody>
    </table>
  );
}
