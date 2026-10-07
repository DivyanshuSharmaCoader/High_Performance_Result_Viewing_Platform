import {
  api,
  ApiError,
  newIdempotencyKey,
  type ResultOutcome,
  type ResultsOverview,
} from "@scorecode/api-client";
import {
  Badge,
  Button,
  Callout,
  ConfirmDialog,
  EmptyState,
  Input,
  LoadMore,
  Section,
  Segmented,
  Sheet,
  SheetContent,
  Skeleton,
  Spinner,
  StatTile,
  TBody,
  THead,
  Table,
  TableContainer,
  TableSkeletonRows,
  Td,
  Th,
  formatDateTime,
  formatNumber,
  formatRelative,
  noun,
} from "@scorecode/ui";
import { useMutation } from "@tanstack/react-query";
import {
  AlertTriangle,
  BadgeCheck,
  Calculator,
  CheckCircle2,
  ChevronRight,
  Info,
  RotateCcw,
  Search,
  Undo2,
  XCircle,
} from "lucide-react";
import { useDeferredValue, useState } from "react";
import { Link, useParams } from "react-router";

import { useReauth } from "../../components/reauth";
import { toastError } from "../../lib/forms";
import { trimNum, useExam } from "../exams/api";
import {
  OUTCOME,
  anomaliesOf,
  resultsUrl,
  statsOf,
  useResultStudent,
  useResultStudents,
  useResults,
  useSetResults,
  type Anomaly,
  type ResultStats,
} from "./api";
import { ResultCard, type PaperMeta } from "./card";

type Pending = "process" | "approve" | "reject" | "revoke" | "discard" | null;

const pct = (v: string | null | undefined) => (v === null || v === undefined ? "—" : `${trimNum(v)}%`);

// ---- run status and actions ---------------------------------------------------------------------

