import { api, ApiError, type ImportIssue, type ImportJob, type ImportRow } from "@scorecode/api-client";
import {
  Badge,
  Button,
  Callout,
  ConfirmDialog,
  Dialog,
  DialogContent,
  EmptyState,
  Field,
  FileDropzone,
  Input,
  LoadMore,
  PageHeader,
  Section,
  Segmented,
  Select,
  Skeleton,
  Spinner,
  StatTile,
  Stepper,
  TBody,
  THead,
  Table,
  TableContainer,
  TableSkeletonRows,
  Td,
  Th,
  formatNumber,
  formatRelative,
  noun,
  pluralize,
  toast,
} from "@scorecode/ui";
import { useMutation } from "@tanstack/react-query";
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  Columns3,
  FileDown,
  FileUp,
  Info,
  KeyRound,
  Users,
  X,
} from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { toastError } from "../../lib/forms";
import { I, isBusy, uploadImport, useImport, useImportRows, useRefreshImport } from "./api";
import { ImportStatusBadge } from "./hub";

const STEPS = [{ label: "Upload" }, { label: "Check" }, { label: "Review" }, { label: "Import" }];

function stepOf(job: ImportJob): number {
  switch (job.status) {
    case "uploaded":
    case "parsing":
    case "validating":
    case "needs_mapping":
    case "failed":
      return 1;
    case "validated":
    case "cancelled":
      return 2;
    case "committing":
      return 3;
    case "committed":
      return 4;
  }
}

const columnLetter = (i: number): string =>
  i < 26
    ? String.fromCharCode(65 + i)
    : columnLetter(Math.floor(i / 26) - 1) + String.fromCharCode(65 + (i % 26));

function Busy({ job }: { job: ImportJob }) {
  const text = {
    uploaded: "Waiting for a worker to pick up your file…",
    parsing: "Reading your file…",
    validating: "Checking every row…",
    committing: `Importing ${formatNumber(job.rows_valid + job.rows_warning)} rows…`,
  }[job.status as "uploaded" | "parsing" | "validating" | "committing"];
  return (
    <Section>
      <div className="flex flex-col items-center gap-3 py-8 text-center" role="status" aria-live="polite">
        <Spinner className="size-7" label="" />
        <p className="text-sm font-medium text-fg">{text}</p>
        <p className="max-w-md text-[13px] text-fg-subtle">
          This usually takes a few seconds. You can leave this page — the import keeps going and you&apos;ll
          find it under Imports.
        </p>
      </div>
    </Section>
  );
}

// ---- mapping ------------------------------------------------------------------------------------

