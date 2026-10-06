import { api, isApiError, type PlatformMe } from "@scorecode/api-client";
import { Skeleton } from "@scorecode/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Navigate, Outlet, useLocation, useNavigate } from "react-router";

export const meKey = ["platform-me"] as const;

export function usePlatformMe() {
  return useQuery({
    queryKey: meKey,
    queryFn: () => api.get<PlatformMe>("/api/v1/platform/me"),
    retry: (n, e) => !isApiError(e, 401) && !isApiError(e, 404) && n < 2,
    staleTime: 5 * 60_000,
  });
}

export function useCan(permission: string): boolean {
  return Boolean(usePlatformMe().data?.permissions.includes(permission));
}

export function RequireAuth() {
  const me = usePlatformMe();
  const location = useLocation();
  if (me.isPending) {
    return (
      <div className="flex min-h-dvh items-center justify-center" aria-busy="true">
        <Skeleton className="h-8 w-48" />
      </div>
    );
  }
  if (me.error) {
    if (isApiError(me.error, 401))
      return <Navigate to={`/login?next=${encodeURIComponent(location.pathname)}`} replace />;
    throw me.error;
  }
  return <Outlet />;
}

export function useLogout() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  return useMutation({
    mutationFn: () => api.post("/api/v1/platform/auth/logout"),
    onSettled: () => {
      qc.clear();
      void navigate("/login", { replace: true });
    },
  });
}

export function safeNext(next: string | null): string {
  return next && next.startsWith("/") && !next.startsWith("//") && !next.startsWith("/\\") ? next : "/";
}
