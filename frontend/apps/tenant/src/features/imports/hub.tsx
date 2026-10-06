import { ApiError, type ImportListItem, type ImportStatus } from "@scorecode/api-client";
import {
  Badge,
  EmptyState,
  Field,
  FileDropzone,
  PageHeader,
  RadioCards,
  Section,
  Select,
  Spinner,
  TBody,
  THead,
  Table,
  TableContainer,
  TableSkeletonRows,
  Td,
  Th,
  formatNumber,
  formatRelative,
  toast,
} from "@scorecode/ui";
import { useMutation } from "@tanstack/react-query";
import { FileSpreadsheet, FileDown, UserPlus, UserRoundPen } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router";

import { toastError } from "../../lib/forms";
import { useSessions } from "../academics/api";
import { I, isBusy, uploadImport, useImportList } from "./api";

const MAX_BYTES = 10 * 1024 * 1024;

export const STATUS_BADGE: Record<
  ImportStatus,
  { label: string; tone: "neutral" | "info" | "warning" | "success" | "danger" }
> = {
  uploaded: { label: "Queued", tone: "info" },
  parsing: { label: "Reading file", tone: "info" },
  needs_mapping: { label: "Needs column mapping", tone: "warning" },
  validating: { label: "Checking", tone: "info" },
  validated: { label: "Ready to review", tone: "warning" },
  committing: { label: "Importing", tone: "info" },
  committed: { label: "Imported", tone: "success" },
  failed: { label: "Couldn't read file", tone: "danger" },
  cancelled: { label: "Cancelled", tone: "neutral" },
};

export function ImportStatusBadge({ status }: { status: ImportStatus }) {
  const b = STATUS_BADGE[status];
  return (
    <Badge tone={b.tone} dot icon={isBusy(status) ? <Spinner className="size-3" label="" /> : undefined}>
      {b.label}
    </Badge>
  );
}

function RecentImports({ items, loading }: { items: ImportListItem[]; loading: boolean }) {
  return (
    <TableContainer>
      <Table>
        <THead>
          <tr>
            <Th>File</Th>
            <Th>Status</Th>
            <Th className="hidden sm:table-cell">Rows</Th>
            <Th className="hidden md:table-cell">Uploaded</Th>
          </tr>
        </THead>
        <TBody>
          {loading ? (
            <TableSkeletonRows cols={4} rows={3} />
          ) : items.length === 0 ? (
            <tr>
              <td colSpan={4}>
                <EmptyState compact title="No imports yet" description="Files you upload appear here." />
              </td>
            </tr>
          ) : (
            items.map((i) => (
              <tr key={i.id}>
                <Td className="w-full max-w-0">
                  <Link
                    to={`/admin/imports/${i.id}`}
                    className="flex min-w-0 items-center gap-2 font-medium hover:underline"
                  >
                    <FileSpreadsheet className="size-4 shrink-0 text-fg-subtle" aria-hidden />
                    <span className="truncate">{i.file_name}</span>
                  </Link>
                </Td>
                <Td className="whitespace-nowrap">
                  <ImportStatusBadge status={i.status} />
                </Td>
                <Td className="hidden whitespace-nowrap text-fg-muted tabular sm:table-cell">
                  {formatNumber(i.rows_total)}
                  {i.rows_error > 0 && (
                    <span className="text-danger"> · {formatNumber(i.rows_error)} errors</span>
                  )}
                </Td>
                <Td className="hidden whitespace-nowrap text-fg-subtle md:table-cell">
                  {formatRelative(i.created_at)}
                  {i.created_by_name && <> · {i.created_by_name}</>}
                </Td>
              </tr>
            ))
          )}
        </TBody>
      </Table>
    </TableContainer>
  );
}

export default function ImportsPage() {
  const navigate = useNavigate();
  const sessions = useSessions();
  const current = sessions.data?.find((s) => s.is_current);
  const [sessionId, setSessionId] = useState("");
  const [mode, setMode] = useState<"upsert" | "create_only">("upsert");
  const list = useImportList("students");
  const upload = useMutation({
    mutationFn: (file: File) =>
      uploadImport(file, { kind: "students", mode, session_id: sessionId || current?.id }),
    onSuccess: (job) => {
      if (job.resumed) toast.info("You've uploaded this file before — continuing where you left off.");
      void navigate(`/admin/imports/${job.id}`);
    },
    onError: (e) => {
      if (e instanceof ApiError && e.status === 409 && typeof e.body.import_id === "string") {
        const id = e.body.import_id;
        toast.error("Already imported", {
          description: e.detail,
          action: { label: "View", onClick: () => void navigate(`/admin/imports/${id}`) },
        });
        return;
      }
      toastError(e);
    },
  });

  return (
    <>
      <PageHeader
        title="Imports"
        description="Bring students in from a spreadsheet. Everything is checked first — nothing changes until you confirm."
      />
      <div className="grid gap-5 lg:grid-cols-[1fr_340px]">
        <Section title="Import students" description="Excel (.xlsx) or CSV, any column order. Up to 10 MB.">
          <div className="flex flex-col gap-5">
            <Field label="Existing students">
              <RadioCards
                name="mode"
                value={mode}
                onChange={setMode}
                options={[
                  {
                    value: "upsert",
                    label: "Add new and update existing",
                    icon: <UserRoundPen />,
                    description: "Students already here (same enrollment no.) get the details from the file.",
                  },
                  {
                    value: "create_only",
                    label: "Only add new students",
                    icon: <UserPlus />,
                    description: "Rows for students who already exist are skipped.",
                  },
                ]}
              />
            </Field>
            <Field
              label="Session for the cohort column"
              optional
              description="Only used if your file has a cohort/section column."
            >
              <Select
                value={sessionId || current?.id || ""}
                onChange={(e) => setSessionId(e.target.value)}
                className="sm:w-80"
              >
                {(sessions.data ?? []).map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                    {s.is_current ? " (current)" : ""}
                  </option>
                ))}
              </Select>
            </Field>
            {upload.isPending ? (
              <div className="flex items-center justify-center gap-3 rounded-xl border-2 border-dashed border-border-strong px-6 py-10 text-sm text-fg-muted">
                <Spinner className="size-5" label="" /> Uploading {upload.variables?.name}…
              </div>
            ) : (
              <FileDropzone
                accept=".xlsx,.csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv"
                maxBytes={MAX_BYTES}
                onFile={(f) => upload.mutate(f)}
                hint="We'll check every row and show you exactly what will change."
              />
            )}
          </div>
        </Section>
        <Section title="Tips">
          <ul className="flex list-disc flex-col gap-2 pl-4 text-[13px] leading-5 text-fg-muted">
            <li>
              Only enrollment number and name are required. Columns can be in any order — you can map them
              after uploading.
            </li>
            <li>Enrollment numbers become student logins, so they must be unique.</li>
            <li>
              Long numbers? Format that column as <strong>Text</strong> in Excel so they don&apos;t turn into
              1.02E+11.
            </li>
            <li>Blank cells never erase details that are already saved.</li>
          </ul>
          <a
            href={`${I}/template.xlsx?kind=students`}
            className="mt-4 inline-flex items-center gap-2 text-[13px] font-medium text-brand-ink hover:underline"
          >
            <FileDown className="size-4" aria-hidden /> Download the template
          </a>
        </Section>
      </div>
      <h2 className="mb-3 mt-8 text-[15px] font-semibold text-fg">Recent imports</h2>
      <RecentImports items={list.data ?? []} loading={list.isPending} />
    </>
  );
}
