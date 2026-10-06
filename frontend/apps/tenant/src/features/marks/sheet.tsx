import { api, ApiError, type MarkSheet, type SavedMark } from "@scorecode/api-client";
import {
  Badge,
  Button,
  Callout,
  ConfirmDialog,
  PageHeader,
  ProgressBar,
  Skeleton,
  formatDateTime,
  toast,
} from "@scorecode/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Check, CloudUpload, Loader2, Send, Undo2 } from "lucide-react";
import { useEffect, useReducer, useRef, useState, type ClipboardEvent, type KeyboardEvent } from "react";
import { Link, useParams } from "react-router";

import { toastError } from "../../lib/forms";
import {
  CODES,
  attendanceOf,
  cellError,
  changeFor,
  liveTotal,
  parseClipboard,
  rowFromServer,
  trimNum,
  type RowState,
} from "./logic";

const AUTOSAVE_MS = 800;

type Rows = Record<string, RowState & { rev: number }>;
type ActionT =
  | { type: "load"; sheet: MarkSheet; conflicts?: Set<string>; pending?: Rows }
  | { type: "edit"; edits: { id: string; code: string; value: string }[]; sheet: MarkSheet }
  | { type: "saving"; ids: string[] }
  | { type: "saved"; saved: SavedMark[]; sent: Record<string, number>; sheet: MarkSheet }
  | { type: "failed"; ids: string[] };

function init(sheet: MarkSheet): Rows {
  return Object.fromEntries(
    sheet.students.map((s) => [s.student_id, { ...rowFromServer(sheet, s.student_id), rev: 0 }]),
  );
}

const isCode = (v: string) => Boolean(CODES[v.trim().toUpperCase()]);
const MIXED =
  "A code applies to the whole paper. Clear the other marks, or enter 0 for a part the student missed.";

/** One cell edit. A code (AB/EX/MP/WH) typed into an otherwise blank row fills the row; mixed with marks it
 *  is an error rather than silently discarding marks. A mark typed into a coded row replaces the code. */
function editRow(
  row: Rows[string],
  code: string,
  value: string,
  byCode: Record<string, MarkSheet["components"][number]>,
): Rows[string] {
  let values = { ...row.values, [code]: value };
  const others = Object.entries(values).filter(([k]) => k !== code);
  if (isCode(value)) {
    if (!others.some(([, v]) => v.trim() !== "" && !isCode(v)))
      values = Object.fromEntries(Object.keys(values).map((k) => [k, value.trim().toUpperCase()]));
  } else if (others.some(([, v]) => isCode(v))) {
    values = Object.fromEntries(
      Object.entries(values).map(([k, v]) => [k, k === code ? v : isCode(v) ? "" : v]),
    );
  }
  const mixed =
    Object.values(values).some(isCode) && Object.values(values).some((v) => v.trim() !== "" && !isCode(v));
  const errors: Record<string, string> = {};
  for (const [k, v] of Object.entries(values)) {
    const e = mixed && isCode(v) ? MIXED : byCode[k] ? cellError(v, byCode[k]) : null;
    if (e) errors[k] = e;
  }
  return {
    ...row,
    values,
    errors,
    status: Object.keys(errors).length ? "error" : "dirty",
    note: undefined,
    rev: row.rev + 1,
  };
}

function reducer(rows: Rows, a: ActionT): Rows {
  switch (a.type) {
    case "load": {
      const fresh = init(a.sheet);
      for (const [id, row] of Object.entries(rows)) {
        if (a.conflicts?.has(id)) {
          const mine = Object.values(row.values).filter(Boolean).join(" / ") || "blank";
          fresh[id] = {
            ...fresh[id]!,
            status: "conflict",
            note: `Someone else saved this row first. Your entry (${mine}) was not saved.`,
          };
        } else if (row.status === "dirty" || row.status === "error") {
          fresh[id] = { ...row, version: fresh[id]!.version }; // keep unsaved typing, adopt the new version
        }
      }
      return fresh;
    }
    case "edit": {
      const next = { ...rows };
      const byCode = Object.fromEntries(a.sheet.components.map((c) => [c.code, c]));
      for (const { id, code, value } of a.edits) {
        const row = next[id];
        if (!row) continue;
        next[id] = editRow(row, code, value, byCode);
      }
      return next;
    }
    case "saving": {
      const next = { ...rows };
      for (const id of a.ids) if (next[id]) next[id] = { ...next[id], status: "saving" };
      return next;
    }
    case "saved": {
      const next = { ...rows };
      for (const s of a.saved) {
        const row = next[s.student_id];
        if (!row) continue;
        const unchangedSince = a.sent[s.student_id] === row.rev;
        next[s.student_id] = {
          ...row,
          version: s.entry.version,
          total: s.entry.total ?? null,
          attendance: s.entry.attendance,
          status: unchangedSince ? "saved" : "dirty",
        };
      }
      for (const id of Object.keys(a.sent))
        if (next[id]?.status === "saving" && !a.saved.some((s) => s.student_id === id))
          next[id] = { ...next[id], status: "saved" }; // blank row: nothing stored
      return next;
    }
    case "failed": {
      const next = { ...rows };
      for (const id of a.ids) if (next[id]?.status === "saving") next[id] = { ...next[id], status: "dirty" };
      return next;
    }
  }
}

