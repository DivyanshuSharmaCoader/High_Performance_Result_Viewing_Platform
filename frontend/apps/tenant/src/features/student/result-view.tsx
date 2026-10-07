import type { ResultPayload, SnapPaper } from "@scorecode/api-client";
import { cn } from "@scorecode/ui";

/**
 * One student's result exactly as published — the snapshot payload (schema 1). Administrators preview
 * results with this same component, so what they approve is what students see (docs/03 W8).
 */

type Tone = "success" | "danger" | "neutral" | "warning";
const OUTCOME: Record<string, { label: string; tone: Tone; note?: string }> = {
  pass: { label: "Passed", tone: "success" },
  fail: {
    label: "Not passed",
    tone: "danger",
    note: "Talk to your institution about re-evaluation or a supplementary exam.",
  },
  absent: { label: "Absent", tone: "neutral" },
  withheld: {
    label: "Result withheld",
    tone: "warning",
    note: "Your institution will tell you why and what happens next.",
  },
  incomplete: {
    label: "Incomplete",
    tone: "warning",
    note: "Some marks weren't entered. Contact your institution.",
  },
};
const PAPER: Record<string, { label: string; tone: Tone }> = {
  pass: { label: "Pass", tone: "success" },
  fail: { label: "Fail", tone: "danger" },
  absent: { label: "Absent", tone: "neutral" },
  exempt: { label: "Exempt", tone: "neutral" },
  withheld: { label: "Withheld", tone: "warning" },
  incomplete: { label: "Incomplete", tone: "warning" },
};
const ATTENDANCE: Record<string, string> = {
  absent: "Absent",
  exempt: "Exempt",
  malpractice: "Withheld",
  withheld: "Withheld",
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
  const status = PAPER[p.outcome] ?? { label: p.outcome, tone: "neutral" as const };
  const present = p.attendance === "present";
  return (
    <li className="rounded-xl border border-border bg-surface p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[15px] font-semibold leading-5 text-fg">{p.course_name}</p>
          <p className="mt-0.5 text-[12px] text-fg-subtle">
            <span className="font-mono">{p.course_code}</span>
            {p.credits && <> · {p.credits} credits</>}
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
                    {failed && <span className="ml-1.5 text-[11px] font-medium">below the minimum</span>}
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
          {p.attendance ? (ATTENDANCE[p.attendance] ?? p.attendance) : "No marks entered"}
        </p>
      )}
      {(p.total || average) && (
        <div className="mt-3 flex items-baseline justify-between gap-3 border-t border-border pt-3 text-[13px]">
          <span className="text-fg-muted">
            Total{average && <span className="text-fg-subtle"> · class average {average}</span>}
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
  const r = payload.result;
  const outcome = OUTCOME[r.outcome] ?? { label: r.outcome, tone: "neutral" as const };
  const figures = [
    r.sgpa != null ? { label: "SGPA", value: gpa(r.sgpa) } : null,
    pct(r.percentage) ? { label: "Percentage", value: pct(r.percentage)! } : null,
    r.grade ? { label: "Grade", value: r.grade } : null,
    r.total != null ? { label: "Total", value: `${r.total} / ${r.max_total}` } : null,
    r.rank != null ? { label: "Rank", value: `#${r.rank}` } : null,
  ].filter((f): f is { label: string; value: string } => f !== null);
  const [lead, ...rest] = figures;
  return (
    <article aria-label={`Result of ${payload.student.full_name}`} className="flex flex-col gap-4">
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
              Credits earned {r.credits_earned ?? "0"} of {r.credits_attempted}
            </p>
          )}
        </div>
      </section>
      <section aria-label="Marks by paper">
        <h3 className="mb-2 px-1 text-[13px] font-semibold text-fg-muted">Marks by paper</h3>
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
