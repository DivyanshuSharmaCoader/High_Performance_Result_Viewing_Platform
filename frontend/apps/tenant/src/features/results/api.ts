import {
  api,
  type ResultOutcome,
  type ResultsOverview,
  type ResultStudent,
  type ResultStudentsPage,
} from "@scorecode/api-client";
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";

export const resultsUrl = (examId: string) => `/api/v1/admin/exams/${examId}/results`;

export const resultKeys = {
  overview: (examId: string) => ["results", examId] as const,
  students: (examId: string, runId: string, filters: object) =>
    ["results", examId, "students", runId, filters] as const,
  student: (examId: string, runId: string, studentId: string) =>
    ["results", examId, "student", runId, studentId] as const,
};

/** The shapes inside `run.stats` and `run.anomalies` (backend `results/compute.py`). */
export interface ResultStats {
  students: number;
  outcomes: Record<ResultOutcome, number>;
  pass_percentage: string | null;
  average_percentage: string | null;
  median_percentage: string | null;
  histogram: { from: number; to: number; count: number }[];
  grades: { grade: string; count: number }[];
  grades_basis?: "exam" | "paper"; // "paper": the scheme grades papers and gives the exam an SGPA
  papers: {
    paper_id: string;
    course_code: string;
    course_name: string;
    max_total: string;
    appeared: number;
    passed: number;
    pass_percentage: string | null;
    absent: number;
    incomplete: number;
    average: string | null;
    highest: string | null;
    lowest: string | null;
  }[];
}

export interface Anomaly {
  code: string;
  severity: "warning" | "info";
  title: string;
  count: number;
  items: { student_id?: string; enrollment_no?: string; full_name?: string; detail: string }[];
}

export const statsOf = (o: ResultsOverview) => (o.run?.stats ?? null) as ResultStats | null;
export const anomaliesOf = (o: ResultsOverview) => (o.run?.anomalies ?? []) as unknown as Anomaly[];

/** Polls while a run is in progress (docs/05: polling, never websockets). */
export function useResults(examId: string) {
  return useQuery({
    queryKey: resultKeys.overview(examId),
    queryFn: () => api.get<ResultsOverview>(resultsUrl(examId)),
    refetchInterval: (q) => (q.state.data?.run?.status === "running" ? 1500 : false),
  });
}

export function useSetResults(examId: string) {
  const qc = useQueryClient();
  return (o: ResultsOverview) => {
    qc.setQueryData(resultKeys.overview(examId), o);
    void qc.invalidateQueries({ queryKey: ["exams"] }); // the exam's status moves with its results
    void qc.invalidateQueries({ queryKey: ["marking"] });
  };
}

export interface StudentFilters {
  q: string;
  outcome: ResultOutcome | "";
}

export function useResultStudents(examId: string, runId: string, filters: StudentFilters) {
  return useInfiniteQuery({
    queryKey: resultKeys.students(examId, runId, filters),
    queryFn: ({ pageParam }) =>
      api.get<ResultStudentsPage>(`${resultsUrl(examId)}/students`, {
        query: {
          run_id: runId,
          q: filters.q || undefined,
          outcome: filters.outcome || undefined,
          after: pageParam ?? undefined,
          limit: 50,
        },
      }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_after ?? undefined,
    enabled: Boolean(runId),
  });
}

export const useResultStudent = (examId: string, runId: string, studentId: string | null) =>
  useQuery({
    queryKey: resultKeys.student(examId, runId, studentId ?? ""),
    queryFn: () =>
      api.get<ResultStudent>(`${resultsUrl(examId)}/students/${studentId}`, { query: { run_id: runId } }),
    enabled: Boolean(studentId && runId),
  });

export const OUTCOME: Record<
  ResultOutcome,
  { label: string; tone: "success" | "danger" | "neutral" | "warning" }
> = {
  pass: { label: "Pass", tone: "success" },
  fail: { label: "Fail", tone: "danger" },
  absent: { label: "Absent", tone: "neutral" },
  withheld: { label: "Withheld", tone: "warning" },
  incomplete: { label: "Incomplete", tone: "warning" },
};
