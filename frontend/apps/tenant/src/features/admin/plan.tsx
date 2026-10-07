import { ApiError, type PublicPlan, type SubscriptionOut, type TrialOut } from "@scorecode/api-client";
import {
  Badge,
  Button,
  Callout,
  ConfirmDialog,
  Meter,
  PageHeader,
  Section,
  Skeleton,
  SkeletonText,
  cn,
  formatDate,
  toast,
} from "@scorecode/ui";
import {
  BarChart3,
  CalendarClock,
  Check,
  Info,
  Mail,
  Minus,
  Network,
  Palette,
  ShieldCheck,
  Sparkles,
  Users,
} from "lucide-react";
import { useState } from "react";

import { useSession } from "../../lib/session";
import { useTenant } from "../../lib/tenant";
import { formatRupees, salesMailto, usePlanCatalogue, useStartTrial, useSubscription } from "../plan/api";

const FEATURE_LABELS: Record<string, string> = {
  custom_branding: "Your colours, typeface and login page",
  scheduled_publication: "Scheduled publication",
  maker_checker_approval: "Two-person approval",
  multiple_departments: "Multiple departments",
  advanced_analytics: "Advanced analytics",
  remove_powered_by: "Hide “Powered by ScoreCode”",
  verification_challenge: "Full verification after a date-of-birth check",
  custom_domain: "Your own domain",
  api_access: "Integration API",
  email_notifications: "Email notifications",
  credit_grading: "Credit-based grading (SGPA)",
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

const HIGHLIGHTS = [
  { icon: Palette, text: "Your colours, typeface and login page" },
  { icon: CalendarClock, text: "Publish at a set time, automatically" },
  { icon: ShieldCheck, text: "Two-person approval before release" },
  { icon: Network, text: "Departments for every wing or faculty" },
  { icon: BarChart3, text: "Trends across exams and subjects" },
  { icon: Users, text: "Up to 1,000 students and 40 staff" },
];

// ---- the trial ----------------------------------------------------------------------------------

/** Days left as a ring: calm while there's time, amber in the last week. */
function CountdownRing({ left, total }: { left: number; total: number }) {
  const r = 34;
  const c = 2 * Math.PI * r;
  const urgent = left <= 7;
  return (
    <div className="relative size-24 shrink-0" aria-hidden>
      <svg viewBox="0 0 80 80" className="size-24 -rotate-90">
        <circle cx="40" cy="40" r={r} className="fill-none stroke-surface-3" strokeWidth="7" />
        <circle
          cx="40"
          cy="40"
          r={r}
          className={cn(
            "fill-none transition-[stroke-dashoffset] duration-700",
            urgent ? "stroke-warning" : "stroke-brand",
          )}
          strokeWidth="7"
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - Math.max(0, Math.min(1, left / total)))}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="tabular text-2xl font-semibold leading-none text-fg">{left}</span>
        <span className="mt-0.5 text-[11px] text-fg-subtle">{left === 1 ? "day" : "days"}</span>
      </div>
    </div>
  );
}

