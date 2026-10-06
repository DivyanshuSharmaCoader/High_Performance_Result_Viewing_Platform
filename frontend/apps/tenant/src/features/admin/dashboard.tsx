import {
  api,
  type AuditEntry,
  type Onboarding,
  type Page,
  type SubscriptionOut,
} from "@scorecode/api-client";
import {
  Badge,
  Button,
  Meter,
  PageHeader,
  ProgressBar,
  Section,
  Skeleton,
  SkeletonText,
  formatRelative,
  toast,
} from "@scorecode/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, CheckCircle2, Circle, X } from "lucide-react";
import { Link } from "react-router";

import { useCan, useSession } from "../../lib/session";
import { describeAction } from "./audit-format";

function greeting(): string {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}

function OnboardingChecklist() {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["onboarding"],
    queryFn: () => api.get<Onboarding>("/api/v1/admin/onboarding"),
  });
  const dismiss = useMutation({
    mutationFn: (dismissed: boolean) => api.put<Onboarding>("/api/v1/admin/onboarding", { dismissed }),
    onSuccess: (data) => {
      qc.setQueryData(["onboarding"], data);
      if (data.dismissed)
        toast("Setup guide hidden", { description: "You can bring it back from Settings." });
    },
  });
  if (q.isPending) return <Skeleton className="h-56 rounded-xl" />;
  if (!q.data || q.data.dismissed || q.data.completed === q.data.total) return null;
  const { steps, completed, total } = q.data;
  const next = steps.find((s) => !s.done);
  return (
    <section className="rounded-xl border border-border bg-surface shadow-xs" aria-labelledby="setup-title">
      <div className="flex items-start justify-between gap-4 px-5 pb-4 pt-5">
        <div className="min-w-0 flex-1">
          <h2 id="setup-title" className="text-[15px] font-semibold">
            Set up your institution
          </h2>
          <p className="mt-0.5 text-[13px] text-fg-subtle">
            {completed} of {total} steps done{next ? ` · Next: ${next.title.toLowerCase()}` : ""}
          </p>
          <ProgressBar value={(completed / total) * 100} label="Setup progress" className="mt-3 max-w-sm" />
        </div>
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={() => dismiss.mutate(true)}
          aria-label="Hide setup guide"
        >
          <X />
        </Button>
      </div>
      <ul className="divide-y divide-border border-t border-border">
        {steps.map((step) => (
          <li key={step.key}>
            <Link
              to={step.href}
              className="group flex items-center gap-3.5 px-5 py-3.5 transition-colors hover:bg-surface-2/60"
            >
              {step.done ? (
                <CheckCircle2 className="size-5 shrink-0 text-success" aria-label="Done" />
              ) : (
                <Circle className="size-5 shrink-0 text-border-strong" aria-label="Not done" />
              )}
              <span className="min-w-0 flex-1">
                <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <span
                    className={
                      step.done
                        ? "text-sm text-fg-subtle line-through decoration-border-strong"
                        : "text-sm font-medium text-fg"
                    }
                  >
                    {step.title}
                  </span>
                  {step.required_for_publishing && !step.done && (
                    <Badge tone="warning">Needed to publish</Badge>
                  )}
                </span>
                {!step.done && (
                  <span className="mt-0.5 block text-[13px] leading-5 text-fg-subtle">
                    {step.detail ?? step.description}
                  </span>
                )}
              </span>
              <ArrowRight
                className="size-4 shrink-0 text-fg-subtle opacity-0 transition-opacity group-hover:opacity-100"
                aria-hidden
              />
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

function PlanUsage() {
  const q = useQuery({
    queryKey: ["subscription"],
    queryFn: () => api.get<SubscriptionOut>("/api/v1/admin/subscription"),
  });
  const shown = ["max_students", "max_staff", "max_storage_mb"];
  return (
    <Section
      title="Plan usage"
      description={q.data ? `${q.data.plan_name} plan` : undefined}
      actions={
        <Link to="/admin/plan" className="text-[13px] font-medium text-brand-ink hover:underline">
          Details
        </Link>
      }
    >
      {q.isPending ? (
        <SkeletonText lines={4} />
      ) : (
        <div className="flex flex-col gap-5">
          {q.data?.limits
            .filter((l) => shown.includes(l.key))
            .map((l) => (
              <Meter
                key={l.key}
                label={
                  {
                    max_students: "Active students",
                    max_staff: "Staff accounts",
                    max_storage_mb: "Storage (MB)",
                  }[l.key] ?? l.description
                }
                value={l.used}
                max={l.limit ?? null}
              />
            ))}
        </div>
      )}
    </Section>
  );
}

function RecentActivity() {
  const q = useQuery({
    queryKey: ["audit", "recent"],
    queryFn: () => api.get<Page<AuditEntry>>("/api/v1/admin/audit-logs", { query: { limit: 6 } }),
  });
  return (
    <Section
      title="Recent activity"
      actions={
        <Link to="/admin/audit-log" className="text-[13px] font-medium text-brand-ink hover:underline">
          View all
        </Link>
      }
    >
      {q.isPending ? (
        <SkeletonText lines={5} />
      ) : q.data && q.data.items.length > 0 ? (
        <ol className="flex flex-col gap-4">
          {q.data.items.map((e) => (
            <li key={e.id} className="flex gap-3 text-sm">
              <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-border-strong" aria-hidden />
              <span className="min-w-0 flex-1">
                <span className="text-fg">{e.summary ?? describeAction(e.action)}</span>
                <span className="mt-0.5 block text-[13px] text-fg-subtle">
                  {e.actor_label ?? "System"} · {formatRelative(e.occurred_at)}
                </span>
              </span>
            </li>
          ))}
        </ol>
      ) : (
        <p className="text-sm text-fg-subtle">Changes made by your team will appear here.</p>
      )}
    </Section>
  );
}

export default function DashboardPage() {
  const me = useSession();
  const canSettings = useCan("settings.manage");
  const canAudit = useCan("audit.view");
  return (
    <>
      <PageHeader
        title={`${greeting()}, ${me.full_name}`}
        description={`Here's what's happening at ${me.tenant.name}.`}
      />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
        <div className="flex min-w-0 flex-col gap-6">
          {canSettings && <OnboardingChecklist />}
          {canAudit && <RecentActivity />}
        </div>
        <div className="flex flex-col gap-6">
          <PlanUsage />
        </div>
      </div>
    </>
  );
}
