import { api, isApiError, type TenantConfig } from "@scorecode/api-client";
import { applyBrandTokens } from "@scorecode/ui";
import { useQuery } from "@tanstack/react-query";
import { createContext, useContext, useEffect, type ReactNode } from "react";

import { BootError, BootSplash, NoInstitution, PortalUnavailable } from "../components/system-pages";

const TenantContext = createContext<TenantConfig | null>(null);

export const tenantConfigKey = ["tenant-config"] as const;

export function TenantProvider({ children }: { children: ReactNode }) {
  const query = useQuery({
    queryKey: tenantConfigKey,
    queryFn: () => api.get<TenantConfig>("/api/v1/tenant/config"),
    staleTime: 60_000,
  });

  useEffect(() => {
    if (!query.data) return;
    applyBrandTokens(query.data.branding.tokens);
    document.title = `${query.data.branding.display_name} · Results portal`;
  }, [query.data]);

  if (query.isPending) return <BootSplash />;
  if (query.error) {
    if (isApiError(query.error, 404)) return <NoInstitution />;
    if (isApiError(query.error, 403)) {
      const name =
        typeof query.error.body.institution === "string" ? query.error.body.institution : undefined;
      return <PortalUnavailable institution={name} />;
    }
    return <BootError onRetry={() => void query.refetch()} />;
  }
  return <TenantContext.Provider value={query.data}>{children}</TenantContext.Provider>;
}

export function useTenant(): TenantConfig {
  const ctx = useContext(TenantContext);
  if (!ctx) throw new Error("useTenant must be used inside TenantProvider");
  return ctx;
}

export function useFeature(key: string): boolean {
  return Boolean(useTenant().features[key]);
}