function TrialCard({ s, trial }: { s: SubscriptionOut; trial: TrialOut }) {
  const me = useSession();
  const { branding } = useTenant();
  const institution = branding.display_name;
  const start = useStartTrial();
  const [confirming, setConfirming] = useState(false);
  const [endsOn, setEndsOn] = useState("");
  const [refusal, setRefusal] = useState<{ detail: string; review: boolean } | null>(null);

  if (trial.state === "available") {
    return (
      <section
        aria-labelledby="trial-title"
        className="relative mb-6 overflow-hidden rounded-2xl border border-brand/20 bg-surface p-6 shadow-xs sm:p-8"
      >
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 bg-[radial-gradient(80%_120%_at_100%_0%,color-mix(in_oklab,var(--sc-brand)_12%,transparent),transparent)]"
        />
        <div className="relative flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
          <div className="max-w-2xl">
            <Badge tone="brand" icon={<Sparkles />}>
              {trial.days} days free · no card
            </Badge>
            <h2 id="trial-title" className="mt-3 text-[22px] font-semibold tracking-[-0.01em] text-fg">
              Try everything in Pro, free for {trial.days} days
            </h2>
            <p className="mt-2 text-sm leading-6 text-fg-muted">
              Nothing is charged, ever. When the trial ends you move back to Free on your own and keep
              everything you created.
            </p>
            <ul className="mt-5 grid gap-x-6 gap-y-2.5 sm:grid-cols-2">
              {HIGHLIGHTS.map(({ icon: Icon, text }) => (
                <li key={text} className="flex items-center gap-2.5 text-sm text-fg">
                  <span className="flex size-6 shrink-0 items-center justify-center rounded-md bg-brand-soft text-brand-ink">
                    <Icon className="size-3.5" aria-hidden />
                  </span>
                  {text}
                </li>
              ))}
            </ul>
          </div>
          <div className="flex shrink-0 flex-col items-start gap-2 lg:items-end">
            {trial.can_start ? (
              <>
                <Button
                  size="lg"
                  leadingIcon={<Sparkles />}
                  onClick={() => {
                    setEndsOn(formatDate(new Date(Date.now() + trial.days * 86_400_000).toISOString()));
                    setConfirming(true);
                  }}
                >
                  Start my free trial
                </Button>
                <span className="text-[12px] text-fg-subtle">One trial per institution</span>
              </>
            ) : (
              <p className="max-w-xs text-[13px] text-fg-muted">
                Your institution&apos;s owner can start the trial from this page.
              </p>
            )}
          </div>
        </div>
        {refusal && (
          <Callout
            tone={refusal.review ? "info" : "warning"}
            title={refusal.review ? "Almost there" : "The trial isn't available"}
            className="relative mt-6"
            action={
              <Button size="sm" variant="secondary" leadingIcon={<Mail />} asChild>
                <a
                  href={`mailto:support@scorecode.in?subject=${encodeURIComponent(`Trial for ${institution}`)}`}
                >
                  Write to support
                </a>
              </Button>
            }
          >
            {refusal.detail}
          </Callout>
        )}
        <ConfirmDialog
          open={confirming}
          onOpenChange={setConfirming}
          title={`Start your ${trial.days}-day Pro trial?`}
          description={`It runs until ${endsOn}. We'll remind ${me.email ?? "you"} a week and a day before it ends. Afterwards you're back on Free automatically — nothing is charged and nothing is deleted.`}
          confirmLabel="Start trial"
          loading={start.isPending}
          onConfirm={() =>
            start.mutate(undefined, {
              onSuccess: (next) => {
                setConfirming(false);
                setRefusal(null);
                toast.success("Your Pro trial has started", {
                  description: next.trial.ends_at
                    ? `Everything in Pro until ${formatDate(next.trial.ends_at)}.`
                    : undefined,
                });
              },
              onError: (e) => {
                setConfirming(false);
                if (e instanceof ApiError && e.code === "trial-unavailable") {
                  setRefusal({ detail: e.detail, review: e.body.reason === "review" });
                } else {
                  toast.error("The trial couldn't start", {
                    description: e instanceof ApiError ? e.detail : "Please try again.",
                  });
                }
              },
            })
          }
        />
      </section>
    );
  }

  if (trial.state === "active" && trial.days_left !== null && trial.ends_at) {
    const urgent = trial.days_left <= 7;
    return (
      <section
        aria-label="Your Pro trial"
        className={cn(
          "mb-6 flex flex-col gap-5 rounded-2xl border bg-surface p-6 shadow-xs sm:flex-row sm:items-center",
          urgent ? "border-warning-border" : "border-border",
        )}
      >
        <CountdownRing left={trial.days_left} total={trial.days} />
        <div className="min-w-0 flex-1">
          <Badge tone={urgent ? "warning" : "info"} dot>
            {s.plan_name}
          </Badge>
          <h2 className="mt-2 text-lg font-semibold text-fg">
            {trial.days_left === 0
              ? "Your trial ends today"
              : `${trial.days_left} ${trial.days_left === 1 ? "day" : "days"} left in your Pro trial`}
          </h2>
          <p className="mt-1 text-sm text-fg-muted">
            Ends on {formatDate(trial.ends_at)}. Then you&apos;re back on Free: nothing is deleted, and above
            Free&apos;s limits you can still view and export everything.
          </p>
        </div>
        <Button variant={urgent ? "primary" : "secondary"} leadingIcon={<Mail />} asChild>
          <a href={salesMailto("Keeping Pro", institution)}>Keep Pro</a>
        </Button>
      </section>
    );
  }

  if ((trial.state === "ended" || trial.state === "revoked") && trial.ends_at) {
    return (
      <Callout
        tone="info"
        title={`Your Pro trial ended on ${formatDate(trial.ends_at)}`}
        className="mb-6"
        action={
          <Button size="sm" variant="secondary" leadingIcon={<Mail />} asChild>
            <a href={salesMailto("Upgrading", institution)}>Talk to us</a>
          </Button>
        }
      >
        You&apos;re on Free and everything you created is still here.
      </Callout>
    );
  }
  return null;
}

