import { api, isApiError, type Me } from "@scorecode/api-client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Navigate, Outlet, useLocation, useNavigate } from "react-router";

import { AppSkeleton, Forbidden } from "../components/system-pages";

export const meKey = ["me"] as const;

export function useMe() {
  return useQuery({
    queryKey: meKey,
    queryFn: () => api.get<Me>("/api/v1/me"),
    retry: (count, error) => !isApiError(error, 401) && count < 2,
    staleTime: 5 * 60_000,
  });
}

/** The signed-in principal; only call below <RequireAuth>. */
export function useSession(): Me {
  const { data } = useMe();
  if (!data) throw new Error("useSession used outside RequireAuth");
  return data;
}

export function useCan(permission: string): boolean {
  const { data } = useMe();
  return Boolean(data?.permissions.includes(permission));
}

export function homePathFor(me: Pick<Me, "permissions">): string {
  if (me.permissions.includes("students.view")) return "/admin";
  return "/account";
}

export function RequireAuth() {
  const location = useLocation();
  const me = useMe();
  if (me.isPending) return <AppSkeleton />;
  if (me.error) {
    if (isApiError(me.error, 401)) {
      const next = location.pathname + location.search;
      return (
        <Navigate to={`/login${next && next !== "/" ? `?next=${encodeURIComponent(next)}` : ""}`} replace />
      );
    }
    throw me.error;
  }
  return <Outlet />;
}

export function RequirePermission({ permission }: { permission: string }) {
  const allowed = useCan(permission);
  return allowed ? <Outlet /> : <Forbidden />;
}

export function useLogout() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  return useMutation({
    mutationFn: () => api.post("/api/v1/auth/logout"),
    onSettled: () => {
      qc.clear();
      void navigate("/login", { replace: true });
    },
  });
}

/** Only allow same-origin, path-relative redirects after login (no open redirects). */
export function safeNext(next: string | null): string | null {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) return null;
  return next;
}
