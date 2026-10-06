import {
  api,
  type AcademicSession,
  type Cohort,
  type CourseList,
  type Department,
  type Program,
  type StructureCounts,
  type Term,
} from "@scorecode/api-client";
import { useQuery, useQueryClient } from "@tanstack/react-query";

const A = "/api/v1/admin";

export const keys = {
  all: ["academics"] as const,
  summary: ["academics", "summary"] as const,
  sessions: (archived: boolean) => ["academics", "sessions", archived] as const,
  terms: (sessionId: string) => ["academics", "terms", sessionId] as const,
  departments: (archived: boolean) => ["academics", "departments", archived] as const,
  programs: (archived: boolean) => ["academics", "programs", archived] as const,
  cohorts: (sessionId: string, programId: string, archived: boolean) =>
    ["academics", "cohorts", sessionId, programId, archived] as const,
  courses: (q: string, departmentId: string, archived: boolean, offset: number) =>
    ["academics", "courses", q, departmentId, archived, offset] as const,
};

export const useSummary = () =>
  useQuery({
    queryKey: keys.summary,
    queryFn: () => api.get<StructureCounts>(`${A}/academic-structure/summary`),
  });
export const useSessions = (archived = false) =>
  useQuery({
    queryKey: keys.sessions(archived),
    queryFn: () =>
      api.get<AcademicSession[]>(`${A}/academic-sessions`, { query: { include_archived: archived } }),
  });
export const useTerms = (sessionId: string | undefined) =>
  useQuery({
    queryKey: keys.terms(sessionId ?? ""),
    queryFn: () => api.get<Term[]>(`${A}/academic-sessions/${sessionId}/terms`),
    enabled: Boolean(sessionId),
  });
export const useDepartments = (archived = false) =>
  useQuery({
    queryKey: keys.departments(archived),
    queryFn: () => api.get<Department[]>(`${A}/departments`, { query: { include_archived: archived } }),
  });
export const usePrograms = (archived = false) =>
  useQuery({
    queryKey: keys.programs(archived),
    queryFn: () => api.get<Program[]>(`${A}/programs`, { query: { include_archived: archived } }),
  });
export const useCohorts = (sessionId: string, programId: string, archived = false) =>
  useQuery({
    queryKey: keys.cohorts(sessionId, programId, archived),
    queryFn: () =>
      api.get<Cohort[]>(`${A}/cohorts`, {
        query: { session_id: sessionId, program_id: programId, include_archived: archived },
      }),
  });
export const useCourses = (q: string, departmentId: string, archived: boolean, offset: number, limit = 50) =>
  useQuery({
    queryKey: keys.courses(q, departmentId, archived, offset),
    queryFn: () =>
      api.get<CourseList>(`${A}/courses`, {
        query: { q, department_id: departmentId, include_archived: archived, offset, limit },
      }),
    placeholderData: (prev) => prev,
  });

/** After any academic write: refresh lists, counts and the onboarding checklist. */
export function useInvalidateAcademics() {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: keys.all });
    void qc.invalidateQueries({ queryKey: ["onboarding"] });
  };
}

export const academicsApi = {
  base: A,
};
