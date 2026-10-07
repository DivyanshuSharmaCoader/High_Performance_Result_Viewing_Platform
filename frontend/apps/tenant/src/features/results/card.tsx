import type { ResultPaper, ResultStudent } from "@scorecode/api-client";
import { Badge } from "@scorecode/ui";

import { trimNum } from "../exams/api";
import { OUTCOME } from "./api";

export interface PaperMeta {
  id: string;
  course_code: string;
  course_name: string;
  components: { code: string; label: string; max: string | number }[];
}

const PAPER_OUTCOME: Record<string, { label: string; tone: "success" | "danger" | "neutral" | "warning" }> = {
  ...OUTCOME,
  exempt: { label: "Exempt", tone: "neutral" },
};

function Figure({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-[12px] font-medium uppercase tracking-wide text-fg-subtle">{label}</dt>
      <dd className="tabular mt-0.5 text-xl font-semibold text-fg">{value}</dd>
    </div>
  );
}

function PaperRow({ paper, meta }: { paper: ResultPaper; meta: PaperMeta | undefined }) {
  const outcome = PAPER_OUTCOME[paper.outcome] ?? { label: paper.outcome, tone: "neutral" as const };
  const marks = paper.components as Record<string, string>;
  const present = paper.attendance === "present";
  return (
    <tr className="border-t border-border align-top">
      <td className="px-3 py-2.5">
        <p className="font-medium text-fg">{meta?.course_code ?? "Paper"}</p>
        <p className="text-[13px] text-fg-muted">{meta?.course_name}</p>
      </td>
      <td className="px-3 py-2.5 text-[13px]">
        {present ? (
          <ul className="flex flex-wrap gap-x-3 gap-y-1">
            {(meta?.components ?? []).map((c) => {
              const failed = paper.failed_components.includes(c.code);
              const missing = paper.missing_components.includes(c.code);
              return (
                <li key={c.code} className={failed ? "text-danger" : "text-fg-muted"}>
                  {c.label}{" "}
                  <span className="tabular font-medium text-fg">
                    {missing ? "—" : trimNum(marks[c.code])}
                  </span>
                  <span className="text-fg-subtle">/{trimNum(c.max)}</span>
                  {failed && <span className="sr-only"> (below the minimum)</span>}
                </li>
              );
            })}
          </ul>
        ) : (
          <span className="text-fg-muted">
            {paper.attendance ? (PAPER_OUTCOME[paper.attendance]?.label ?? paper.attendance) : "No marks"}
          </span>
        )}
      </td>
      <td className="tabular px-3 py-2.5 text-right font-medium">
        {paper.total !== null ? `${trimNum(paper.total)}/${trimNum(paper.max_total)}` : "—"}
      </td>
      <td className="px-3 py-2.5 text-center font-semibold">{paper.grade ?? "—"}</td>
      <td className="px-3 py-2.5 text-right">
        <Badge tone={outcome.tone}>{outcome.label}</Badge>
      </td>
    </tr>
  );
}

/** One student's result, as the student will see it (the student portal reuses this in Phase 10). */
export function ResultCard({ result, papers }: { result: ResultStudent; papers: Map<string, PaperMeta> }) {
  const outcome = OUTCOME[result.outcome];
  const figures = [
    result.percentage !== null && { label: "Percentage", value: `${trimNum(result.percentage)}%` },
    result.sgpa !== null && { label: "SGPA", value: trimNum(result.sgpa) },
    result.grade && { label: "Grade", value: result.grade },
    result.total !== null && {
      label: "Total",
      value: `${trimNum(result.total)}/${trimNum(result.max_total)}`,
    },
    result.rank !== null && { label: "Rank", value: `#${result.rank}` },
  ].filter((f): f is { label: string; value: string } => Boolean(f));
  return (
    <article className="flex flex-col gap-4" aria-label={`Result of ${result.full_name}`}>
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="truncate text-lg font-semibold text-fg">{result.full_name}</h3>
          <p className="text-[13px] text-fg-muted">
            <span className="font-mono">{result.enrollment_no}</span> · {result.cohort_code}
          </p>
        </div>
        <Badge tone={outcome.tone} dot>
          {outcome.label}
        </Badge>
      </header>
      {figures.length > 0 && (
        <dl className="grid grid-cols-2 gap-4 rounded-xl bg-surface-2 p-4 sm:grid-cols-4">
          {figures.map((f) => (
            <Figure key={f.label} {...f} />
          ))}
        </dl>
      )}
      <div className="overflow-x-auto rounded-xl border border-border">
        <table className="w-full min-w-[520px] text-sm">
          <caption className="sr-only">Marks by paper</caption>
          <thead className="bg-surface-2 text-left text-xs text-fg-subtle">
            <tr>
              <th className="px-3 py-2 font-medium">Paper</th>
              <th className="px-3 py-2 font-medium">Marks</th>
              <th className="px-3 py-2 text-right font-medium">Total</th>
              <th className="px-3 py-2 text-center font-medium">Grade</th>
              <th className="px-3 py-2 text-right font-medium">Result</th>
            </tr>
          </thead>
          <tbody>
            {result.papers.map((p) => (
              <PaperRow key={p.exam_paper_id} paper={p} meta={papers.get(p.exam_paper_id)} />
            ))}
          </tbody>
        </table>
      </div>
      {result.notes.length > 0 && (
        <ul className="list-disc pl-5 text-[13px] text-fg-muted">
          {result.notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      )}
    </article>
  );
}
