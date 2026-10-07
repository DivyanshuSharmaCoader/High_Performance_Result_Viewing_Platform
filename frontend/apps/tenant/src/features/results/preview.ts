import type { Exam, ResultPayload, ResultStudent, ResultsOverview } from "@scorecode/api-client";

import { trimNum } from "../exams/api";

const n = (v: string | number | null | undefined): string | null => (v == null ? null : trimNum(v));

/**
 * A processed (not yet published) result in the shape of a published snapshot, so the preview is drawn by
 * the very component students will see. Mirrors backend `publishing/snapshot.py` (payload schema 1).
 */
export function previewPayload(
  r: ResultStudent,
  exam: Exam | undefined,
  overview: ResultsOverview,
  institution: string,
): ResultPayload {
  const papers = new Map((exam?.papers ?? []).map((p) => [p.id, p]));
  return {
    schema: 1,
    institution: { name: institution, display_name: institution },
    exam: {
      name: overview.exam_name,
      kind: exam?.kind ?? "",
      term: exam?.term.name ?? "",
      session: exam?.term.session_code ?? "",
    },
    scheme: { name: overview.run?.scheme?.name ?? "", strategy: "" },
    student: {
      enrollment_no: r.enrollment_no,
      full_name: r.full_name,
      cohort: { code: r.cohort_code, name: r.cohort_code },
      program: null,
    },
    result: {
      outcome: r.outcome,
      total: n(r.total),
      max_total: n(r.max_total),
      percentage: n(r.percentage),
      grade: r.grade,
      grade_point: n(r.grade_point),
      sgpa: n(r.sgpa),
      credits_attempted: n(r.credits_attempted),
      credits_earned: n(r.credits_earned),
      rank: r.rank,
      notes: r.notes,
    },
    papers: r.papers.flatMap((p) => {
      const meta = papers.get(p.exam_paper_id);
      if (!meta) return [];
      const marks = p.components as Record<string, string>;
      return [
        {
          course_code: meta.course_code,
          course_name: meta.course_name,
          credits: n(meta.credits),
          attendance: p.attendance,
          outcome: p.outcome,
          total: n(p.total),
          max_total: n(p.max_total),
          percentage: n(p.percentage),
          grade: p.grade,
          grade_point: n(p.grade_point),
          failed_components: p.failed_components,
          missing_components: p.missing_components,
          components: meta.components.map((c) => ({
            code: c.code,
            label: c.label,
            max: n(c.max),
            marks: n(marks[c.code]),
          })),
        },
      ];
    }),
  };
}
