import type { ImportListItem, ImportStatus } from "@scorecode/api-client";
import {
  Badge,
  Button,
  EmptyState,
  Field,
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
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Td,
  Th,
  formatNumber,
  formatRelative,
} from "@scorecode/ui";
import { ClipboardList, FileDown, FileSpreadsheet, UserPlus, UserRoundPen } from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router";

import { useSessions } from "../academics/api";
import { useExam, useExams } from "../exams/api";
import { isBusy, templateUrl, useImportList } from "./api";
import { UploadZone, useUploadImport } from "./upload";

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

function StudentsImport() {
  const sessions = useSessions();
  const current = sessions.data?.find((s) => s.is_current);
  const [sessionId, setSessionId] = useState("");
  const [mode, setMode] = useState<"upsert" | "create_only">("upsert");
  const list = useImportList("students");
  const upload = useUploadImport();

  return (
    <>
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
            <UploadZone
              uploading={upload.isPending ? (upload.variables?.file.name ?? "") : null}
              onFile={(file) =>
                upload.mutate({
                  file,
                  fields: { kind: "students", mode, session_id: sessionId || current?.id },
                })
              }
              hint="We'll check every row and show you exactly what will change."
            />
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
            href={templateUrl("students")}
            className="mt-4 inline-flex items-center gap-2 text-[13px] font-medium text-brand-ink hover:underline"
          >
            <FileDown className="size-4" aria-hidden /> Download the template
          </a>
        </Section>
      </div>
      <h2 className="mb-3 mt-8 text-[15px] font-semibold text-fg">Recent student imports</h2>
      <RecentImports items={list.data ?? []} loading={list.isPending} />
    </>
  );
}

const TAKING_MARKS = ["marks_entry_open", "marks_entry_closed"];

function MarksImport({ examParam, onExam }: { examParam: string; onExam: (id: string) => void }) {
  const exams = useExams("");
  const open = (exams.data ?? []).filter((e) => TAKING_MARKS.includes(e.status));
  const examId = open.some((e) => e.id === examParam) ? examParam : (open[0]?.id ?? "");
  const exam = useExam(examId);
  // The paper choice belongs to the exam it was made for; switching exams starts from "all papers".
  const [paper, setPaper] = useState({ exam: "", id: "" });
  const paperId = paper.exam === examId ? paper.id : "";
  const chosen = exam.data?.papers.find((p) => p.id === paperId);
  const list = useImportList("marks");
  const upload = useUploadImport();

  if (exams.isPending) return <Section title="Import marks">{null}</Section>;
  return (
    <>
      <div className="grid gap-5 lg:grid-cols-[1fr_340px]">
        <Section
          title="Import marks"
          description="One file for a whole exam, or one paper at a time. Excel (.xlsx) or CSV, up to 10 MB."
        >
          {open.length === 0 ? (
            <EmptyState
              compact
              icon={<ClipboardList />}
              title="No exam is taking marks"
              description="Open marks entry on an exam first; its papers and students set the columns."
              action={
                <Button variant="secondary" size="sm" asChild>
                  <Link to="/admin/exams">Go to exams</Link>
                </Button>
              }
            />
          ) : (
            <div className="flex flex-col gap-5">
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Exam">
                  <Select value={examId} onChange={(e) => onExam(e.target.value)}>
                    {open.map((e) => (
                      <option key={e.id} value={e.id}>
                        {e.name} · {e.term.session_code}
                        {e.status === "marks_entry_closed" ? " (entry closed)" : ""}
                      </option>
                    ))}
                  </Select>
                </Field>
                <Field label="Papers in the file">
                  <Select
                    value={paperId}
                    onChange={(e) => setPaper({ exam: examId, id: e.target.value })}
                    disabled={!exam.data}
                  >
                    <option value="">All papers</option>
                    {(exam.data?.papers ?? []).map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.course_code} — {p.course_name}
                      </option>
                    ))}
                  </Select>
                </Field>
              </div>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-fg-muted">
                <a
                  href={templateUrl("marks", { exam_id: examId, paper_id: paperId })}
                  className="inline-flex items-center gap-2 font-medium text-brand-ink hover:underline"
                >
                  <FileDown className="size-4" aria-hidden />
                  Download the template{chosen ? ` for ${chosen.course_code}` : " for all papers"}
                </a>
                <span>Pre-filled with every student sitting the exam.</span>
              </div>
              <UploadZone
                uploading={upload.isPending ? (upload.variables?.file.name ?? "") : null}
                disabled={!examId}
                onFile={(file) =>
                  upload.mutate({
                    file,
                    fields: { kind: "marks", exam_id: examId, paper_id: paperId || undefined },
                  })
                }
                hint="We'll check every mark against the paper's maximums before anything is saved."
              />
            </div>
          )}
        </Section>
        <Section title="Tips">
          <ul className="flex list-disc flex-col gap-2 pl-4 text-[13px] leading-5 text-fg-muted">
            <li>
              Students are matched by enrollment number. A name column, if present, is only cross-checked.
            </li>
            <li>
              Three layouts work: one paper with a column per component (<em>Internal</em>, <em>External</em>
              ); a list with a course-code column; or one row per student with columns like{" "}
              <span className="font-mono">UCS301_INT</span>.
            </li>
            <li>
              Columns you leave out keep their saved marks, so internals can go in before externals. Type{" "}
              <strong>AB</strong>, <strong>EX</strong>, <strong>MP</strong> or <strong>WH</strong> for
              attendance.
            </li>
            <li>If someone changes a mark in the grid after your file is checked, nothing is overwritten.</li>
          </ul>
        </Section>
      </div>
      <h2 className="mb-3 mt-8 text-[15px] font-semibold text-fg">Recent marks imports</h2>
      <RecentImports items={list.data ?? []} loading={list.isPending} />
    </>
  );
}

export default function ImportsPage() {
  const [params, setParams] = useSearchParams();
  const kind = params.get("kind") === "marks" ? "marks" : "students";
  const examParam = params.get("exam") ?? "";
  return (
    <>
      <PageHeader
        title="Imports"
        description="Bring students and marks in from a spreadsheet. Everything is checked first — nothing changes until you confirm."
      />
      <Tabs
        value={kind}
        onValueChange={(v) => setParams(v === "marks" ? { kind: "marks" } : {}, { replace: true })}
      >
        <TabsList className="mb-5">
          <TabsTrigger value="students">Students</TabsTrigger>
          <TabsTrigger value="marks">Marks</TabsTrigger>
        </TabsList>
        <TabsContent value="students">
          <StudentsImport />
        </TabsContent>
        <TabsContent value="marks">
          <MarksImport
            examParam={examParam}
            onExam={(id) => setParams({ kind: "marks", exam: id }, { replace: true })}
          />
        </TabsContent>
      </Tabs>
    </>
  );
}
