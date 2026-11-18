import { Bookmark, BookmarkCheck } from "lucide-react";
import { useCandidate } from "../lib/candidate";
import { useTracking } from "../lib/tracking";
import type { JobSummary } from "../lib/types";

export function SaveButton({ job, size = "md" }: { job: JobSummary; size?: "sm" | "md" }) {
  const { candidateId } = useCandidate();
  const { statusOf, track } = useTracking();
  const status = statusOf(job.id);
  const cls = size === "sm" ? "btn-secondary h-8 px-2.5 text-xs" : "btn-secondary";
  if (!candidateId) return null;
  if (status) {
    return (
      <span className={`${cls} cursor-default`} title="In your tracker">
        <BookmarkCheck className="h-3.5 w-3.5 text-brand-600" aria-hidden />
        {status}
      </span>
    );
  }
  return (
    <button className={cls} onClick={() => track(job, "Saved")}>
      <Bookmark className="h-3.5 w-3.5" aria-hidden />
      Save
    </button>
  );
}
