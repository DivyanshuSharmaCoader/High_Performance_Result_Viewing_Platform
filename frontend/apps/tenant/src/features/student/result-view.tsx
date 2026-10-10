import type { ResultPayload, SnapPaper } from "@scorecode/api-client";
import { cn } from "@scorecode/ui";

import { useI18n, type MessageKey } from "../../lib/i18n";

/**
 * One student's result exactly as published — the snapshot payload (schema 1). Administrators preview
 * results with this same component, so what they approve is what students see (docs/03 W8).
 */

type Tone = "success" | "danger" | "neutral" | "warning";
// Labels come from the student catalogue (lib/i18n): English for staff previews, the student's language
// in the portal.
const OUTCOME: Record<string, { label: MessageKey; tone: Tone; note?: MessageKey }> = {
  pass: { label: "outcome.pass", tone: "success" },
  fail: { label: "outcome.fail", tone: "danger", note: "outcome.fail_note" },
  absent: { label: "outcome.absent", tone: "neutral" },
  withheld: { label: "outcome.withheld", tone: "warning", note: "outcome.withheld_note" },
  incomplete: { label: "outcome.incomplete", tone: "warning", note: "outcome.incomplete_note" },
};
const PAPER: Record<string, { label: MessageKey; tone: Tone }> = {
  pass: { label: "paper.pass", tone: "success" },
  fail: { label: "paper.fail", tone: "danger" },
  absent: { label: "paper.absent", tone: "neutral" },
  exempt: { label: "paper.exempt", tone: "neutral" },
  withheld: { label: "paper.withheld", tone: "warning" },
  incomplete: { label: "paper.incomplete", tone: "warning" },
};
const ATTENDANCE: Record<string, MessageKey> = {
  absent: "paper.absent",
  exempt: "paper.exempt",
  malpractice: "paper.withheld",
  withheld: "paper.withheld",
};

const TONE: Record<Tone, string> = {
  success: "bg-success-soft text-success",
  danger: "bg-danger-soft text-danger",
  neutral: "bg-surface-2 text-fg-muted",
  warning: "bg-warning-soft text-warning",
};

export function Pill({ tone, children, className }: { tone: Tone; children: string; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex h-6 items-center rounded-full px-2.5 text-xs font-semibold",
        TONE[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

const pct = (v: string | null | undefined) => (v == null ? null : `${v}%`);
/** Grade-point averages are read with two decimals (9.00, 8.25), whatever the stored precision. */
export const gpa = (v: string) => Number(v).toFixed(2);

function Figure({ label, value, big }: { label: string; value: string; big?: boolean }) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] font-semibold uppercase tracking-[0.06em] text-fg-subtle">{label}</dt>
      <dd className={cn("tabular mt-0.5 font-semibold text-fg", big ? "text-[28px] leading-8" : "text-lg")}>
        {value}
      </dd>
    </div>
  );
}

