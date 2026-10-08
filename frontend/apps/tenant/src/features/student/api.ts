import { api, type Marksheet, type MyResult, type MyResultItem, type MyStats } from "@scorecode/api-client";
import { useQuery } from "@tanstack/react-query";

// Personal results: never cached by the browser (the server sends no-store), and kept in memory only
// briefly, so a shared computer doesn't show the last student's marks for long (docs/11 §2.6).
export const myResultsKey = ["me", "results"] as const;

export const useMyResults = () =>
  useQuery({
    queryKey: myResultsKey,
    queryFn: () => api.get<MyResultItem[]>("/api/v1/me/results"),
    staleTime: 60_000,
    gcTime: 5 * 60_000,
  });

export const useMyResult = (id: string) =>
  useQuery({
    queryKey: [...myResultsKey, id],
    queryFn: () => api.get<MyResult>(`/api/v1/me/results/${id}`),
    staleTime: 60_000,
    gcTime: 5 * 60_000,
  });

export const useMyStats = (id: string) =>
  useQuery({
    queryKey: [...myResultsKey, id, "stats"],
    queryFn: () => api.get<MyStats>(`/api/v1/me/results/${id}/stats`),
    staleTime: 5 * 60_000,
    retry: false,
  });

export const myMarksheetKey = (id: string) => [...myResultsKey, id, "marksheet"] as const;
export const fetchMyMarksheet = (id: string) => api.get<Marksheet>(`/api/v1/me/results/${id}/marksheet`);

/** The PDF is prepared right after publication; poll gently until it's ready. */
export const useMyMarksheet = (id: string) =>
  useQuery({
    queryKey: myMarksheetKey(id),
    queryFn: () => fetchMyMarksheet(id),
    staleTime: 30_000,
    gcTime: 60_000,
    retry: false,
    refetchInterval: (q) => (q.state.data?.status === "pending" ? 4000 : false),
  });