function RowStatus({ row }: { row: RowState }) {
  if (row.status === "saving")
    return <Loader2 className="size-4 animate-spin text-fg-subtle" aria-label="Saving" />;
  if (row.status === "dirty")
    return <CloudUpload className="size-4 text-fg-subtle" aria-label="Not saved yet" />;
  if (row.status === "error")
    return <AlertTriangle className="size-4 text-danger" aria-label="Fix this row" />;
  if (row.status === "conflict")
    return <AlertTriangle className="size-4 text-warning" aria-label="Changed by someone else" />;
  return row.version ? <Check className="size-4 text-success" aria-label="Saved" /> : null;
}

function Grid({ sheet, onRefetch }: { sheet: MarkSheet; onRefetch: () => Promise<MarkSheet | undefined> }) {
  const qc = useQueryClient();
  const [rows, dispatch] = useReducer(reducer, sheet, init);
  const [confirmSubmit, setConfirmSubmit] = useState(false);
  const [returning, setReturning] = useState(false);
  const table = useRef<HTMLTableElement>(null);
  const url = `/api/v1/exams/${sheet.exam_id}/papers/${sheet.paper_id}/cohorts/${sheet.cohort_id}/marks`;
  const readOnly = !sheet.can_edit;
  const ids = sheet.students.map((s) => s.student_id);
  const pending = ids.filter((id) => rows[id]?.status === "dirty");
  const busy = ids.some((id) => rows[id]?.status === "saving");
  const errors = ids.filter((id) => rows[id]?.status === "error").length;
  const complete = ids.filter((id) => {
    const r = rows[id];
    return (
      r &&
      r.version !== null &&
      r.status === "saved" &&
      (attendanceOf(r.values) !== "present" || Object.values(r.values).every((v) => v.trim() !== ""))
    );
  }).length;

  const save = useMutation({
    mutationFn: (sent: Record<string, number>) =>
      api.put<SavedMark[]>(url, { changes: Object.keys(sent).map((id) => changeFor(id, rows[id]!)) }),
    onMutate: (sent) => dispatch({ type: "saving", ids: Object.keys(sent) }),
    onSuccess: (saved, sent) => {
      dispatch({ type: "saved", saved, sent, sheet });
      void qc.invalidateQueries({ queryKey: ["marking"] });
    },
    onError: async (e, sent) => {
      if (e instanceof ApiError && e.status === 409 && Array.isArray(e.body.conflicts)) {
        const conflicts = new Set((e.body.conflicts as { student_id: string }[]).map((c) => c.student_id));
        const fresh = await onRefetch();
        if (fresh) dispatch({ type: "load", sheet: fresh, conflicts });
        toast.warning("Some marks were changed by someone else", { description: e.detail });
        return;
      }
      dispatch({ type: "failed", ids: Object.keys(sent) });
      toastError(e);
    },
  });

  // Autosave: a short pause after typing sends every finished row (with the version it was based on).
  useEffect(() => {
    if (readOnly || pending.length === 0 || save.isPending) return;
    const timer = setTimeout(() => {
      save.mutate(Object.fromEntries(pending.map((id) => [id, rows[id]!.rev])));
    }, AUTOSAVE_MS);
    return () => clearTimeout(timer);
  }, [rows, pending, readOnly, save]);

  useEffect(() => {
    if (pending.length === 0 && !busy) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [pending.length, busy]);

  const focusCell = (r: number, c: number) => {
    const el = table.current?.querySelector<HTMLInputElement>(`[data-cell="${r}:${c}"]`);
    el?.focus();
    el?.select();
  };
  const onKey = (e: KeyboardEvent<HTMLInputElement>, r: number, c: number) => {
    if (e.key === "Enter" || e.key === "ArrowDown") {
      e.preventDefault();
      focusCell(e.shiftKey && e.key === "Enter" ? r - 1 : r + 1, c);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      focusCell(r - 1, c);
    }
  };
  const onPaste = (e: ClipboardEvent<HTMLInputElement>, r: number, c: number) => {
    const text = e.clipboardData.getData("text/plain");
    if (!text.includes("\t") && !text.includes("\n")) return; // a single value: let the input handle it
    e.preventDefault();
    const grid = parseClipboard(text);
    const edits: { id: string; code: string; value: string }[] = [];
    grid.forEach((line, i) =>
      line.forEach((value, j) => {
        const student = sheet.students[r + i];
        const comp = sheet.components[c + j];
        if (student && comp) edits.push({ id: student.student_id, code: comp.code, value });
      }),
    );
    dispatch({ type: "edit", edits, sheet });
    toast.info(`Pasted ${grid.length} row${grid.length === 1 ? "" : "s"}`);
  };

  const submit = useMutation({
    mutationFn: () => api.post<MarkSheet>(`${url}/submit`),
    onSuccess: (s) => {
      qc.setQueryData(["marks", "sheet", url], s);
      void qc.invalidateQueries({ queryKey: ["marking"] });
      setConfirmSubmit(false);
      toast.success("Paper submitted", { description: "An administrator will review the marks." });
    },
    onError: (e) => {
      setConfirmSubmit(false);
      toastError(e);
    },
  });
  const giveBack = useMutation({
    mutationFn: (reason: string) => api.post<MarkSheet>(`${url}/return`, { reason }),
    onSuccess: (s) => {
      qc.setQueryData(["marks", "sheet", url], s);
      setReturning(false);
      toast.success("Returned to faculty");
    },
    onError: (e) => {
      setReturning(false);
      toastError(e);
    },
  });

  const saveState = busy
    ? "Saving…"
    : pending.length
      ? `${pending.length} unsaved`
      : errors
        ? `${errors} to fix`
        : "All changes saved";
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-3 rounded-xl border border-border bg-surface p-4 shadow-xs sm:flex-row sm:items-center">
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-3 text-[13px]">
            <span className="text-fg-muted">
              <span className="font-semibold text-fg tabular">{complete}</span> of {ids.length} students
              complete
            </span>
            <span className={errors ? "text-danger" : "text-fg-subtle"} role="status" aria-live="polite">
              {readOnly ? "Read only" : saveState}
            </span>
          </div>
          <ProgressBar
            value={ids.length ? (complete / ids.length) * 100 : 0}
            label="Students complete"
            className="mt-2"
          />
        </div>
        <div className="flex gap-2">
          {sheet.can_return && (
            <Button variant="secondary" leadingIcon={<Undo2 />} onClick={() => setReturning(true)}>
              Return to faculty
            </Button>
          )}
          {sheet.can_submit && (
            <Button
              leadingIcon={<Send />}
              disabled={busy || pending.length > 0 || errors > 0 || complete < ids.length}
              title={complete < ids.length ? "Every student needs marks or an attendance code" : undefined}
              onClick={() => setConfirmSubmit(true)}
            >
              Submit paper
            </Button>
          )}
        </div>
      </div>
      {!readOnly && (
        <p className="text-[13px] text-fg-subtle">
          Type marks or <strong>AB</strong> absent · <strong>EX</strong> exempt · <strong>MP</strong>{" "}
          malpractice · <strong>WH</strong> withheld. Enter moves down; paste a column or block straight from
          Excel. Changes save automatically.
        </p>
      )}
      <div className="overflow-x-auto rounded-xl border border-border bg-surface shadow-xs">
        <table ref={table} className="w-full border-collapse text-sm" aria-label="Marks">
          <thead className="sticky top-0 z-10 bg-surface-2 text-left text-xs text-fg-subtle">
            <tr>
              <th className="w-12 px-3 py-2 font-medium">#</th>
              <th className="px-3 py-2 font-medium">Student</th>
              {sheet.components.map((c) => (
                <th key={c.code} className="w-28 px-2 py-2 font-medium">
                  {c.label}
                  <span className="block font-normal">
                    out of {trimNum(c.max)}
                    {c.min_pass !== null && ` · min ${trimNum(c.min_pass)}`}
                  </span>
                </th>
              ))}
              <th className="w-20 px-3 py-2 text-right font-medium">Total</th>
              <th className="w-10 px-2 py-2">
                <span className="sr-only">Status</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {sheet.students.map((s, r) => {
              const row = rows[s.student_id]!;
              return (
                <tr
                  key={s.student_id}
                  className={row.status === "conflict" ? "bg-warning-soft/50" : "border-t border-border"}
                  style={{ contentVisibility: "auto", containIntrinsicSize: "auto 44px" }}
                >
                  <td className="px-3 py-1.5 tabular text-fg-subtle">{r + 1}</td>
                  <td className="px-3 py-1.5">
                    <span className="font-mono text-[13px] text-fg">{s.enrollment_no}</span>
                    <span className="ml-2 text-fg-muted">{s.full_name}</span>
                    {row.note && <span className="block text-xs text-warning">{row.note}</span>}
                    {Object.keys(row.errors).length > 0 && (
                      <span id={`err-${s.student_id}`} className="block text-xs text-danger">
                        {sheet.components
                          .filter((c) => row.errors[c.code])
                          .map((c) => `${c.label}: ${row.errors[c.code]}`)
                          .join(" · ")}
                      </span>
                    )}
                  </td>
                  {sheet.components.map((c, j) => {
                    const err = row.errors[c.code];
                    return (
                      <td key={c.code} className="px-2 py-1">
                        <input
                          data-cell={`${r}:${j}`}
                          aria-label={`${s.enrollment_no} ${c.label}`}
                          aria-invalid={err ? true : undefined}
                          aria-describedby={err ? `err-${s.student_id}` : undefined}
                          title={err}
                          inputMode="decimal"
                          autoComplete="off"
                          readOnly={readOnly}
                          value={row.values[c.code] ?? ""}
                          onChange={(e) =>
                            dispatch({
                              type: "edit",
                              edits: [{ id: s.student_id, code: c.code, value: e.target.value }],
                              sheet,
                            })
                          }
                          onKeyDown={(e) => onKey(e, r, j)}
                          onPaste={(e) => onPaste(e, r, j)}
                          onFocus={(e) => e.target.select()}
                          className={
                            "h-8 w-full rounded-md border px-2 text-right tabular outline-none transition-colors focus:border-brand focus:ring-2 focus:ring-brand/20 " +
                            (err ? "border-danger-solid bg-danger-soft" : "border-border bg-surface") +
                            (readOnly ? " cursor-default bg-surface-2 text-fg-muted" : "")
                          }
                        />
                      </td>
                    );
                  })}
                  <td className="px-3 py-1.5 text-right font-semibold tabular">
                    {row.status === "saved" && row.total !== null
                      ? trimNum(row.total)
                      : liveTotal(row, sheet.components)}
                  </td>
                  <td className="px-2 py-1.5">
                    <RowStatus row={row} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <ConfirmDialog
        open={confirmSubmit}
        onOpenChange={setConfirmSubmit}
        title={`Submit ${sheet.course_code} for ${sheet.cohort_code}?`}
        description="You won't be able to change these marks unless an administrator returns the paper to you."
        confirmLabel="Submit paper"
        loading={submit.isPending}
        onConfirm={() => submit.mutate()}
      />
      <ConfirmDialog
        open={returning}
        onOpenChange={setReturning}
        title="Return this paper to faculty?"
        description="They can edit and resubmit. Your note is shown to them and kept in the audit log."
        confirmLabel="Return paper"
        requireReason
        reasonLabel="What needs fixing?"
        loading={giveBack.isPending}
        onConfirm={(reason) => giveBack.mutate(reason)}
      />
    </div>
  );
}

const SUBMISSION = {
  open: { label: "Open", tone: "info" },
  submitted: { label: "Submitted", tone: "success" },
  returned: { label: "Returned for changes", tone: "warning" },
  locked: { label: "Locked", tone: "neutral" },
} as const;

export default function MarkSheetPage() {
  const { examId = "", paperId = "", cohortId = "" } = useParams();
  const url = `/api/v1/exams/${examId}/papers/${paperId}/cohorts/${cohortId}/marks`;
  const q = useQuery({
    queryKey: ["marks", "sheet", url],
    queryFn: () => api.get<MarkSheet>(url),
    staleTime: Infinity,
  });
  if (q.isPending) return <Skeleton className="h-96 w-full" />;
  if (q.error)
    return <Callout tone="danger">This mark sheet couldn't be loaded, or it isn't assigned to you.</Callout>;
  const s = q.data;
  const sub = SUBMISSION[s.submission_status];
  return (
    <>
      <PageHeader
        breadcrumb={<Link to="/marking">Marks entry</Link>}
        title={`${s.course_code} — ${s.course_name}`}
        meta={
          <>
            <Badge tone={sub.tone} dot>
              {sub.label}
            </Badge>
            <span className="text-[13px] text-fg-subtle">
              {s.exam_name} · {s.cohort_code} ({s.cohort_name})
              {s.marks_deadline && <> · due {formatDateTime(s.marks_deadline)}</>}
            </span>
          </>
        }
      />
      {s.submission_status === "returned" && s.return_reason && (
        <Callout tone="warning" title="Returned for changes" className="mb-4">
          {s.return_reason}
        </Callout>
      )}
      {s.submission_status === "submitted" && (
        <Callout tone="success" title="Submitted" className="mb-4">
          {s.submitted_by_name
            ? `${s.submitted_by_name} submitted these marks`
            : "These marks were submitted"}
          {s.submitted_at && ` on ${formatDateTime(s.submitted_at)}`}.
        </Callout>
      )}
      <Grid
        key={`${s.submission_status}:${s.can_edit}`}
        sheet={s}
        onRefetch={async () => (await q.refetch()).data}
      />
    </>
  );
}