// ---- usage and features ---------------------------------------------------------------------------

const storage = (mb: number) =>
  mb >= 1024
    ? `${(mb / 1024).toLocaleString("en-IN", { maximumFractionDigits: 1 })} GB`
    : `${mb.toLocaleString("en-IN")} MB`;

function Usage({ s }: { s: SubscriptionOut }) {
  const usage = s.limits.filter((l) =>
    ["max_students", "max_staff", "max_admins", "max_storage_mb", "max_published_exams_per_year"].includes(
      l.key,
    ),
  );
  const caps = s.limits.filter((l) => ["history_years", "max_import_rows"].includes(l.key));
  const full = usage.filter((l) => l.limit !== null && l.used >= l.limit);
  return (
    <Section
      title="Usage"
      description="Limits are checked when you add something, so nothing stops half-way."
    >
      <div className="flex flex-col gap-5">
        {full.length > 0 && (
          <Callout tone="warning">
            You&apos;ve reached the limit for{" "}
            {full.map((l) => (LIMIT_LABELS[l.key]?.label ?? l.description).toLowerCase()).join(" and ")}.
            Everything already here keeps working; to add more, upgrade
            {s.trial.state === "available" ? " or start the free trial" : ""}.
          </Callout>
        )}
        {usage.map((l) => (
          <Meter
            key={l.key}
            label={LIMIT_LABELS[l.key]?.label ?? l.description}
            value={l.used}
            max={l.limit ?? null}
            formatValue={(n) => (l.key === "max_storage_mb" ? storage(n) : n.toLocaleString("en-IN"))}
          />
        ))}
        <dl className="mt-1 grid gap-3 border-t border-border pt-4 sm:grid-cols-2">
          {caps.map((l) => (
            <div key={l.key}>
              <dt className="text-[13px] text-fg-subtle">{LIMIT_LABELS[l.key]?.label}</dt>
              <dd className="tabular text-sm font-medium">
                {l.limit === null || l.limit === undefined ? "Unlimited" : l.limit.toLocaleString("en-IN")}
              </dd>
            </div>
          ))}
        </dl>
      </div>
    </Section>
  );
}

function Mark({ on, label }: { on: boolean; label: string }) {
  return on ? (
    <span className="inline-flex size-5 items-center justify-center rounded-full bg-success-soft text-success">
      <Check className="size-3.5" strokeWidth={3} aria-label={`${label}: included`} />
    </span>
  ) : (
    <span className="inline-flex size-5 items-center justify-center rounded-full bg-surface-2 text-fg-disabled">
      <Minus className="size-3.5" strokeWidth={3} aria-label={`${label}: not included`} />
    </span>
  );
}

function Features({ s }: { s: SubscriptionOut }) {
  return (
    <Section title="Included now">
      <ul className="flex flex-col gap-3">
        {Object.entries(FEATURE_LABELS).map(([key, label]) => {
          const on = Boolean(s.features[key]);
          return (
            <li key={key} className="flex items-center gap-3 text-sm">
              <Mark on={on} label={label} />
              <span className={on ? "text-fg" : "text-fg-subtle"}>{label}</span>
              {s.overrides.includes(key) && <Badge tone="info">Custom</Badge>}
            </li>
          );
        })}
      </ul>
    </Section>
  );
}

// ---- compare plans --------------------------------------------------------------------------------

