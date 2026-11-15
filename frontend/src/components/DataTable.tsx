import { useMemo, useState, type ReactNode } from "react";
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronLeft, ChevronRight } from "lucide-react";

export interface Column<T> {
  key: string;
  header: string;
  render?: (row: T) => ReactNode;
  sortValue?: (row: T) => string | number | null | undefined;
  align?: "left" | "right";
  className?: string;
  sortable?: boolean;
}

interface Props<T> {
  rows: T[];
  columns: Column<T>[];
  rowKey: (row: T) => string;
  caption: string;
  pageSize?: number;
  initialSort?: { key: string; dir: "asc" | "desc" };
  filter?: string;
  filterText?: (row: T) => string;
  onRowClick?: (row: T) => void;
  rowClassName?: (row: T) => string;
  empty?: ReactNode;
}

/** Sortable, paginated, keyboard-accessible table (sort buttons in headers with aria-sort). */
export function DataTable<T>({
  rows, columns, rowKey, caption, pageSize = 25, initialSort, filter, filterText, onRowClick, rowClassName, empty,
}: Props<T>) {
  const [sort, setSort] = useState(initialSort);
  const [page, setPage] = useState(0);

  const filtered = useMemo(() => {
    const q = filter?.trim().toLowerCase();
    if (!q || !filterText) return rows;
    return rows.filter((r) => filterText(r).toLowerCase().includes(q));
  }, [rows, filter, filterText]);

  const sorted = useMemo(() => {
    if (!sort) return filtered;
    const col = columns.find((c) => c.key === sort.key);
    if (!col) return filtered;
    const val = col.sortValue ?? ((r: T) => (r as Record<string, unknown>)[col.key] as string | number | null);
    const dir = sort.dir === "asc" ? 1 : -1;
    return [...filtered].sort((a, b) => {
      const x = val(a);
      const y = val(b);
      if (x === y) return 0;
      if (x === null || x === undefined) return 1; // blanks last either way
      if (y === null || y === undefined) return -1;
      return (x < y ? -1 : 1) * dir;
    });
  }, [filtered, sort, columns]);

  const pages = Math.max(1, Math.ceil(sorted.length / pageSize));
  const current = Math.min(page, pages - 1);
  const shown = sorted.slice(current * pageSize, current * pageSize + pageSize);

  const toggle = (key: string) => {
    setPage(0);
    setSort((s) => (s?.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: "asc" }));
  };

  return (
    <div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <caption className="sr-only">{caption}</caption>
          <thead className="bg-slate-50 text-left text-xs dark:bg-slate-900">
            <tr>
              {columns.map((c) => {
                const active = sort?.key === c.key;
                const ariaSort = active ? (sort!.dir === "asc" ? "ascending" : "descending") : "none";
                return (
                  <th key={c.key} scope="col" aria-sort={c.sortable === false ? undefined : ariaSort} className={`px-3 py-2 font-medium muted ${c.align === "right" ? "text-right" : ""}`}>
                    {c.sortable === false ? (
                      c.header
                    ) : (
                      <button className="inline-flex items-center gap-1 rounded hover:text-slate-900 focus-visible:outline-2 focus-visible:outline-brand-500 dark:hover:text-white" onClick={() => toggle(c.key)}>
                        {c.header}
                        {active ? sort!.dir === "asc" ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" /> : <ArrowUpDown className="h-3 w-3 opacity-40" />}
                      </button>
                    )}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {shown.map((r) => (
              <tr
                key={rowKey(r)}
                className={`${onRowClick ? "cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800/50" : ""} ${rowClassName?.(r) ?? ""}`}
                onClick={onRowClick ? () => onRowClick(r) : undefined}
              >
                {columns.map((c) => (
                  <td key={c.key} className={`px-3 py-2 align-top ${c.align === "right" ? "text-right tabular-nums" : ""} ${c.className ?? ""}`}>
                    {c.render ? c.render(r) : String((r as Record<string, unknown>)[c.key] ?? "-")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {sorted.length === 0 && <div className="p-6 text-center text-sm muted">{empty ?? "Nothing to show"}</div>}
      </div>
      {sorted.length > pageSize && (
        <nav className="flex items-center justify-between border-t border-slate-200 px-3 py-2 text-xs dark:border-slate-800" aria-label={`${caption} pages`}>
          <span className="muted">
            {current * pageSize + 1}-{Math.min(sorted.length, (current + 1) * pageSize)} of {sorted.length}
          </span>
          <span className="flex gap-1">
            <button className="btn-ghost p-1" onClick={() => setPage(current - 1)} disabled={current === 0} aria-label="Previous page">
              <ChevronLeft className="h-4 w-4" />
            </button>
            <span className="px-2 py-1">Page {current + 1} of {pages}</span>
            <button className="btn-ghost p-1" onClick={() => setPage(current + 1)} disabled={current >= pages - 1} aria-label="Next page">
              <ChevronRight className="h-4 w-4" />
            </button>
          </span>
        </nav>
      )}
    </div>
  );
}