function MappingPanel({ job, onDone }: { job: ImportJob; onDone?: () => void }) {
  const refresh = useRefreshImport(job.id);
  const [mapping, setMapping] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      job.fields.map((f) => [f.key, job.mapping[f.key] !== undefined ? String(job.mapping[f.key]) : ""]),
    ),
  );
  const [headerRow, setHeaderRow] = useState(String(job.header_row ?? 1));
  const [sheet, setSheet] = useState(job.sheet_name ?? "");
  const used = Object.values(mapping).filter(Boolean);
  const duplicate = used.find((c, i) => used.indexOf(c) !== i);
  const save = useMutation({
    mutationFn: () =>
      api.put<ImportJob>(`${I}/${job.id}/mapping`, {
        mapping: Object.fromEntries(
          Object.entries(mapping).map(([k, v]) => [k, v === "" ? null : Number(v)]),
        ),
        header_row: Number(headerRow) || null,
        sheet_name: sheet || null,
      }),
    onSuccess: (j) => {
      refresh(j);
      onDone?.();
    },
    onError: (e) => toastError(e),
  });
  return (
    <Section
      title="Match your columns"
      description="Tell us which column holds each field. Required fields must be matched; everything else is optional."
    >
      <form
        className="flex flex-col gap-5"
        onSubmit={(e) => {
          e.preventDefault();
          if (!duplicate) save.mutate();
        }}
      >
        {job.file_issues
          .filter((i) => i.code === "MISSING_COLUMN")
          .map((i) => (
            <Callout key={i.msg} tone="warning">
              {i.msg}
            </Callout>
          ))}
        <div className="grid gap-4 sm:grid-cols-2">
          {job.sheets.length > 1 && (
            <Field label="Sheet">
              <Select value={sheet} onChange={(e) => setSheet(e.target.value)}>
                {job.sheets.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </Select>
            </Field>
          )}
          <Field label="Header row" description="The row with the column names. Data starts below it.">
            <Input
              inputMode="numeric"
              value={headerRow}
              onChange={(e) => setHeaderRow(e.target.value)}
              className="w-28"
            />
          </Field>
        </div>
        <div className="divide-y divide-border rounded-lg border border-border">
          {job.fields.map((f) => (
            <div key={f.key} className="grid items-center gap-2 px-4 py-3 sm:grid-cols-[1fr_minmax(0,320px)]">
              <div>
                <p className="text-sm font-medium text-fg">
                  {f.label}{" "}
                  {f.required && (
                    <Badge tone="info" className="ml-1">
                      Required
                    </Badge>
                  )}
                </p>
                {f.help && <p className="text-[13px] text-fg-subtle">{f.help}</p>}
              </div>
              <Select
                aria-label={`Column for ${f.label}`}
                value={mapping[f.key] ?? ""}
                onChange={(e) => setMapping((m) => ({ ...m, [f.key]: e.target.value }))}
              >
                <option value="">— Not in this file —</option>
                {job.columns.map((c, i) => (
                  <option key={i} value={String(i)}>
                    Column {columnLetter(i)}: {c || "(no heading)"}
                  </option>
                ))}
              </Select>
            </div>
          ))}
        </div>
        {duplicate && (
          <p role="alert" className="text-[13px] text-danger">
            Column {columnLetter(Number(duplicate))} is used for two fields. Each column can hold one field.
          </p>
        )}
        <div className="flex flex-wrap gap-2">
          <Button
            type="submit"
            leadingIcon={<Columns3 />}
            loading={save.isPending}
            disabled={Boolean(duplicate)}
          >
            Check with this mapping
          </Button>
          {onDone && (
            <Button variant="secondary" onClick={onDone}>
              Cancel
            </Button>
          )}
        </div>
      </form>
    </Section>
  );
}

// ---- review -------------------------------------------------------------------------------------

const SEVERITY_ICON = {
  error: <AlertCircle className="size-4 shrink-0 text-danger" aria-label="Error" />,
  warning: <AlertTriangle className="size-4 shrink-0 text-warning" aria-label="Warning" />,
  info: <Info className="size-4 shrink-0 text-info" aria-label="Note" />,
};

function Issues({ issues }: { issues: ImportIssue[] }) {
  if (issues.length === 0) return <span className="text-fg-subtle">—</span>;
  return (
    <ul className="flex flex-col gap-1">
      {issues.map((i, n) => (
        <li key={n} className="flex items-start gap-1.5">
          {SEVERITY_ICON[i.severity]}
          <span className={i.severity === "info" ? "text-fg-muted" : "text-fg"}>{i.msg}</span>
        </li>
      ))}
    </ul>
  );
}

function rowLabel(r: ImportRow): { id: string; name: string } {
  const n = r.normalized ?? {};
  return {
    id: typeof n.enrollment_no === "string" && n.enrollment_no ? n.enrollment_no : (r.raw[0] ?? ""),
    name: typeof n.full_name === "string" ? n.full_name : r.raw.slice(1, 3).join(" "),
  };
}

