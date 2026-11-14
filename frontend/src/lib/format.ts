export function timeAgo(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return "Date not listed";
  const then = new Date(iso);
  const days = Math.floor((now.getTime() - then.getTime()) / 86_400_000);
  if (days <= 0) return "Today";
  if (days === 1) return "1 day ago";
  if (days < 30) return `${days} days ago`;
  const months = Math.floor(days / 30);
  if (months < 12) return months === 1 ? "1 month ago" : `${months} months ago`;
  return "Over a year ago";
}

export function experienceLabel(min: number | null, max: number | null): string | null {
  if (min === null && max === null) return null;
  if (min !== null && max !== null) return min === max ? `${min} yrs` : `${min}-${max} yrs`;
  if (min !== null) return min === 0 ? "Entry level" : `${min}+ yrs`;
  return `Up to ${max} yrs`;
}

export function jobTypeLabel(t: string): string {
  return { internship: "Internship", "full-time": "Full-time", contract: "Contract", "part-time": "Part-time" }[t] ?? t;
}

export const SOURCE_LABELS: Record<string, string> = {
  greenhouse: "Greenhouse",
  lever: "Lever",
  ashby: "Ashby",
  remotive: "Remotive",
  adzuna: "Adzuna",
  jooble: "Jooble",
  jsearch: "Google Jobs",
  serpapi: "Google Jobs",
  import: "Imported",
};

export function pct(x: number): string {
  return `${Math.round(x * 100)}%`;
}

export function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}
