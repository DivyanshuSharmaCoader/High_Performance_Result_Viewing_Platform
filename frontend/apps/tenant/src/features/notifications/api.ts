import { api, type Inbox, type Preferences } from "@scorecode/api-client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

export const unreadKey = ["me", "notifications", "unread"] as const;
export const inboxKey = ["me", "notifications", "inbox"] as const;
export const preferencesKey = ["me", "preferences"] as const;

/**
 * Unread count: fetched on load and when the window regains focus, never on a timer. On result day
 * thousands of open tabs polling every minute would cost more than the results themselves.
 */
export const useUnread = () =>
  useQuery({
    queryKey: unreadKey,
    queryFn: () => api.get<{ unread: number }>("/api/v1/me/notifications/unread-count"),
    staleTime: 60_000,
    refetchOnWindowFocus: true,
  });

export const useInbox = (enabled: boolean) =>
  useQuery({
    queryKey: inboxKey,
    queryFn: () => api.get<Inbox>("/api/v1/me/notifications?limit=20"),
    enabled,
    staleTime: 30_000,
  });

export function useMarkRead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string | "all") =>
      api.post(id === "all" ? "/api/v1/me/notifications/read-all" : `/api/v1/me/notifications/${id}/read`),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["me", "notifications"] });
    },
  });
}

export const usePreferences = () =>
  useQuery({ queryKey: preferencesKey, queryFn: () => api.get<Preferences>("/api/v1/me/preferences") });

export function useSetPreferences() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (p: Preferences) => api.put<Preferences>("/api/v1/me/preferences", p),
    onSuccess: (p) => qc.setQueryData(preferencesKey, p),
  });
}