function RowsTable({ job }: { job: ImportJob }) {
  const problems = job.rows_error + job.rows_warning;
  const [filter, setFilter] = useState<"problems" | "error" | "warning" | "">(problems ? "problems" : "");
  const rows = useImportRows(job.id, filter, true);
  const items = rows.data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <div>
      <div className="mb-3 overflow-x-auto">
        <Segmented
          label="Show rows"
          value={filter}
          onChange={setFilter}
          options={[
            { value: "problems", label: "Needs attention", count: problems },
            { value: "error", label: "Errors", count: job.rows_error },
            { value: "warning", label: "Warnings", count: job.rows_warning },
            { value: "", label: "All rows", count: job.rows_total },
          ]}
        />
      </div>
      <TableContainer>
        <Table>
          <THead>
            <tr>
              <Th className="w-16">Row</Th>
              <Th>Student</Th>
              <Th>What we found</Th>
            </tr>
          </THead>
          <TBody>
            {rows.isPending ? (
              <TableSkeletonRows cols={3} rows={5} />
            ) : items.length === 0 ? (
              <tr>
                <td colSpan={3}>
                  <EmptyState
                    compact
                    icon={<CheckCircle2 />}
                    title="Nothing here"
                    description="No rows match this filter."
                  />
                </td>
              </tr>
            ) : (
              items.map((r) => {
                const label = rowLabel(r);
                return (
                  <tr key={r.row_no} className="align-top">
                    <Td className="tabular text-fg-subtle">{r.row_no}</Td>
                    <Td className="max-w-[16rem]">
                      <p className="truncate font-mono text-[13px] text-fg">{label.id || "—"}</p>
                      <p className="truncate text-[13px] text-fg-muted">{label.name}</p>
                    </Td>
                    <Td className="text-[13px]">
                      <Issues issues={r.issues} />
                    </Td>
                  </tr>
                );
              })
            )}
          </TBody>
        </Table>
      </TableContainer>
      <LoadMore
        hasMore={Boolean(rows.hasNextPage)}
        loading={rows.isFetchingNextPage}
        onLoadMore={() => void rows.fetchNextPage()}
      />
    </div>
  );
}

function ReuploadDialog({ job, onClose }: { job: ImportJob; onClose: () => void }) {
  const navigate = useNavigate();
  const upload = useMutation({
    mutationFn: (file: File) =>
      uploadImport(file, {
        kind: job.kind,
        mode: typeof job.params.mode === "string" ? job.params.mode : undefined,
        session_id: typeof job.params.session_id === "string" ? job.params.session_id : undefined,
        supersedes_id: job.id,
      }),
    onSuccess: (j) => {
      onClose();
      void navigate(`/admin/imports/${j.id}`);
    },
    onError: (e) => toastError(e),
  });
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent
        title="Upload the fixed file"
        description="This check is replaced by the new file. If the columns are the same, your mapping is kept."
      >
        {upload.isPending ? (
          <div className="flex items-center justify-center gap-3 py-10 text-sm text-fg-muted">
            <Spinner className="size-5" label="" /> Uploading…
          </div>
        ) : (
          <FileDropzone accept=".xlsx,.csv" maxBytes={10 * 1024 * 1024} onFile={(f) => upload.mutate(f)} />
        )}
      </DialogContent>
    </Dialog>
  );
}

