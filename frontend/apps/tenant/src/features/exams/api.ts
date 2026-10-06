import { api, type Exam, type ExamKind, type ExamListItem, type ExamStatus } from "@scorecode/api-client";
import { useQuery, useQueryClient } from "@tanstack/react-query";

export const E = "/api/v1/admin/exams";

export const examKeys = {
  all: ["exams"] as const,
  list: (status: string) => ["exams", "list", status] as const,
  one: (id: string) => ["exams", "one", id] as const,
};

export const useExams = (status: ExamStatus | "") =>
  useQuery({
    queryKey: examKeys.list(status),
    queryFn: () => api.get<ExamListItem[]>(E, { query: { status: status || undefined } }),
  });

export const useExam = (id: string) =>
  useQuery({ queryKey: examKeys.one(id), queryFn: () => api.get<Exam>(`${E}/${id}`) });

export function useSetExam() {
  const qc = useQueryClient();
  return (exam: Exam) => {
    qc.setQueryData(examKeys.one(exam.id), exam);
    void qc.invalidateQueries({ queryKey: ["exams", "list"] });
  };
}

export const KIND_LABEL: Record<ExamKind, string> = {
  unit_test: "Unit test",
  term: "Term exam",
  semester: "Semester exam",
  supplementary: "Supplementary",
  other: "Other",
};

export const STATUS: Record<
  ExamStatus,
  { label: string; tone: "neutral" | "info" | "warning" | "success" | "brand" }
> = {
  draft: { label: "Draft", tone: "neutral" },
  marks_entry_open: { label: "Marks entry open", tone: "info" },
  marks_entry_closed: { label: "Marks entry closed", tone: "warning" },
  processed: { label: "Processed", tone: "warning" },
  approved: { label: "Approved", tone: "brand" },
  scheduled: { label: "Scheduled", tone: "brand" },
  published: { label: "Published", tone: "success" },
  correction_draft: { label: "Correction", tone: "warning" },
  withdrawn: { label: "Withdrawn", tone: "neutral" },
  archived: { label: "Archived", tone: "neutral" },
};

/** Statuses in which papers, components and cohorts may still change (mirrors the API). */
export const SETUP_EDITABLE: ExamStatus[] = ["draft", "marks_entry_open", "marks_entry_closed"];

export interface ComponentDraft {
  code: string;
  label: string;
  max: string;
  min_pass: string;
}

export const COMPONENT_PRESETS: { label: string; components: ComponentDraft[] }[] = [
  { label: "One total out of 100", components: [{ code: "T", label: "Total", max: "100", min_pass: "" }] },
  {
    label: "Internal 40 + External 60",
    components: [
      { code: "INT", label: "Internal", max: "40", min_pass: "" },
      { code: "EXT", label: "External", max: "60", min_pass: "" },
    ],
  },
  {
    label: "Theory 80 + Internal assessment 20",
    components: [
      { code: "TH", label: "Theory", max: "80", min_pass: "" },
      { code: "IA", label: "Internal assessment", max: "20", min_pass: "" },
    ],
  },
  {
    label: "Mid-sem 25 + End-sem 45 + Sessionals 30",
    components: [
      { code: "MST", label: "Mid-semester", max: "25", min_pass: "" },
      { code: "EST", label: "End-semester", max: "45", min_pass: "" },
      { code: "SESS", label: "Sessionals", max: "30", min_pass: "" },
    ],
  },
];

/** "40.00" → "40" for display and editing. */
export const trimNum = (v: string | number | null | undefined): string => {
  if (v === null || v === undefined) return "";
  const s = String(v);
  return s.includes(".") ? s.replace(/\.?0+$/, "") : s;
};
