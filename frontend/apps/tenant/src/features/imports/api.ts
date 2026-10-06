import {
  api,
  type ImportJob,
  type ImportListItem,
  type ImportRowsPage,
  type ImportStatus,
} from "@scorecode/api-client";
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";

export const I = "/api/v1/admin/imports";
export const BUSY: ImportStatus[] = ["uploaded", "parsing", "validating", "committing"];
export const isBusy = (s: ImportStatus | undefined) => Boolean(s && BUSY.includes(s));

export const importKeys = {
  all: ["imports"] as const,
  list: (kind: string) => ["imports", "list", kind] as const,
  one: (id: string) => ["imports", "one", id] as const,
  rows: (id: string, status: string) => ["imports", "rows", id, status] as const,
};

/** Polls while the worker is busy (docs/13 §5: progress via polling, never websockets). */
export function useImport(id: string) {
  return useQuery({
    queryKey: importKeys.one(id),
    queryFn: () => api.get<ImportJob>(`${I}/${id}`),
    refetchInterval: (q) => (isBusy(q.state.data?.status) ? 1200 : false),
    staleTime: 0,
  });
}

export const useImportList = (kind: string) =>
  useQuery({
    queryKey: importKeys.list(kind),
    queryFn: () => api.get<ImportListItem[]>(I, { query: { kind } }),
    refetchInterval: (q) => ((q.state.data ?? []).some((i) => isBusy(i.status)) ? 3000 : false),
  });

export function useImportRows(id: string, status: string, enabled: boolean) {
  return useInfiniteQuery({
    queryKey: importKeys.rows(id, status),
    queryFn: ({ pageParam }) =>
      api.get<ImportRowsPage>(`${I}/${id}/rows`, {
        query: { status: status || undefined, after: pageParam ?? undefined, limit: 100 },
      }),
    initialPageParam: null as number | null,
    getNextPageParam: (last) => last.next_after ?? undefined,
    enabled,
  });
}

export function useRefreshImport(id: string) {
  const qc = useQueryClient();
  return (job?: ImportJob) => {
    if (job) qc.setQueryData(importKeys.one(id), job);
    void qc.invalidateQueries({ queryKey: importKeys.one(id) });
    void qc.invalidateQueries({ queryKey: ["imports", "rows", id] });
    void qc.invalidateQueries({ queryKey: ["imports", "list"] });
  };
}

export function uploadImport(file: File, fields: Record<string, string | undefined>) {
  const form = new FormData();
  form.append("file", file);
  for (const [k, v] of Object.entries(fields)) if (v) form.append(k, v);
  return api.upload<ImportJob>(I, form);
}