function Review({ job }: { job: ImportJob }) {
  const navigate = useNavigate();
  const refresh = useRefreshImport(job.id);
  const [remap, setRemap] = useState(false);
  const [reupload, setReupload] = useState(false);
  const [confirm, setConfirm] = useState<null | { skipErrors: boolean }>(null);
  const [cancelling, setCancelling] = useState(false);
  const s = job.summary as Record<string, number | string | boolean | null>;
  const creates = Number(s.create ?? 0);
  const updates = Number(s.update ?? 0);
  const ready = job.rows_valid + job.rows_warning;
  const blocking = job.file_issues.filter((i) => i.severity === "error");
  const commit = useMutation({
    mutationFn: (skipErrors: boolean) =>
      api.post<ImportJob>(`${I}/${job.id}/commit`, { skip_errors: skipErrors }),
    onSuccess: (j) => {
      setConfirm(null);
      refresh(j);
    },
    onError: (e) => {
      setConfirm(null);
      toastError(e);
    },
  });
  const cancel = useMutation({
    mutationFn: () => api.post<ImportJob>(`${I}/${job.id}/cancel`, {}),
    onSuccess: (j) => {
      refresh(j);
      setCancelling(false);
      toast.success("Import cancelled");
      void navigate("/admin/imports");
    },
    onError: (e) => toastError(e),
  });
  const recheck = useMutation({
    mutationFn: () => api.post<ImportJob>(`${I}/${job.id}/revalidate`, {}),
    onSuccess: (j) => refresh(j),
    onError: (e) => toastError(e),
  });

  if (remap) return <MappingPanel job={job} onDone={() => setRemap(false)} />;

  const outcome = [
    creates > 0 && `${formatNumber(creates)} new ${noun(creates, "student")} will be added`,
    updates > 0 && `${formatNumber(updates)} existing ${noun(updates, "student")} will be updated`,
  ].filter(Boolean);
  return (
    <div className="flex flex-col gap-5">
      {job.error_detail && (
        <Callout
          tone="danger"
          title="The import didn't go through"
          action={
            <Button
              size="sm"
              variant="secondary"
              loading={recheck.isPending}
              onClick={() => recheck.mutate()}
            >
              Check again
            </Button>
          }
        >
          {job.error_detail} Nothing was changed.
        </Callout>
      )}
      {job.file_issues.map((i) => (
        <Callout key={i.code + i.msg} tone={i.severity === "error" ? "danger" : "warning"}>
          {i.msg}
        </Callout>
      ))}
      <div className="grid gap-3 sm:grid-cols-3">
        <StatTile
          label="Ready"
          value={formatNumber(job.rows_valid)}
          icon={<CheckCircle2 className="text-success" />}
        />
        <StatTile
          label="Warnings"
          value={formatNumber(job.rows_warning)}
          hint="Will import; worth a look"
          icon={<AlertTriangle className="text-warning" />}
        />
        <StatTile
          label="Errors"
          value={formatNumber(job.rows_error)}
          hint={job.rows_error ? "Can't import until fixed" : undefined}
          icon={<AlertCircle className="text-danger" />}
        />
      </div>
      <Section
        title="Rows"
        description={`${formatNumber(job.rows_total)} rows from “${job.sheet_name ?? "sheet"}”, header on row ${job.header_row ?? 1}.`}
        actions={
          <>
            <Button variant="ghost" size="sm" leadingIcon={<Columns3 />} onClick={() => setRemap(true)}>
              Columns
            </Button>
            <Button variant="secondary" size="sm" asChild>
              <a href={`${I}/${job.id}/report.xlsx`}>
                <FileDown aria-hidden /> Download checked file
              </a>
            </Button>
          </>
        }
      >
        <RowsTable job={job} />
      </Section>
      <div className="sticky bottom-0 z-10 -mx-1 flex flex-col gap-3 rounded-xl border border-border bg-surface/95 p-4 shadow-md backdrop-blur sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-fg-muted">
          {blocking.length > 0
            ? "Fix the problem above before importing."
            : ready === 0
              ? "No rows can be imported yet."
              : outcome.length
                ? `${outcome.join(" and ")}.`
                : "Everything in this file is already up to date."}
          {job.rows_error > 0 && ready > 0 && blocking.length === 0 && (
            <> {pluralize(job.rows_error, "row")} with errors can be skipped.</>
          )}
        </p>
        <div className="flex flex-wrap gap-2">
          <Button variant="ghost" leadingIcon={<X />} onClick={() => setCancelling(true)}>
            Cancel import
          </Button>
          <Button variant="secondary" leadingIcon={<FileUp />} onClick={() => setReupload(true)}>
            Upload fixed file
          </Button>
          {job.rows_error > 0 ? (
            <Button
              disabled={ready === 0 || blocking.length > 0}
              onClick={() => setConfirm({ skipErrors: true })}
            >
              Import {formatNumber(ready)} valid {noun(ready, "row")}
            </Button>
          ) : (
            <Button
              disabled={ready === 0 || blocking.length > 0}
              onClick={() => setConfirm({ skipErrors: false })}
            >
              Import {pluralize(ready, "row")}
            </Button>
          )}
        </div>
      </div>
      {confirm && (
        <ConfirmDialog
          open
          onOpenChange={(o) => !o && setConfirm(null)}
          title="Import these students?"
          description={
            <>
              {outcome.length ? `${outcome.join(" and ")}.` : "No student details change."}{" "}
              {Boolean(s.cohort_column) &&
                "Students with a cohort in the file are placed in it (moving them out of a sibling cohort). "}
              {confirm.skipErrors && `${pluralize(job.rows_error, "row")} with errors will be skipped. `}
              Everything happens in one step: if anything fails, nothing changes.
            </>
          }
          confirmLabel="Import"
          loading={commit.isPending}
          onConfirm={() => commit.mutate(confirm.skipErrors)}
        />
      )}
      {cancelling && (
        <ConfirmDialog
          open
          onOpenChange={(o) => !o && setCancelling(false)}
          title="Cancel this import?"
          description="The checked rows are discarded. Nothing has been imported yet."
          confirmLabel="Cancel import"
          cancelLabel="Keep it"
          variant="danger"
          loading={cancel.isPending}
          onConfirm={() => cancel.mutate()}
        />
      )}
      {reupload && <ReuploadDialog job={job} onClose={() => setReupload(false)} />}
    </div>
  );
}

