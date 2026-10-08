import { formatNumber, noun } from "@scorecode/ui";

interface Bin {
  from: number;
  to: number;
  count: number;
}

export interface FullStats {
  students?: number;
  pass_percentage?: string | null;
  average_percentage?: string | null;
  median_percentage?: string | null;
  histogram?: Bin[];
}

const trim = (v: string) => v.replace(/\.0+$|(\.\d*[1-9])0+$/, "$1");

/**
 * Where the student stands, when the institution shares full statistics (docs/12, P13.3). Only aggregates:
 * nobody else's result can be worked out from it.
 */
export function ClassStats({ stats, percentage }: { stats: FullStats; percentage: string | null }) {
  const bins = stats.histogram ?? [];
  if (bins.length === 0) return null;
  const mine = percentage === null ? -1 : Math.min(9, Math.max(0, Math.floor(Number(percentage) / 10)));
  const max = Math.max(1, ...bins.map((b) => b.count));
  const facts = [
    stats.students !== undefined && `${formatNumber(stats.students)} ${noun(stats.students, "student")}`,
    stats.pass_percentage && `${trim(stats.pass_percentage)}% passed`,
    stats.average_percentage && `average ${trim(stats.average_percentage)}%`,
    stats.median_percentage && `median ${trim(stats.median_percentage)}%`,
  ].filter(Boolean);
  return (
    <section
      aria-labelledby="class-stats"
      className="mt-5 rounded-2xl border border-border bg-surface p-4 sm:p-5 print:hidden"
    >
      <h2 id="class-stats" className="text-sm font-semibold text-fg">
        How the class did
      </h2>
      <p className="text-[13px] text-fg-muted">{facts.join(" · ")}</p>
      <ul className="mt-4 flex h-24 items-end gap-1" aria-label="Students by percentage">
        {bins.map((b, i) => (
          <li
            key={b.from}
            className="flex h-full flex-1 flex-col justify-end"
            aria-label={`${b.from}–${b.to === 100 ? 100 : b.to - 1}%: ${formatNumber(b.count)} ${noun(b.count, "student")}${i === mine ? " (you)" : ""}`}
          >
            <span
              aria-hidden
              className={`w-full rounded-t ${i === mine ? "bg-brand" : "bg-surface-3"}`}
              style={{ height: `${(b.count / max) * 100}%`, minHeight: b.count ? 2 : 0 }}
            />
          </li>
        ))}
      </ul>
      <div className="mt-1 flex justify-between text-[11px] text-fg-subtle" aria-hidden>
        <span>0%</span>
        {mine >= 0 && <span className="font-medium text-brand-ink">Your band is highlighted</span>}
        <span>100%</span>
      </div>
    </section>
  );
}
