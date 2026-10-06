import { api, type MarkingWork } from "@scorecode/api-client";
import { Badge, EmptyState, PageHeader, ProgressBar, Skeleton, formatDateTime } from "@scorecode/ui";
import { useQuery } from "@tanstack/react-query";
import { ClipboardCheck } from "lucide-react";
import { Link } from "react-router";

const SUBMISSION = {
  open: { label: "To do", tone: "info" },
  submitted: { label: "Submitted", tone: "success" },
  returned: { label: "Returned for changes", tone: "warning" },
  locked: { label: "Locked", tone: "neutral" },
} as const;

export const useMarking = () =>
  useQuery({ queryKey: ["marking"], queryFn: () => api.get<MarkingWork[]>("/api/v1/marking") });

export default function MarkingPage() {
  const q = useMarking();
  const items = q.data ?? [];
  const exams = [...new Set(items.map((i) => i.exam_id))];
  return (
    <>
      <PageHeader
        title="Marks entry"
        description="The papers you can enter marks for. Marks save as you type; submit each paper when it's complete."
      />
      {q.isPending ? (
        <div className="flex flex-col gap-3">
          {Array.from({ length: 3 }, (_, i) => (
            <Skeleton key={i} className="h-20" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-xl border border-border bg-surface">
          <EmptyState
            icon={<ClipboardCheck />}
            title="Nothing to mark right now"
            description="Papers appear here when an exam opens for marks entry and you're assigned to them."
          />
        </div>
      ) : (
        <div className="flex flex-col gap-6">
          {exams.map((examId) => {
            const rows = items.filter((i) => i.exam_id === examId);
            const first = rows[0]!;
            return (
              <section key={examId} aria-labelledby={`exam-${examId}`}>
                <h2 id={`exam-${examId}`} className="mb-2 text-[15px] font-semibold text-fg">
                  {first.exam_name}
                  {first.marks_deadline && (
                    <span className="ml-2 text-[13px] font-normal text-fg-subtle">
                      due {formatDateTime(first.marks_deadline)}
                    </span>
                  )}
                  {first.exam_status === "marks_entry_closed" && <Badge className="ml-2">Entry closed</Badge>}
                </h2>
                <ul className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                  {rows.map((w) => {
                    const sub = SUBMISSION[w.submission_status];
                    const pct = w.students ? Math.min(100, (w.entered / w.students) * 100) : 0;
                    return (
                      <li key={`${w.paper_id}:${w.cohort_id}`}>
                        <Link
                          to={`/marking/${w.exam_id}/${w.paper_id}/${w.cohort_id}`}
                          className="flex flex-col gap-2 rounded-xl border border-border bg-surface p-4 shadow-xs transition-colors hover:border-border-strong"
                        >
                          <div className="flex items-start justify-between gap-2">
                            <div className="min-w-0">
                              <p className="truncate text-sm font-semibold text-fg">
                                {w.course_code} · {w.cohort_code}
                              </p>
                              <p className="truncate text-[13px] text-fg-muted">{w.course_name}</p>
                            </div>
                            <Badge tone={sub.tone}>{sub.label}</Badge>
                          </div>
                          <ProgressBar value={pct} label={`${w.course_code} ${w.cohort_code} progress`} />
                          <p className="text-xs text-fg-subtle tabular">
                            {w.entered} of {w.students} students entered
                          </p>
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              </section>
            );
          })}
        </div>
      )}
    </>
  );
}
