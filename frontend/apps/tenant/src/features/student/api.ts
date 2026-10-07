import { api, type MyResult, type MyResultItem, type MyStats } from "@scorecode/api-client";
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