function RunPanel({ o }: { o: ResultsOverview }) {
  const setResults = useSetResults(o.exam_id);
  const withReauth = useReauth();
  const [pending, setPending] = useState<Pending>(null);
  const [processKey, setProcessKey] = useState("");
  const run = o.run;
  const url = resultsUrl(o.exam_id);
  const act = useMutation({
    mutationFn: async ({ action, reason }: { action: Exclude<Pending, null>; reason?: string }) => {
      switch (action) {
        case "process":
          return api.post<ResultsOverview>(
            `${url}/process`,
            { override_reason: reason || null },
            { idempotencyKey: processKey },
          );
        case "approve":
          return withReauth(() => api.post<ResultsOverview>(`${url}/approve`, { run_id: run?.id }));
        case "reject":
          return withReauth(() => api.post<ResultsOverview>(`${url}/reject`, { run_id: run?.id, reason }));
        case "revoke":
          return withReauth(() => api.post<ResultsOverview>(`${url}/revoke`, { reason }));
        case "discard":
          return api.post<ResultsOverview>(`${url}/discard`, { reason });
      }
    },
    onSuccess: (next) => {
      setPending(null);
      setResults(next);
    },
    onError: (e) => {
      setPending(null);
      if (!(e instanceof ApiError && e.code === "reauth-cancelled")) toastError(e);
    },
  });
  const open = (p: Exclude<Pending, null>) => {
    if (p === "process") setProcessKey(newIdempotencyKey());
    setPending(p);
  };
  const a = o.actions;
  const outcomes = (statsOf(o)?.outcomes ?? {}) as Partial<Record<ResultOutcome, number>>;
  const summary = run
    ? `${formatNumber(run.students)} ${noun(run.students, "student")}: ${formatNumber(outcomes.pass ?? 0)} pass, ${formatNumber(outcomes.fail ?? 0)} fail`
    : "";

  let body;
  if (!run) {
    body =
      o.exam_status === "draft" || o.exam_status === "marks_entry_open" ? (
        <EmptyState
          compact
          icon={<Calculator />}
          title="Not ready to process yet"
          description="Close marks entry when every paper is in; then process results here."
          action={
            <Button variant="secondary" size="sm" asChild>
              <Link to={`/admin/exams/${o.exam_id}`}>Go to setup</Link>
            </Button>
          }
        />
      ) : (
        <p className="text-sm text-fg-muted">
          Marks entry is closed. Processing computes every student&apos;s result with the exam&apos;s grading
          scheme — nothing is visible to students until you approve and publish.
        </p>
      );
  } else if (run.status === "running") {
    body = (
      <div className="flex items-center gap-3 py-2 text-sm text-fg" role="status" aria-live="polite">
        <Spinner className="size-5" label="" /> Processing results (revision {run.revision})… This usually
        takes a few seconds.
      </div>
    );
  } else {
    body = (
      <div className="flex flex-col gap-3">
        {run.status === "failed" && (
          <Callout tone="danger" title="Processing didn't finish">
            {run.error_detail} Nothing was saved; fix the cause and process again.
          </Callout>
        )}
        {run.status === "stale" && (
          <Callout tone="warning" title="These results are out of date">
            Marks changed after processing. Process again before anyone can approve them.
          </Callout>
        )}
        {run.status === "approved" && (
          <Callout tone="success" title="Approved">
            {o.approvals[0]?.decided_by_name ?? "An administrator"} approved revision {run.revision}
            {o.approvals[0] && <> on {formatDateTime(o.approvals[0].created_at)}</>}. Marks are locked.
          </Callout>
        )}
        <p className="text-[13px] text-fg-subtle">
          Revision {run.revision} · processed {formatRelative(run.finished_at ?? run.created_at)}
          {run.started_by_name && <> by {run.started_by_name}</>}
          {run.scheme && (
            <>
              {" "}
              · {run.scheme.name} v{run.scheme.version}
            </>
          )}
          {run.status !== "failed" && <> · {summary}</>}
          {run.override_reason && <> · processed early: “{run.override_reason}”</>}
        </p>
        {run.content_hash && run.status !== "failed" && (
          <p className="text-[12px] text-fg-subtle">
            Fingerprint <span className="font-mono">{run.content_hash.slice(0, 12)}</span> — the approval
            records it, so what is published can be proven to match.
          </p>
        )}
      </div>
    );
  }

  return (
    <Section
      title="Results"
      actions={
        <div className="flex flex-wrap gap-2">
          {a.can_discard && (
            <Button size="sm" variant="ghost" leadingIcon={<Undo2 />} onClick={() => open("discard")}>
              Back to marks entry
            </Button>
          )}
          {a.can_process && (
            <Button
              size="sm"
              variant={run && run.status === "completed" ? "secondary" : "primary"}
              leadingIcon={run ? <RotateCcw /> : <Calculator />}
              onClick={() => open("process")}
            >
              {run ? "Process again" : "Process results"}
            </Button>
          )}
          {a.can_reject && (
            <Button size="sm" variant="secondary" leadingIcon={<XCircle />} onClick={() => open("reject")}>
              Reject
            </Button>
          )}
          {(a.can_approve || a.approve_blocked_reason) && (
            <Button
              size="sm"
              leadingIcon={<BadgeCheck />}
              disabled={!a.can_approve}
              title={a.approve_blocked_reason ?? undefined}
              onClick={() => open("approve")}
            >
              Approve results
            </Button>
          )}
          {a.can_revoke && (
            <Button size="sm" variant="secondary" leadingIcon={<Undo2 />} onClick={() => open("revoke")}>
              Revoke approval
            </Button>
          )}
        </div>
      }
    >
      {body}
      {a.approve_blocked_reason && (
        <p className="mt-3 text-[13px] text-fg-muted">
          <Info className="mr-1 inline size-4 align-text-bottom" aria-hidden />
          {a.approve_blocked_reason}
        </p>
      )}
      {o.unsubmitted.length > 0 && a.can_process && (!run || run.status !== "completed") && (
        <Callout tone="warning" title="Not every paper is submitted" className="mt-3">
          {o.unsubmitted
            .slice(0, 6)
            .map((u) => `${u.course_code} · ${u.cohort_code}`)
            .join(", ")}
          {o.unsubmitted.length > 6 && ` and ${o.unsubmitted.length - 6} more`}. You can wait for faculty, or
          process now and give a reason.
        </Callout>
      )}
      <ConfirmDialog
        open={pending === "process"}
        onOpenChange={(v) => !v && setPending(null)}
        title={run ? "Process the results again?" : "Process results?"}
        description={
          o.unsubmitted.length > 0
            ? `${noun(o.unsubmitted.length, "A paper isn't", `${o.unsubmitted.length} papers aren't`)} submitted yet. Processing now is recorded with your reason.`
            : "Every student's result is computed with the latest version of the grading scheme. You can process again any time before approval."
        }
        confirmLabel={run ? "Process again" : "Process results"}
        requireReason={o.unsubmitted.length > 0}
        reasonLabel="Why process before every paper is submitted?"
        loading={act.isPending}
        onConfirm={(reason) => act.mutate({ action: "process", reason })}
      />
      <ConfirmDialog
        open={pending === "approve"}
        onOpenChange={(v) => !v && setPending(null)}
        title={`Approve revision ${run?.revision ?? ""}?`}
        description={`${summary}. Approving locks every paper's marks and records this exact result set, ready to publish.`}
        confirmLabel="Approve results"
        loading={act.isPending}
        onConfirm={() => act.mutate({ action: "approve" })}
      />
      <ConfirmDialog
        open={pending === "reject"}
        onOpenChange={(v) => !v && setPending(null)}
        title="Reject these results?"
        description="Your note is recorded. The results stay processed until marks are corrected and processed again."
        confirmLabel="Reject"
        requireReason
        reasonLabel="What needs fixing?"
        loading={act.isPending}
        onConfirm={(reason) => act.mutate({ action: "reject", reason })}
      />
      <ConfirmDialog
        open={pending === "revoke"}
        onOpenChange={(v) => !v && setPending(null)}
        title="Revoke the approval?"
        description="Papers unlock and the results need approving again before they can be published."
        confirmLabel="Revoke approval"
        variant="danger"
        requireReason
        loading={act.isPending}
        onConfirm={(reason) => act.mutate({ action: "revoke", reason })}
      />
      <ConfirmDialog
        open={pending === "discard"}
        onOpenChange={(v) => !v && setPending(null)}
        title="Go back to marks entry?"
        description="These results are set aside (kept for the record). Process again after the marks are fixed."
        confirmLabel="Back to marks entry"
        requireReason
        loading={act.isPending}
        onConfirm={(reason) => act.mutate({ action: "discard", reason })}
      />
    </Section>
  );
}

