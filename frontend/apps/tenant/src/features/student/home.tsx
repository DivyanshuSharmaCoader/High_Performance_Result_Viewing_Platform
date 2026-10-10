import type { MyResultItem } from "@scorecode/api-client";
import { EmptyState, Skeleton } from "@scorecode/ui";
import { ChevronRight, FileText, Sparkles } from "lucide-react";
import { Link } from "react-router";

import { useI18n, type MessageKey } from "../../lib/i18n";
import { useSession } from "../../lib/session";
import { useTenant } from "../../lib/tenant";
import { useMyResults } from "./api";
import { Pill, gpa } from "./result-view";

const OUTCOME = {
  pass: { label: "outcome.pass", tone: "success" },
  fail: { label: "outcome.fail", tone: "danger" },
  absent: { label: "outcome.absent", tone: "neutral" },
  withheld: { label: "outcome.withheld", tone: "warning" },
  incomplete: { label: "outcome.incomplete", tone: "warning" },
} as const satisfies Record<string, { label: MessageKey; tone: string }>;

function useOutcome() {
  const { t } = useI18n();
  return (outcome: string) => {
    const o = OUTCOME[outcome as keyof typeof OUTCOME];
    return o ? { label: t(o.label), tone: o.tone } : { label: outcome, tone: "neutral" as const };
  };
}

function useHeadline() {
  const { t } = useI18n();
  return (r: MyResultItem) =>
    r.sgpa != null
      ? { label: t("view.sgpa"), value: gpa(r.sgpa) }
      : r.percentage != null
        ? { label: t("view.percentage"), value: `${r.percentage}%` }
        : null;
}

function LatestCard({ r }: { r: MyResultItem }) {
  const { t, relative } = useI18n();
  const o = useOutcome()(r.outcome);
  const h = useHeadline()(r);
  return (
    <Link
      to={`/me/results/${r.publication_id}`}
      className="group relative block overflow-hidden rounded-2xl border border-border bg-surface p-5 shadow-xs transition-shadow hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand sm:p-6"
    >
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(90%_120%_at_100%_0%,color-mix(in_oklab,var(--sc-brand)_10%,transparent),transparent)]"
      />
      <div className="relative">
        <p className="inline-flex items-center gap-1.5 text-[12px] font-semibold uppercase tracking-[0.06em] text-brand-ink">
          <Sparkles className="size-3.5" aria-hidden /> {t("home.latest")}
        </p>
        <div className="mt-2 flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-xl font-semibold tracking-[-0.01em] text-fg">{r.exam.name}</h2>
            <p className="mt-0.5 text-[13px] text-fg-subtle">
              {r.exam.term} · {r.exam.session} · {t("home.published", { when: relative(r.published_at) })}
              {r.revised && ` · ${t("home.revised")}`}
            </p>
          </div>
          <Pill tone={o.tone}>{o.label}</Pill>
        </div>
        <div className="mt-5 flex items-end justify-between gap-4">
          {h ? (
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-fg-subtle">
                {h.label}
              </p>
              <p className="tabular text-[34px] font-semibold leading-10 text-fg">{h.value}</p>
            </div>
          ) : (
            <span />
          )}
          <span className="inline-flex items-center gap-1 text-sm font-medium text-brand-ink">
            {t("home.see_full")}{" "}
            <ChevronRight className="size-4 transition-transform group-hover:translate-x-0.5" />
          </span>
        </div>
      </div>
    </Link>
  );
}

export default function StudentHome() {
  const { t, date } = useI18n();
  const outcomeOf = useOutcome();
  const headline = useHeadline();
  const me = useSession();
  const { branding } = useTenant();
  const results = useMyResults();
  const first = me.full_name.split(" ")[0] ?? me.full_name;
  const [latest, ...older] = results.data ?? [];
  return (
    <>
      <h1 className="text-[22px] font-semibold tracking-[-0.01em] text-fg">
        {t("home.hello", { name: first })}
      </h1>
      <p className="mt-1 text-sm text-fg-subtle">
        {t("home.enrollment_no")} <span className="font-mono text-fg-muted">{me.login_id}</span>
      </p>
      <div className="mt-6 flex flex-col gap-6">
        {results.isPending ? (
          <Skeleton className="h-44 w-full rounded-2xl" />
        ) : !latest ? (
          <div className="rounded-xl border border-border bg-surface">
            <EmptyState
              icon={<FileText />}
              title={t("home.no_results")}
              description={t("home.no_results_desc", {
                institution: branding.short_name ?? branding.display_name,
              })}
            />
          </div>
        ) : (
          <LatestCard r={latest} />
        )}
        {older.length > 0 && (
          <section aria-labelledby="history">
            <h2 id="history" className="mb-2 px-1 text-[13px] font-semibold text-fg-muted">
              {t("home.earlier")}
            </h2>
            <ul className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-surface">
              {older.map((r) => {
                const o = outcomeOf(r.outcome);
                const h = headline(r);
                return (
                  <li key={r.publication_id}>
                    <Link
                      to={`/me/results/${r.publication_id}`}
                      className="flex items-center gap-3 px-4 py-3.5 hover:bg-surface-2/60 focus-visible:bg-surface-2/60 focus-visible:outline-none"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium text-fg">{r.exam.name}</p>
                        <p className="text-[12px] text-fg-subtle">
                          {r.exam.session} · {date(r.published_at)}
                        </p>
                      </div>
                      {h && <span className="tabular text-sm font-semibold text-fg">{h.value}</span>}
                      <Pill tone={o.tone}>{o.label}</Pill>
                      <ChevronRight className="size-4 shrink-0 text-fg-subtle" aria-hidden />
                    </Link>
                  </li>
                );
              })}
            </ul>
          </section>
        )}
      </div>
    </>
  );
}