function PaperCard({ p, average }: { p: SnapPaper; average?: string | null }) {
  const { t } = useI18n();
  const known = PAPER[p.outcome];
  const status = known
    ? { label: t(known.label), tone: known.tone }
    : { label: p.outcome, tone: "neutral" as const };
  const present = p.attendance === "present";
  return (
    <li className="rounded-xl border border-border bg-surface p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[15px] font-semibold leading-5 text-fg">{p.course_name}</p>
          <p className="mt-0.5 text-[12px] text-fg-subtle">
            <span className="font-mono">{p.course_code}</span>
            {p.credits && <> · {t("view.credits", { n: p.credits })}</>}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {p.grade && (
            <span className="tabular rounded-md bg-surface-2 px-2 py-0.5 text-sm font-semibold text-fg">
              {p.grade}
            </span>
          )}
          <Pill tone={status.tone}>{status.label}</Pill>
        </div>
      </div>
      {present ? (
        <ul className="mt-3 flex flex-col gap-2">
          {p.components.map((c) => {
            const failed = p.failed_components.includes(c.code);
            const missing = p.missing_components.includes(c.code) || c.marks == null;
            const ratio = !missing && c.max ? Math.min(1, Number(c.marks) / Number(c.max)) : 0;
            return (
              <li key={c.code}>
                <div className="flex items-baseline justify-between gap-3 text-[13px]">
                  <span className={failed ? "text-danger" : "text-fg-muted"}>
                    {c.label}
                    {failed && (
                      <span className="ml-1.5 text-[11px] font-medium">{t("view.below_minimum")}</span>
                    )}
                  </span>
                  <span className="tabular text-fg">
                    <span className="font-semibold">{missing ? "—" : c.marks}</span>
                    <span className="text-fg-subtle"> / {c.max}</span>
                  </span>
                </div>
                <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-surface-3" aria-hidden>
                  <div
                    className={cn("h-full rounded-full", failed ? "bg-danger-solid" : "bg-brand")}
                    style={{ width: `${Math.round(ratio * 100)}%` }}
                  />
                </div>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="mt-3 text-[13px] text-fg-muted">
          {p.attendance
            ? ATTENDANCE[p.attendance]
              ? t(ATTENDANCE[p.attendance]!)
              : p.attendance
            : t("view.no_marks")}
        </p>
      )}
      {(p.total || average) && (
        <div className="mt-3 flex items-baseline justify-between gap-3 border-t border-border pt-3 text-[13px]">
          <span className="text-fg-muted">
            {t("view.total")}
            {average && (
              <span className="text-fg-subtle"> · {t("view.class_average", { value: average })}</span>
            )}
          </span>
          <span className="tabular font-semibold text-fg">
            {p.total ?? "—"}
            <span className="font-normal text-fg-subtle"> / {p.max_total}</span>
          </span>
        </div>
      )}
    </li>
  );
}

export function StudentResultView({
  payload,
  averages,
}: {
  payload: ResultPayload;
  averages?: Record<string, string | null>; // course code → class average, when the institution shares it
}) {
  const { t } = useI18n();
  const r = payload.result;
  const known = OUTCOME[r.outcome];
  const outcome = known
    ? { label: t(known.label), tone: known.tone, note: known.note && t(known.note) }
    : { label: r.outcome, tone: "neutral" as const, note: undefined };
  const figures = [
    r.sgpa != null ? { label: t("view.sgpa"), value: gpa(r.sgpa) } : null,
    pct(r.percentage) ? { label: t("view.percentage"), value: pct(r.percentage)! } : null,
    r.grade ? { label: t("view.grade"), value: r.grade } : null,
    r.total != null ? { label: t("view.total"), value: `${r.total} / ${r.max_total}` } : null,
    r.rank != null ? { label: t("view.rank"), value: `#${r.rank}` } : null,
  ].filter((f): f is { label: string; value: string } => f !== null);
  const [lead, ...rest] = figures;
  return (
    <article
      aria-label={t("view.result_of", { name: payload.student.full_name })}
      className="flex flex-col gap-4"
    >
      <section className="overflow-hidden rounded-2xl border border-border bg-surface shadow-xs">
        <div
          className={cn(
            "h-1.5",
            outcome.tone === "success"
              ? "bg-success-solid"
              : outcome.tone === "danger"
                ? "bg-danger-solid"
                : "bg-surface-3",
          )}
        />
        <div className="p-5 sm:p-6">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="text-[12px] font-medium text-fg-subtle">
                {payload.exam.term} · {payload.exam.session}
              </p>
              <h2 className="mt-0.5 text-xl font-semibold tracking-[-0.01em] text-fg">{payload.exam.name}</h2>
              <p className="mt-1 text-[13px] text-fg-muted">
                {payload.student.full_name} ·{" "}
                <span className="font-mono">{payload.student.enrollment_no}</span> ·{" "}
                {payload.student.cohort.code}
              </p>
            </div>
            <Pill tone={outcome.tone} className="h-7 px-3 text-[13px]">
              {outcome.label}
            </Pill>
          </div>
          {figures.length > 0 && (
            <dl className="mt-5 grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-4">
              {lead && <Figure {...lead} big />}
              {rest.map((f) => (
                <Figure key={f.label} {...f} />
              ))}
            </dl>
          )}
          {outcome.note && <p className="mt-4 text-[13px] text-fg-muted">{outcome.note}</p>}
          {r.credits_attempted && r.credits_attempted !== "0" && (
            <p className="mt-3 text-[12px] text-fg-subtle">
              {t("view.credits_earned", { earned: r.credits_earned ?? "0", attempted: r.credits_attempted })}
            </p>
          )}
        </div>
      </section>
      <section aria-label={t("view.marks_by_paper")}>
        <h3 className="mb-2 px-1 text-[13px] font-semibold text-fg-muted">{t("view.marks_by_paper")}</h3>
        <ul className="grid gap-3 sm:grid-cols-2">
          {payload.papers.map((p) => (
            <PaperCard key={p.course_code} p={p} average={averages?.[p.course_code]} />
          ))}
        </ul>
      </section>
      {r.notes.length > 0 && (
        <ul className="list-disc pl-5 text-[13px] text-fg-muted">
          {r.notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      )}
    </article>
  );
}
