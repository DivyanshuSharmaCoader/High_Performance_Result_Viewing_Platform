import {
  Badge,
  Section,
  Sheet,
  SheetContent,
  StatTile,
  TBody,
  THead,
  Table,
  TableContainer,
  Td,
  Th,
  formatNumber,
  noun,
} from "@scorecode/ui";
import { ChevronRight } from "lucide-react";
import { useState } from "react";

import { trimNum } from "../exams/api";
import type { Bin, ResultStats } from "./api";

/**
 * Exam analytics for administrators (P13.2): headline figures, the distribution, grades, a
 * section-by-section comparison and a drill-down per paper. Loaded as its own chunk, only when there are
 * results to show.
 */

type PaperStats = ResultStats["papers"][number];

const pct = (v: string | null | undefined) => (v === null || v === undefined ? "—" : `${trimNum(v)}%`);
const BELOW = 15; // a section this many points under the overall pass rate is worth a look

export function Histogram({
  bins,
  caption,
  label = "Students by percentage",
}: {
  bins: Bin[];
  caption: string;
  label?: string;
}) {
  const max = Math.max(1, ...bins.map((b) => b.count));
  const range = (b: Bin) => `${b.from}–${b.to === 100 ? 100 : b.to - 1}%`;
  return (
    <figure>
      <ul className="flex h-36 items-end gap-1.5" aria-label={label}>
        {bins.map((b) => (
          <li
            key={b.from}
            className="flex h-full flex-1 flex-col items-center justify-end gap-1"
            aria-label={`${range(b)}: ${formatNumber(b.count)} ${noun(b.count, "student")}`}
          >
            <span className="tabular text-[11px] text-fg-subtle" aria-hidden>
              {b.count || ""}
            </span>
            <span
              aria-hidden
              className="w-full rounded-t bg-brand/75 transition-[height] duration-300"
              style={{ height: `${(b.count / max) * 100}%`, minHeight: b.count ? 2 : 0 }}
            />
          </li>
        ))}
      </ul>
      <div className="mt-1 flex gap-1.5 border-t border-border pt-1 text-[11px] text-fg-subtle" aria-hidden>
        {bins.map((b) => (
          <span key={b.from} className="flex-1 text-center">
            {b.from}
          </span>
        ))}
      </div>
      <figcaption className="mt-1 text-[12px] text-fg-subtle">{caption}</figcaption>
    </figure>
  );
}

function Bar({ value, tone = "brand" }: { value: string | null; tone?: "brand" | "warning" }) {
  const width = value === null ? 0 : Math.max(0, Math.min(100, Number(value)));
  return (
    <span className="hidden h-2 w-28 overflow-hidden rounded-full bg-surface-2 sm:inline-block" aria-hidden>
      <span
        className={`block h-full rounded-full ${tone === "warning" ? "bg-warning" : "bg-brand/70"}`}
        style={{ width: `${width}%` }}
      />
    </span>
  );
}

function Sections({ s }: { s: ResultStats }) {
  const rows = s.cohorts ?? [];
  if (rows.length < 2) return null; // one section: nothing to compare
  const overall = s.pass_percentage === null ? null : Number(s.pass_percentage);
  return (
    <Section title="By section" description="How each section did, against the exam as a whole.">
      <TableContainer>
        <Table>
          <caption className="sr-only">Results by section</caption>
          <THead>
            <tr>
              <Th>Section</Th>
              <Th className="text-right">Students</Th>
              <Th className="text-right">Pass rate</Th>
              <Th className="hidden text-right sm:table-cell">Average</Th>
            </tr>
          </THead>
          <TBody>
            {rows.map((r) => {
              const below =
                overall !== null &&
                r.pass_percentage !== null &&
                overall - Number(r.pass_percentage) >= BELOW;
              return (
                <tr key={r.cohort_id}>
                  <Td>
                    <span className="font-medium">{r.code}</span>{" "}
                    <span className="hidden text-fg-muted sm:inline">{r.name}</span>
                    {below && (
                      <Badge tone="warning" className="ml-2">
                        Below the exam
                      </Badge>
                    )}
                  </Td>
                  <Td className="tabular text-right">
                    {formatNumber(r.students)}
                    {r.appeared !== r.students && (
                      <span className="block text-[11px] text-fg-subtle">
                        {formatNumber(r.appeared)} with a result
                      </span>
                    )}
                  </Td>
                  <Td className="text-right">
                    <span className="inline-flex items-center gap-2">
                      <Bar value={r.pass_percentage} tone={below ? "warning" : "brand"} />
                      <span className="tabular w-14">{pct(r.pass_percentage)}</span>
                    </span>
                  </Td>
                  <Td className="tabular hidden text-right sm:table-cell">{pct(r.average_percentage)}</Td>
                </tr>
              );
            })}
          </TBody>
        </Table>
      </TableContainer>
    </Section>
  );
}