const ROWS: { key: string; label: string; kind: "limit" | "feature"; unit?: string }[] = [
  { key: "max_students", label: "Active students", kind: "limit" },
  { key: "max_staff", label: "Staff accounts", kind: "limit" },
  { key: "max_admins", label: "Administrator seats", kind: "limit" },
  { key: "max_published_exams_per_year", label: "Exam publications a year", kind: "limit" },
  { key: "history_years", label: "Years of results online", kind: "limit" },
  { key: "max_storage_mb", label: "Storage", kind: "limit", unit: "GB" },
  { key: "custom_branding", label: "Your colours and login page", kind: "feature" },
  { key: "scheduled_publication", label: "Scheduled publication", kind: "feature" },
  { key: "maker_checker_approval", label: "Two-person approval", kind: "feature" },
  { key: "multiple_departments", label: "Multiple departments", kind: "feature" },
  { key: "advanced_analytics", label: "Advanced analytics", kind: "feature" },
  { key: "remove_powered_by", label: "No ScoreCode branding", kind: "feature" },
  { key: "custom_domain", label: "Your own domain", kind: "feature" },
  { key: "api_access", label: "Integration API", kind: "feature" },
];

function cell(p: PublicPlan, row: (typeof ROWS)[number]) {
  if (row.kind === "feature")
    return <Mark on={Boolean(p.features[row.key])} label={`${p.name}: ${row.label}`} />;
  const v = p.limits[row.key];
  if (v === null || v === undefined) return <span className="text-fg">Unlimited</span>;
  const n = row.unit === "GB" ? v / 1024 : v;
  return (
    <span className="tabular text-fg">
      {n.toLocaleString("en-IN")}
      {row.unit ? ` ${row.unit}` : ""}
    </span>
  );
}

function ComparePlans({ s }: { s: SubscriptionOut }) {
  const catalogue = usePlanCatalogue();
  const { branding } = useTenant();
  const plans = catalogue.data?.plans ?? [];
  const current = s.status === "trialing" ? "pro" : s.plan_code;
  return (
    <Section
      title="Compare plans"
      description="Prices are per institution per academic year, plus GST. Upgrades apply at once; downgrades never delete data."
    >
      {catalogue.isPending ? (
        <Skeleton className="h-80 w-full" />
      ) : (
        <>
          <ul className="flex flex-col gap-3 md:hidden" aria-label="Plans">
            {plans.map((p) => {
              const here = p.code === current;
              const included = ROWS.filter((r) => r.kind === "feature" && p.features[r.key]);
              return (
                <li
                  key={p.code}
                  className={cn(
                    "rounded-xl border p-4",
                    here ? "border-brand/40 bg-brand-soft/40" : "border-border",
                  )}
                >
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="flex items-center gap-2 text-[15px] font-semibold text-fg">
                        {p.name}
                        {here && (
                          <Badge tone="brand">{s.status === "trialing" ? "Your trial" : "Current"}</Badge>
                        )}
                      </p>
                      <p className="tabular text-[13px] text-fg-muted">
                        {p.price_paise_yearly ? `${formatRupees(p.price_paise_yearly)} / year` : "Free"}
                      </p>
                    </div>
                    {p.price_paise_yearly && !(here && s.status !== "trialing") ? (
                      <Button size="sm" variant={here ? "primary" : "secondary"} asChild>
                        <a href={salesMailto(`The ${p.name} plan`, branding.display_name)}>Talk to sales</a>
                      </Button>
                    ) : null}
                  </div>
                  <dl className="mt-3 grid gap-x-6 gap-y-1.5 text-[13px] min-[480px]:grid-cols-2">
                    {ROWS.filter((r) => r.kind === "limit").map((r) => (
                      <div key={r.key} className="flex justify-between gap-2">
                        <dt className="text-fg-subtle">{r.label}</dt>
                        <dd>{cell(p, r)}</dd>
                      </div>
                    ))}
                  </dl>
                  {included.length > 0 && (
                    <p className="mt-3 text-[13px] text-fg-muted">
                      <span className="font-medium text-fg">Includes:</span>{" "}
                      {included.map((r) => r.label).join(" · ")}
                    </p>
                  )}
                </li>
              );
            })}
          </ul>
          <div className="-mx-5 hidden overflow-x-auto px-5 md:block">
            <table className="w-full min-w-[640px] border-separate border-spacing-0 text-sm">
              <caption className="sr-only">Plans and what they include</caption>
              <thead>
                <tr>
                  <th className="sticky left-0 z-10 w-48 bg-surface pb-4 text-left align-bottom text-[13px] font-medium text-fg-subtle">
                    &nbsp;
                  </th>
                  {plans.map((p) => {
                    const here = p.code === current;
                    return (
                      <th
                        key={p.code}
                        scope="col"
                        className={cn(
                          "rounded-t-xl px-3 pb-4 pt-3 text-left align-top font-normal",
                          here && "bg-brand-soft/60",
                        )}
                      >
                        <div className="flex items-center gap-2">
                          <span className="text-[15px] font-semibold text-fg">{p.name}</span>
                          {here && (
                            <Badge tone="brand">{s.status === "trialing" ? "Your trial" : "Current"}</Badge>
                          )}
                        </div>
                        <div className="tabular mt-1 text-[13px] text-fg-muted">
                          {p.price_paise_yearly ? `${formatRupees(p.price_paise_yearly)} / year` : "Free"}
                        </div>
                      </th>
                    );
                  })}
                </tr>
              </thead>
              <tbody>
                {ROWS.map((row) => (
                  <tr key={row.key}>
                    <th
                      scope="row"
                      className="sticky left-0 z-10 border-t border-border bg-surface py-2.5 pr-3 text-left text-[13px] font-normal text-fg-muted"
                    >
                      {row.label}
                    </th>
                    {plans.map((p) => (
                      <td
                        key={p.code}
                        className={cn(
                          "border-t border-border px-3 py-2.5",
                          p.code === current && "bg-brand-soft/60",
                        )}
                      >
                        {cell(p, row)}
                      </td>
                    ))}
                  </tr>
                ))}
                <tr>
                  <td className="sticky left-0 bg-surface" />
                  {plans.map((p) => {
                    const here = p.code === current;
                    return (
                      <td
                        key={p.code}
                        className={cn("rounded-b-xl px-3 pb-3 pt-3", here && "bg-brand-soft/60")}
                      >
                        {here && s.status !== "trialing" ? (
                          <span className="text-[13px] text-fg-subtle">Your plan</span>
                        ) : p.price_paise_yearly ? (
                          <Button size="sm" variant={here ? "primary" : "secondary"} asChild>
                            <a href={salesMailto(`The ${p.name} plan`, branding.display_name)}>
                              Talk to sales
                            </a>
                          </Button>
                        ) : null}
                      </td>
                    );
                  })}
                </tr>
              </tbody>
            </table>
          </div>
        </>
      )}
      {s.status === "trialing" && (
        <p className="mt-4 flex items-start gap-2 text-[13px] leading-5 text-fg-muted">
          <Sparkles className="mt-0.5 size-4 shrink-0 text-brand-ink" aria-hidden />
          Your trial includes everything in Pro except your own domain and the integration API, for up to
          1,000 students.
        </p>
      )}
      <p className="mt-4 flex items-start gap-2 text-[13px] leading-5 text-fg-subtle">
        <Info className="mt-0.5 size-4 shrink-0" aria-hidden />
        Universities and groups with several campuses get Enterprise terms with custom limits — write to
        sales@scorecode.in.
      </p>
    </Section>
  );
}

