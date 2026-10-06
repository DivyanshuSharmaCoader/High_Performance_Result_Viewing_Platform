import { api, type SubscriptionOut } from "@scorecode/api-client";
import { Badge, Callout, Meter, PageHeader, Section, SkeletonText, formatDate } from "@scorecode/ui";
import { useQuery } from "@tanstack/react-query";
import { Check, Minus } from "lucide-react";

const FEATURE_LABELS: Record<string, string> = {
  custom_branding: "Custom colours, typeface and login page",
  remove_powered_by: "Hide “Powered by ScoreCode”",
  custom_domain: "Your own domain",
  multiple_departments: "Multiple departments",
  maker_checker_approval: "Two-person approval",
  scheduled_publication: "Scheduled publication",
  email_notifications: "Email notifications",
  advanced_analytics: "Advanced analytics",
  api_access: "Integration API",
  credit_grading: "Credit-based grading (SGPA)",
  verification_challenge: "Full verification after date-of-birth check",
};

const LIMIT_LABELS: Record<string, { label: string; unit?: string }> = {
  max_students: { label: "Active students" },
  max_staff: { label: "Staff accounts" },
  max_admins: { label: "Administrator seats" },
  max_storage_mb: { label: "Storage", unit: "MB" },
  max_published_exams_per_year: { label: "Exam publications this year" },
  history_years: { label: "Years of results online" },
  max_import_rows: { label: "Rows per spreadsheet import" },
};

const STATUS: Record<string, { label: string; tone: "success" | "warning" | "danger" | "info" }> = {
  active: { label: "Active", tone: "success" },
  trialing: { label: "Trial", tone: "info" },
  past_due: { label: "Payment due", tone: "warning" },
  expired: { label: "Expired", tone: "danger" },
  cancelled: { label: "Cancelled", tone: "danger" },
};

export default function PlanPage() {
  const q = useQuery({
    queryKey: ["subscription"],
    queryFn: () => api.get<SubscriptionOut>("/api/v1/admin/subscription"),
  });
  const s = q.data;
  const status = s ? (STATUS[s.status] ?? { label: s.status, tone: "info" as const }) : null;
  const usage =
    s?.limits.filter((l) =>
      ["max_students", "max_staff", "max_admins", "max_storage_mb", "max_published_exams_per_year"].includes(
        l.key,
      ),
    ) ?? [];
  const caps = s?.limits.filter((l) => ["history_years", "max_import_rows"].includes(l.key)) ?? [];
  return (
    <>
      <PageHeader
        title="Plan & usage"
        description="What your plan includes and how much of it you're using."
        meta={
          s &&
          status && (
            <>
              <Badge tone="brand">{s.plan_name} plan</Badge>
              <Badge tone={status.tone} dot>
                {status.label}
              </Badge>
              {s.period_end && (
                <span className="text-[13px] text-fg-subtle">Renews or ends {formatDate(s.period_end)}</span>
              )}
            </>
          )
        }
      />
      {s?.status === "past_due" && (
        <Callout tone="warning" title="Payment is due" className="mb-6">
          Your plan stays active during the grace period. Contact ScoreCode to renew.
        </Callout>
      )}
      <div className="grid gap-6 lg:grid-cols-2">
        <Section
          title="Usage"
          description="Limits are checked at the moment you add something, so you're never cut off mid-task."
        >
          {q.isPending ? (
            <SkeletonText lines={6} />
          ) : (
            <div className="flex flex-col gap-5">
              {usage.map((l) => (
                <Meter
                  key={l.key}
                  label={LIMIT_LABELS[l.key]?.label ?? l.description}
                  value={l.used}
                  max={l.limit ?? null}
                  formatValue={(n) =>
                    `${n.toLocaleString("en-IN")}${LIMIT_LABELS[l.key]?.unit ? ` ${LIMIT_LABELS[l.key]?.unit}` : ""}`
                  }
                />
              ))}
              <dl className="mt-1 grid gap-3 border-t border-border pt-4 sm:grid-cols-2">
                {caps.map((l) => (
                  <div key={l.key}>
                    <dt className="text-[13px] text-fg-subtle">{LIMIT_LABELS[l.key]?.label}</dt>
                    <dd className="tabular text-sm font-medium">
                      {l.limit === null || l.limit === undefined
                        ? "Unlimited"
                        : l.limit.toLocaleString("en-IN")}
                    </dd>
                  </div>
                ))}
              </dl>
            </div>
          )}
        </Section>
        <Section title="Included features">
          {q.isPending ? (
            <SkeletonText lines={8} />
          ) : (
            <ul className="flex flex-col gap-3">
              {Object.entries(FEATURE_LABELS).map(([key, label]) => {
                const on = Boolean(s?.features[key]);
                return (
                  <li key={key} className="flex items-center gap-3 text-sm">
                    {on ? (
                      <span className="flex size-5 items-center justify-center rounded-full bg-success-soft text-success">
                        <Check className="size-3.5" strokeWidth={3} aria-label="Included" />
                      </span>
                    ) : (
                      <span className="flex size-5 items-center justify-center rounded-full bg-surface-2 text-fg-disabled">
                        <Minus className="size-3.5" strokeWidth={3} aria-label="Not included" />
                      </span>
                    )}
                    <span className={on ? "text-fg" : "text-fg-subtle"}>{label}</span>
                    {s?.overrides.includes(key) && <Badge tone="info">Custom</Badge>}
                  </li>
                );
              })}
            </ul>
          )}
          <p className="mt-6 border-t border-border pt-4 text-[13px] leading-5 text-fg-subtle">
            To change plans, write to{" "}
            <a href="mailto:sales@scorecode.in" className="font-medium text-brand-ink hover:underline">
              sales@scorecode.in
            </a>
            . Upgrades take effect immediately; downgrades never delete data.
          </p>
        </Section>
      </div>
    </>
  );
}