function PaperSheet({ paper, onClose }: { paper: PaperStats | null; onClose: () => void }) {
  return (
    <Sheet open={paper !== null} onOpenChange={(v) => !v && onClose()}>
      <SheetContent
        title={paper ? `${paper.course_code} · ${paper.course_name}` : ""}
        description={paper ? `Out of ${trimNum(paper.max_total)} marks` : undefined}
        className="max-w-xl"
      >
        {paper && (
          <div className="flex flex-col gap-5">
            <div className="grid grid-cols-2 gap-3">
              <StatTile
                label="Pass rate"
                value={pct(paper.pass_percentage)}
                hint={`${formatNumber(paper.passed)} of ${formatNumber(paper.appeared)} passed`}
              />
              <StatTile
                label="Average"
                value={paper.average ? trimNum(paper.average) : "—"}
                hint={[
                  paper.median && `median ${trimNum(paper.median)}`,
                  paper.stdev && `spread ±${trimNum(paper.stdev)}`,
                ]
                  .filter(Boolean)
                  .join(" · ")}
              />
              <StatTile label="Highest" value={trimNum(paper.highest) || "—"} />
              <StatTile label="Lowest" value={trimNum(paper.lowest) || "—"} />
            </div>
            {paper.histogram ? (
              <Histogram
                bins={paper.histogram}
                label={`${paper.course_code} students by percentage`}
                caption="Percentage of the paper's marks (students who sat it)"
              />
            ) : (
              <p className="text-[13px] text-fg-subtle">
                Process the results again to see this paper&apos;s distribution.
              </p>
            )}
            {(paper.absent > 0 || paper.incomplete > 0) && (
              <p className="text-[13px] text-fg-muted">
                {[
                  paper.absent && `${formatNumber(paper.absent)} absent`,
                  paper.incomplete && `${formatNumber(paper.incomplete)} with marks missing`,
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </p>
            )}
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}

export default function ExamAnalytics({ s }: { s: ResultStats }) {
  const o = s.outcomes;
  const [paper, setPaper] = useState<PaperStats | null>(null);
  return (
    <div className="flex flex-col gap-5">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="Pass rate" value={pct(s.pass_percentage)} hint={`${formatNumber(o.pass)} passed`} />
        <StatTile label="Failed" value={formatNumber(o.fail)} />
        <StatTile
          label="Average"
          value={pct(s.average_percentage)}
          hint={[
            s.median_percentage && `median ${trimNum(s.median_percentage)}%`,
            s.stdev_percentage && `spread ±${trimNum(s.stdev_percentage)}`,
          ]
            .filter(Boolean)
            .join(" · ")}
        />
        <StatTile
          label="No result"
          value={formatNumber(o.absent + o.incomplete + o.withheld)}
          hint={[
            o.absent && `${o.absent} absent`,
            o.incomplete && `${o.incomplete} incomplete`,
            o.withheld && `${o.withheld} withheld`,
          ]
            .filter(Boolean)
            .join(" · ")}
        />
      </div>
      <div className="grid gap-5 lg:grid-cols-[1fr_280px]">
        <Section title="Distribution">
          <Histogram bins={s.histogram} caption="Percentage (students with a result)" />
        </Section>
        <Section
          title={s.grades_basis === "paper" ? "Paper grades" : "Grades"}
          description={
            s.grades_basis === "paper" ? "Grades of every paper sat; the exam result is an SGPA." : undefined
          }
        >
          {s.grades.length === 0 ? (
            <p className="text-sm text-fg-subtle">This scheme doesn&apos;t give grades.</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {s.grades.map((g) => {
                const total = s.grades.reduce((n, x) => n + x.count, 0);
                return (
                  <li key={g.grade} className="flex items-center gap-3 text-sm">
                    <span className="w-10 font-semibold">{g.grade}</span>
                    <span className="h-2 flex-1 overflow-hidden rounded-full bg-surface-2" aria-hidden>
                      <span
                        className="block h-full rounded-full bg-brand/70"
                        style={{ width: `${(g.count / Math.max(1, total)) * 100}%` }}
                      />
                    </span>
                    <span className="tabular w-10 text-right text-fg-muted">{g.count}</span>
                  </li>
                );
              })}
            </ul>
          )}
        </Section>
      </div>
      <Sections s={s} />
      <TableContainer>
        <Table>
          <caption className="sr-only">Results by paper. Choose a paper to see its distribution.</caption>
          <THead>
            <tr>
              <Th>Paper</Th>
              <Th className="text-right">Appeared</Th>
              <Th className="text-right">Pass rate</Th>
              <Th className="hidden text-right sm:table-cell">Average</Th>
              <Th className="hidden text-right md:table-cell">Highest</Th>
              <Th className="hidden text-right md:table-cell">Lowest</Th>
              <Th className="hidden text-right lg:table-cell">Absent</Th>
              <Th className="w-8">
                <span className="sr-only">Details</span>
              </Th>
            </tr>
          </THead>
          <TBody>
            {s.papers.map((p) => (
              <tr
                key={p.paper_id}
                className="cursor-pointer hover:bg-surface-2/60"
                onClick={() => setPaper(p)}
              >
                <Td>
                  <button
                    type="button"
                    className="text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand rounded"
                    aria-label={`${p.course_code} ${p.course_name}: details`}
                    onClick={(e) => {
                      e.stopPropagation();
                      setPaper(p);
                    }}
                  >
                    <span className="font-medium">{p.course_code}</span>{" "}
                    <span className="hidden text-fg-muted sm:inline">{p.course_name}</span>
                  </button>
                </Td>
                <Td className="tabular text-right">{formatNumber(p.appeared)}</Td>
                <Td className="tabular text-right">{pct(p.pass_percentage)}</Td>
                <Td className="tabular hidden text-right sm:table-cell">
                  {p.average ? `${trimNum(p.average)}/${trimNum(p.max_total)}` : "—"}
                </Td>
                <Td className="tabular hidden text-right md:table-cell">{trimNum(p.highest) || "—"}</Td>
                <Td className="tabular hidden text-right md:table-cell">{trimNum(p.lowest) || "—"}</Td>
                <Td className="tabular hidden text-right lg:table-cell">{formatNumber(p.absent)}</Td>
                <Td>
                  <ChevronRight className="size-4 text-fg-subtle" aria-hidden />
                </Td>
              </tr>
            ))}
          </TBody>
        </Table>
      </TableContainer>
      <PaperSheet paper={paper} onClose={() => setPaper(null)} />
    </div>
  );
}