// ---- statistics ---------------------------------------------------------------------------------

function Histogram({ bins }: { bins: ResultStats["histogram"] }) {
  const max = Math.max(1, ...bins.map((b) => b.count));
  const label = (b: { from: number; to: number }) => `${b.from}–${b.to === 100 ? 100 : b.to - 1}%`;
  return (
    <figure>
      <ul className="flex h-36 items-end gap-1.5" aria-label="Students by percentage">
        {bins.map((b) => (
          <li
            key={b.from}
            className="flex h-full flex-1 flex-col items-center justify-end gap-1"
            aria-label={`${label(b)}: ${formatNumber(b.count)} ${noun(b.count, "student")}`}
          >
            <span className="tabular text-[11px] text-fg-subtle" aria-hidden>
              {b.count || ""}
            </span>
            <span
              aria-hidden
              className="w-full rounded-t bg-brand/75"
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
      <figcaption className="mt-1 text-[12px] text-fg-subtle">Percentage (students with a result)</figcaption>
    </figure>
  );
}

function Stats({ s }: { s: ResultStats }) {
  const o = s.outcomes;
  return (
    <div className="flex flex-col gap-5">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="Pass rate" value={pct(s.pass_percentage)} hint={`${formatNumber(o.pass)} passed`} />
        <StatTile label="Failed" value={formatNumber(o.fail)} />
        <StatTile
          label="Average"
          value={pct(s.average_percentage)}
          hint={s.median_percentage ? `median ${trimNum(s.median_percentage)}%` : undefined}
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
          <Histogram bins={s.histogram} />
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
      <TableContainer>
        <Table>
          <caption className="sr-only">Results by paper</caption>
          <THead>
            <tr>
              <Th>Paper</Th>
              <Th className="text-right">Appeared</Th>
              <Th className="text-right">Pass rate</Th>
              <Th className="hidden text-right sm:table-cell">Average</Th>
              <Th className="hidden text-right md:table-cell">Highest</Th>
              <Th className="hidden text-right md:table-cell">Lowest</Th>
              <Th className="hidden text-right lg:table-cell">Absent</Th>
            </tr>
          </THead>
          <TBody>
            {s.papers.map((p) => (
              <tr key={p.paper_id}>
                <Td>
                  <span className="font-medium">{p.course_code}</span>{" "}
                  <span className="hidden text-fg-muted sm:inline">{p.course_name}</span>
                </Td>
                <Td className="tabular text-right">{formatNumber(p.appeared)}</Td>
                <Td className="tabular text-right">{pct(p.pass_percentage)}</Td>
                <Td className="tabular hidden text-right sm:table-cell">
                  {p.average ? `${trimNum(p.average)}/${trimNum(p.max_total)}` : "—"}
                </Td>
                <Td className="tabular hidden text-right md:table-cell">{trimNum(p.highest) || "—"}</Td>
                <Td className="tabular hidden text-right md:table-cell">{trimNum(p.lowest) || "—"}</Td>
                <Td className="tabular hidden text-right lg:table-cell">{formatNumber(p.absent)}</Td>
              </tr>
            ))}
          </TBody>
        </Table>
      </TableContainer>
    </div>
  );
}

// ---- anomalies ----------------------------------------------------------------------------------

function Anomalies({ items, onOpen }: { items: Anomaly[]; onOpen: (studentId: string) => void }) {
  if (items.length === 0) {
    return (
      <Section title="Worth a look">
        <p className="flex items-center gap-2 text-sm text-fg-muted">
          <CheckCircle2 className="size-4 text-success" aria-hidden /> Nothing unusual: every student has
          marks, and nobody scored full marks everywhere.
        </p>
      </Section>
    );
  }
  return (
    <Section title="Worth a look" description="Check these before approving. They don't block approval.">
      <div className="divide-y divide-border rounded-lg border border-border">
        {items.map((a) => (
          <details key={a.code} className="group" open={a.severity === "warning" && a.count <= 5}>
            <summary className="flex cursor-pointer list-none items-center gap-3 px-4 py-3 text-sm">
              <ChevronRight
                className="size-4 shrink-0 text-fg-subtle transition-transform group-open:rotate-90"
                aria-hidden
              />
              {a.severity === "warning" ? (
                <AlertTriangle className="size-4 shrink-0 text-warning" aria-label="Warning" />
              ) : (
                <Info className="size-4 shrink-0 text-info" aria-label="Note" />
              )}
              <span className="flex-1 font-medium text-fg">{a.title}</span>
              <Badge tone={a.severity === "warning" ? "warning" : "neutral"}>{formatNumber(a.count)}</Badge>
            </summary>
            <ul className="flex flex-col gap-1 px-4 pb-3 pl-11 text-[13px]">
              {a.items.map((i, n) => (
                <li key={i.student_id ?? n} className="flex flex-wrap items-baseline gap-x-2">
                  {i.student_id ? (
                    <button
                      type="button"
                      className="font-mono text-brand-ink hover:underline"
                      onClick={() => onOpen(i.student_id!)}
                    >
                      {i.enrollment_no}
                    </button>
                  ) : null}
                  {i.full_name && <span className="text-fg">{i.full_name}</span>}
                  <span className="text-fg-muted">{i.detail}</span>
                </li>
              ))}
              {a.count > a.items.length && (
                <li className="text-fg-subtle">
                  …and {formatNumber(a.count - a.items.length)} more (filter the student list below).
                </li>
              )}
            </ul>
          </details>
        ))}
      </div>
    </Section>
  );
}

// ---- students -----------------------------------------------------------------------------------

const FILTERS: { value: ResultOutcome | ""; label: string }[] = [
  { value: "", label: "All" },
  { value: "pass", label: "Pass" },
  { value: "fail", label: "Fail" },
  { value: "absent", label: "Absent" },
  { value: "incomplete", label: "Incomplete" },
  { value: "withheld", label: "Withheld" },
];

function Students({ o, onOpen }: { o: ResultsOverview; onOpen: (studentId: string) => void }) {
  const [q, setQ] = useState("");
  const [outcome, setOutcome] = useState<ResultOutcome | "">("");
  const deferred = useDeferredValue(q);
  const counts = (statsOf(o)?.outcomes ?? {}) as Partial<Record<ResultOutcome, number>>;
  const list = useResultStudents(o.exam_id, o.run?.id ?? "", { q: deferred, outcome });
  const rows = list.data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <Section title="Students">
      <div className="mb-3 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div className="max-w-full overflow-x-auto">
          <Segmented
            label="Show"
            value={outcome}
            onChange={setOutcome}
            options={FILTERS.map((f) => ({
              ...f,
              count: f.value ? counts[f.value] : o.run?.students,
            }))}
          />
        </div>
        <div className="relative md:w-72">
          <Search
            className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-fg-subtle"
            aria-hidden
          />
          <Input
            aria-label="Search students"
            placeholder="Enrollment no. or name"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            className="pl-9"
          />
        </div>
      </div>
      <TableContainer>
        <Table>
          <THead>
            <tr>
              <Th>Student</Th>
              <Th className="hidden sm:table-cell">Cohort</Th>
              <Th className="hidden text-right sm:table-cell">Total</Th>
              <Th className="text-right">%</Th>
              <Th className="hidden text-center md:table-cell">Grade / SGPA</Th>
              <Th className="text-right">Result</Th>
            </tr>
          </THead>
          <TBody>
            {list.isPending ? (
              <TableSkeletonRows cols={6} rows={6} />
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={6}>
                  <EmptyState compact title="No students match" description="Try another search or filter." />
                </td>
              </tr>
            ) : (
              rows.map((r) => (
                <tr
                  key={r.student_id}
                  className="cursor-pointer hover:bg-surface-2/60"
                  onClick={() => onOpen(r.student_id)}
                >
                  <Td className="max-w-0 w-full">
                    <button
                      type="button"
                      className="block w-full truncate text-left font-medium text-fg hover:underline"
                      onClick={(e) => {
                        e.stopPropagation();
                        onOpen(r.student_id);
                      }}
                    >
                      {r.full_name}
                    </button>
                    <span className="font-mono text-[12px] text-fg-subtle">{r.enrollment_no}</span>
                  </Td>
                  <Td className="hidden whitespace-nowrap text-fg-muted sm:table-cell">{r.cohort_code}</Td>
                  <Td className="tabular hidden whitespace-nowrap text-right sm:table-cell">
                    {r.total !== null ? `${trimNum(r.total)}/${trimNum(r.max_total)}` : "—"}
                  </Td>
                  <Td className="tabular text-right">
                    {r.percentage !== null ? trimNum(r.percentage) : "—"}
                  </Td>
                  <Td className="hidden text-center font-semibold md:table-cell">
                    {r.sgpa !== null ? trimNum(r.sgpa) : (r.grade ?? "—")}
                  </Td>
                  <Td className="text-right">
                    <Badge tone={OUTCOME[r.outcome].tone}>{OUTCOME[r.outcome].label}</Badge>
                  </Td>
                </tr>
              ))
            )}
          </TBody>
        </Table>
      </TableContainer>
      <LoadMore
        hasMore={Boolean(list.hasNextPage)}
        loading={list.isFetchingNextPage}
        onLoadMore={() => void list.fetchNextPage()}
      />
    </Section>
  );
}

function StudentSheet({
  examId,
  runId,
  studentId,
  papers,
  onClose,
}: {
  examId: string;
  runId: string;
  studentId: string | null;
  papers: Map<string, PaperMeta>;
  onClose: () => void;
}) {
  const q = useResultStudent(examId, runId, studentId);
  return (
    <Sheet open={Boolean(studentId)} onOpenChange={(v) => !v && onClose()}>
      <SheetContent
        title="Result preview"
        description="Exactly what the student will see once these results are published."
        className="max-w-2xl"
      >
        {q.isPending ? (
          <Skeleton className="h-64 w-full" />
        ) : q.error ? (
          <Callout tone="danger">This result couldn&apos;t be loaded.</Callout>
        ) : (
          <ResultCard result={q.data} papers={papers} />
        )}
      </SheetContent>
    </Sheet>
  );
}

// ---- history ------------------------------------------------------------------------------------

const DECISION = {
  approved: { label: "Approved", tone: "success" },
  rejected: { label: "Rejected", tone: "danger" },
  revoked: { label: "Approval revoked", tone: "warning" },
} as const;

const RUN_STATUS = {
  running: "Processing",
  completed: "Waiting for approval",
  failed: "Failed",
  stale: "Out of date",
  approved: "Approved",
  published: "Published",
} as const;

function History({ o }: { o: ResultsOverview }) {
  if (o.runs.length === 0) return null;
  return (
    <Section title="History">
      <ol className="flex flex-col gap-3 text-sm">
        {o.approvals.map((a) => (
          <li key={a.id} className="flex flex-wrap items-baseline gap-x-2">
            <Badge tone={DECISION[a.decision].tone}>{DECISION[a.decision].label}</Badge>
            <span className="text-fg">
              Revision {a.revision} by {a.decided_by_name ?? "an administrator"}
            </span>
            <span className="text-fg-subtle">{formatDateTime(a.created_at)}</span>
            {a.comment && <span className="w-full text-fg-muted">“{a.comment}”</span>}
          </li>
        ))}
        {o.runs.map((r) => (
          <li key={r.id} className="flex flex-wrap items-baseline gap-x-2 text-fg-muted">
            <span className="font-medium text-fg">Revision {r.revision}</span>
            <span>{RUN_STATUS[r.status]}</span>
            <span className="text-fg-subtle">
              {formatDateTime(r.created_at)}
              {r.started_by_name && <> · {r.started_by_name}</>}
            </span>
          </li>
        ))}
      </ol>
    </Section>
  );
}

// ---- page ---------------------------------------------------------------------------------------

export default function ExamResultsPage() {
  const { examId = "" } = useParams();
  const q = useResults(examId);
  const exam = useExam(examId);
  const [studentId, setStudentId] = useState<string | null>(null);
  if (q.isPending) return <Skeleton className="h-64 w-full" />;
  if (q.error) return <Callout tone="danger">Results couldn&apos;t be loaded.</Callout>;
  const o = q.data;
  const stats = statsOf(o);
  const showResults = o.run && stats && o.run.status !== "running" && o.run.status !== "failed";
  const papers = new Map<string, PaperMeta>(
    (exam.data?.papers ?? []).map((p) => [
      p.id,
      {
        id: p.id,
        course_code: p.course_code,
        course_name: p.course_name,
        components: p.components.map((c) => ({ code: c.code, label: c.label, max: c.max })),
      },
    ]),
  );
  return (
    <div className="flex flex-col gap-5">
      <RunPanel o={o} />
      {showResults && (
        <>
          <Stats s={stats} />
          <Anomalies items={anomaliesOf(o)} onOpen={setStudentId} />
          <Students o={o} onOpen={setStudentId} />
          <StudentSheet
            examId={o.exam_id}
            runId={o.run!.id}
            studentId={studentId}
            papers={papers}
            onClose={() => setStudentId(null)}
          />
        </>
      )}
      <History o={o} />
    </div>
  );
}
