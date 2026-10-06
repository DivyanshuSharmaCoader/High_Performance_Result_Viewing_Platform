import {
  api,
  type AccountState,
  type Cohort,
  type Student,
  type StudentCounts,
  type StudentPage,
  type StudentStatus,
} from "@scorecode/api-client";
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";

import { useCohorts, useSessions } from "../academics/api";

export const S = "/api/v1/admin/students";

export interface StudentFilters {
  q: string;
  status: StudentStatus | "";
  cohortId: string;
  account: AccountState | "";
}

export const studentKeys = {
  all: ["students"] as const,
  list: (f: StudentFilters) => ["students", "list", f] as const,
  one: (id: string) => ["students", "one", id] as const,
  counts: ["students", "counts"] as const,
  total: (f: Partial<StudentFilters>) => ["students", "total", f] as const,
};

export function useStudentList(f: StudentFilters) {
  return useInfiniteQuery({
    queryKey: studentKeys.list(f),
    queryFn: ({ pageParam }) =>
      api.get<StudentPage>(S, {
        query: {
          q: f.q || undefined,
          status: f.status || undefined,
          cohort_id: f.cohortId || undefined,
          account: f.account || undefined,
          cursor: pageParam || undefined,
          limit: 50,
        },
      }),
    initialPageParam: "",
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    placeholderData: (prev) => prev,
  });
}

/** Just the count for a filter (limit=1). Used for summaries such as "28 students without an account". */
export function useStudentTotal(f: Partial<StudentFilters>, enabled = true) {
  return useQuery({
    queryKey: studentKeys.total(f),
    queryFn: () =>
      api.get<StudentPage>(S, {
        query: {
          status: f.status || undefined,
          cohort_id: f.cohortId || undefined,
          account: f.account || undefined,
          limit: 1,
        },
      }),
    select: (p) => p.total ?? 0,
    enabled,
  });
}

export const useStudent = (id: string) =>
  useQuery({ queryKey: studentKeys.one(id), queryFn: () => api.get<Student>(`${S}/${id}`) });

export const useStudentCounts = () =>
  useQuery({ queryKey: studentKeys.counts, queryFn: () => api.get<StudentCounts>(`${S}/counts`) });

export function useInvalidateStudents() {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: studentKeys.all });
    void qc.invalidateQueries({ queryKey: ["subscription"] });
    void qc.invalidateQueries({ queryKey: ["onboarding"] });
  };
}

/** Cohorts of the current session (or the newest one), for pickers and filters. */
export function useCurrentCohorts() {
  const sessions = useSessions();
  const current = sessions.data?.find((s) => s.is_current) ?? sessions.data?.[0];
  const cohorts = useCohorts(current?.id ?? "", "");
  const active: Cohort[] = (cohorts.data ?? []).filter((c) => !c.archived_at && c.session_id === current?.id);
  return { session: current, cohorts: active, isPending: sessions.isPending || cohorts.isPending };
}

export const STATUS_LABEL: Record<StudentStatus, string> = {
  active: "Active",
  graduated: "Graduated",
  withdrawn: "Withdrawn",
  archived: "Archived",
};

export const ACCOUNT_LABEL: Record<AccountState, string> = {
  none: "No account yet",
  pending: "Code issued",
  active: "Activated",
  disabled: "Sign-in disabled",
};