export default function PlanPage() {
  const q = useSubscription();
  const s = q.data;
  const status = s ? (STATUS[s.status] ?? { label: s.status, tone: "info" as const }) : null;
  return (
    <>
      <PageHeader
        title="Plan & usage"
        description="What your plan includes, how much of it you're using, and what's next."
        meta={
          s &&
          status && (
            <>
              <Badge tone="brand">{s.plan_name}</Badge>
              <Badge tone={status.tone} dot>
                {status.label}
              </Badge>
              {s.period_end && s.status !== "trialing" && (
                <span className="text-[13px] text-fg-subtle">Renews or ends {formatDate(s.period_end)}</span>
              )}
            </>
          )
        }
      />
      {q.isPending || !s ? (
        <div className="grid gap-6 lg:grid-cols-2">
          <SkeletonText lines={8} />
          <SkeletonText lines={8} />
        </div>
      ) : (
        <>
          {s.status === "past_due" && (
            <Callout tone="warning" title="Payment is due" className="mb-6">
              Your plan stays active during the grace period. Contact ScoreCode to renew.
            </Callout>
          )}
          <TrialCard s={s} trial={s.trial} />
          <div className="grid gap-6 lg:grid-cols-2">
            <Usage s={s} />
            <Features s={s} />
          </div>
          <div className="mt-6">
            <ComparePlans s={s} />
          </div>
        </>
      )}
    </>
  );
}