function Done({ job }: { job: ImportJob }) {
  const r = (job.summary.result ?? {}) as Record<string, number>;
  const parts = [
    r.created && `${formatNumber(r.created)} added`,
    r.updated && `${formatNumber(r.updated)} updated`,
    r.unchanged && `${formatNumber(r.unchanged)} already up to date`,
    r.skipped && `${formatNumber(r.skipped)} skipped`,
  ].filter(Boolean);
  return (
    <Section>
      <div className="flex flex-col items-center gap-3 py-6 text-center">
        <span className="flex size-12 items-center justify-center rounded-full bg-success-soft text-success">
          <CheckCircle2 className="size-6" aria-hidden />
        </span>
        <h2 className="text-lg font-semibold text-fg">Import complete</h2>
        <p className="text-sm text-fg-muted">
          {parts.join(" · ") || "Nothing needed to change."}
          {r.placed_in_cohorts ? ` · ${formatNumber(r.placed_in_cohorts)} placed in cohorts` : ""}
        </p>
        <p className="text-[13px] text-fg-subtle">
          {job.committed_by_name ? `By ${job.committed_by_name}, ` : ""}
          {formatRelative(job.committed_at)}
        </p>
        <div className="mt-2 flex flex-wrap justify-center gap-2">
          <Button asChild>
            <Link to="/admin/students">
              <Users aria-hidden /> View students
            </Link>
          </Button>
          {Boolean(r.created) && (
            <Button variant="secondary" asChild>
              <Link to="/admin/students/activation">
                <KeyRound aria-hidden /> Print activation codes
              </Link>
            </Button>
          )}
          <Button variant="ghost" asChild>
            <Link to="/admin/imports">Import another file</Link>
          </Button>
        </div>
      </div>
    </Section>
  );
}

export default function ImportJobPage() {
  const { importId = "" } = useParams();
  const q = useImport(importId);
  const [reupload, setReupload] = useState(false);
  if (q.isPending) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-10 w-80" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }
  if (q.error) {
    return (
      <Callout tone="danger">
        {q.error instanceof ApiError && q.error.status === 404
          ? "This import doesn't exist."
          : "This import couldn't be loaded."}
      </Callout>
    );
  }
  const job = q.data;
  return (
    <>
      <PageHeader
        breadcrumb={<Link to="/admin/imports">Imports</Link>}
        title={job.file_name ?? "Import"}
        meta={
          <>
            <ImportStatusBadge status={job.status} />
            <span className="text-[13px] text-fg-subtle">
              Student import · uploaded {formatRelative(job.created_at)}
              {job.created_by_name && <> by {job.created_by_name}</>}
            </span>
          </>
        }
      />
      <div className="mb-6">
        <Stepper steps={STEPS} current={stepOf(job)} />
      </div>
      {isBusy(job.status) && <Busy job={job} />}
      {job.status === "needs_mapping" && <MappingPanel job={job} />}
      {job.status === "validated" && <Review job={job} />}
      {job.status === "committed" && <Done job={job} />}
      {job.status === "failed" && (
        <Callout
          tone="danger"
          title="We couldn't read this file"
          action={
            <Button size="sm" variant="secondary" leadingIcon={<FileUp />} onClick={() => setReupload(true)}>
              Upload another file
            </Button>
          }
        >
          {job.error_detail ?? "The file is damaged or in a format we don't support."}
        </Callout>
      )}
      {job.status === "cancelled" && (
        <Callout tone="info" title="This import was cancelled">
          Nothing from this file was imported.{" "}
          <Link to="/admin/imports" className="font-medium underline">
            Start a new import
          </Link>
          .
        </Callout>
      )}
      {reupload && <ReuploadDialog job={job} onClose={() => setReupload(false)} />}
    </>
  );
}
