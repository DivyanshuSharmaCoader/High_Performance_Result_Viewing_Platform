import { api, type PlanCatalogue, type SubscriptionOut } from "@scorecode/api-client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { meKey, useCan } from "../../lib/session";
import { tenantConfigKey } from "../../lib/tenant";

export const subscriptionKey = ["subscription"] as const;

export const useSubscription = (enabled = true) =>
  useQuery({
    queryKey: subscriptionKey,
    queryFn: () => api.get<SubscriptionOut>("/api/v1/admin/subscription"),
    enabled,
    staleTime: 60_000,
  });

/** Trial state for the shell banner; only asked for by people who may see the plan. */
export function useTrial() {
  const allowed = useCan("subscription.view");
  return useSubscription(allowed).data?.trial ?? null;
}

export const usePlanCatalogue = () =>
  useQuery({
    queryKey: ["plans"],
    queryFn: () => api.get<PlanCatalogue>("/api/v1/plans"),
    staleTime: 10 * 60_000,
  });

export function useStartTrial() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<SubscriptionOut>("/api/v1/admin/subscription/trial", {}),
    onSuccess: (s) => {
      qc.setQueryData(subscriptionKey, s);
      void qc.invalidateQueries({ queryKey: meKey }); // the plan badge in the shell
      void qc.invalidateQueries({ queryKey: tenantConfigKey }); // branding features unlock
    },
  });
}

export const formatRupees = (paise: number) =>
  (paise / 100).toLocaleString("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 });

export function salesMailto(subject: string, institution: string): string {
  const body = `Hello ScoreCode team,\n\nWe'd like to talk about ${subject.toLowerCase()} for ${institution}.\n\n`;
  return `mailto:sales@scorecode.in?subject=${encodeURIComponent(`${subject} — ${institution}`)}&body=${encodeURIComponent(body)}`;
}
