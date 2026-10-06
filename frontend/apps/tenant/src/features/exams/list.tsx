import { api, type Exam, type ExamKind, type ExamStatus } from "@scorecode/api-client";
import {
  Badge,
  Button,
  Checkbox,
  EmptyState,
  Field,
  Input,
  PageHeader,
  Select,
  TBody,
  THead,
  Table,
  TableContainer,
  TableSkeletonRows,
  Td,
  Th,
  Toolbar,
  formatRelative,
} from "@scorecode/ui";
import { useMutation } from "@tanstack/react-query";
import { ClipboardList, Plus } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router";

import { FormDialog } from "../../components/form-dialog";
import { applyServerError } from "../../lib/forms";
import { useCan } from "../../lib/session";
import { useCohorts, useSessions, useTerms } from "../academics/api";
import { useSchemes } from "../grading/api";
import { E, KIND_LABEL, STATUS, useExams, useSetExam } from "./api";

export function ExamStatusBadge({ status }: { status: ExamStatus }) {
  const s = STATUS[status];
  return (
    <Badge tone={s.tone} dot>
      {s.label}
    </Badge>
  );
}

function NewExamDialog({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate();
  const setExam = useSetExam();
  const sessions = useSessions();
  const current = sessions.data?.find((s) => s.is_current) ?? sessions.data?.[0];
  const [sessionId, setSessionId] = useState("");
  const session = sessions.data?.find((s) => s.id === (sessionId || current?.id));
  const terms = useTerms(session?.id);
  const cohorts = useCohorts(session?.id ?? "", "");
  const schemes = useSchemes();
  const [name, setName] = useState("");
  const [kind, setKind] = useState<ExamKind>("term");
  const [termId, setTermId] = useState("");
  const [schemeId, setSchemeId] = useState("");
  const [picked, setPicked] = useState<string[]>([]);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<unknown>(null);
  const activeCohorts = (cohorts.data ?? []).filter((c) => !c.archived_at && c.session_id === session?.id);
  const effectiveTerm = termId || terms.data?.[0]?.id || "";
  const effectiveScheme = schemeId || schemes.data?.find((s) => s.is_default)?.id || "";
  const create = useMutation({
    mutationFn: () =>
      api.post<Exam>(E, {
        name,
        kind,
        term_id: effectiveTerm,
        grading_scheme_id: effectiveScheme || null,
        cohort_ids: picked,
      }),
    onSuccess: (exam) => {
      setExam(exam);
      void navigate(`/admin/exams/${exam.id}`);
    },
    onError: (e) => {
      const placed: Record<string, string> = {};
      const msg = applyServerError(
        e,
        (field, err) => {
          placed[String(field)] = err.message ?? "";
        },
        ["name", "term_id", "grading_scheme_id", "cohort_ids"],
      );
      setErrors(placed);
      setError(msg ? e : null);
    },
  });
  return (
    <FormDialog
      open
      onOpenChange={(o) => !o && onClose()}
      title="New exam"
      description="Name the exam and choose who sits it. Papers and faculty come next."
      submitLabel="Create exam"
      submitting={create.isPending}
      error={error}
      formId="new-exam"
      size="lg"
    >
      <form
        id="new-exam"
        noValidate
        className="flex flex-col gap-5"
        onSubmit={(e) => {
          e.preventDefault();
          setErrors({});
          setError(null);
          if (!name.trim()) {
            setErrors({ name: "Give the exam a name." });
            return;
          }
          create.mutate();
        }}
      >
        <div className="grid gap-5 sm:grid-cols-[1fr_180px]">
          <Field label="Name" error={errors.name}>
            <Input
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="End Semester Dec 2025"
            />
          </Field>
          <Field label="Kind">
            <Select value={kind} onChange={(e) => setKind(e.target.value as ExamKind)}>
              {(Object.keys(KIND_LABEL) as ExamKind[]).map((k) => (
                <option key={k} value={k}>
                  {KIND_LABEL[k]}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <div className="grid gap-5 sm:grid-cols-2">
          <Field label="Session">
            <Select
              value={session?.id ?? ""}
              onChange={(e) => {
                setSessionId(e.target.value);
                setTermId("");
                setPicked([]);
              }}
            >
              {(sessions.data ?? []).map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                  {s.is_current ? " (current)" : ""}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Term" error={errors.term_id}>
            <Select
              value={effectiveTerm}
              onChange={(e) => setTermId(e.target.value)}
              disabled={!terms.data?.length}
            >
              {(terms.data ?? []).map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <Field
          label="Grading scheme"
          error={errors.grading_scheme_id}
          description={
            schemes.data?.length ? undefined : "Create a grading scheme first (Academics → Grading)."
          }
        >
          <Select
            value={effectiveScheme}
            onChange={(e) => setSchemeId(e.target.value)}
            disabled={!schemes.data?.length}
          >
            {(schemes.data ?? []).map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
                {s.is_default ? " (default)" : ""}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Cohorts sitting this exam" optional error={errors.cohort_ids}>
          {activeCohorts.length === 0 ? (
            <p className="text-[13px] text-fg-subtle">No cohorts in this session yet.</p>
          ) : (
            <div className="grid max-h-56 gap-2 overflow-y-auto rounded-lg border border-border p-3 sm:grid-cols-2">
              {activeCohorts.map((c) => (
                <Checkbox
                  key={c.id}
                  checked={picked.includes(c.id)}
                  onCheckedChange={(on) =>
                    setPicked((p) => (on ? [...p, c.id] : p.filter((x) => x !== c.id)))
                  }
                  label={`${c.code} — ${c.name}`}
                />
              ))}
            </div>
          )}
        </Field>
      </form>
    </FormDialog>
  );
}

export default function ExamsPage() {
  const canManage = useCan("exams.manage");
  const [status, setStatus] = useState<ExamStatus | "">("");
  const [creating, setCreating] = useState(false);
  const exams = useExams(status);
  const rows = exams.data ?? [];
  return (
    <>
      <PageHeader
        title="Exams"
        description="Set up each exam's papers, cohorts and faculty, then open marks entry."
        actions={
          canManage && (
            <Button leadingIcon={<Plus />} onClick={() => setCreating(true)}>
              New exam
            </Button>
          )
        }
      />
      <Toolbar>
        <Select
          value={status}
          onChange={(e) => setStatus(e.target.value as ExamStatus | "")}
          className="w-full sm:w-56"
          aria-label="Filter by status"
        >
          <option value="">All exams</option>
          {(Object.keys(STATUS) as ExamStatus[]).map((s) => (
            <option key={s} value={s}>
              {STATUS[s].label}
            </option>
          ))}
        </Select>
      </Toolbar>
      {!exams.isPending && rows.length === 0 ? (
        <div className="rounded-xl border border-border bg-surface">
          <EmptyState
            icon={<ClipboardList />}
            title={status ? "No exams with this status" : "No exams yet"}
            description={
              status
                ? "Try another filter."
                : "Create an exam, add its papers and the cohorts sitting it, then open marks entry for faculty."
            }
            action={
              canManage &&
              !status && (
                <Button leadingIcon={<Plus />} onClick={() => setCreating(true)}>
                  Create an exam
                </Button>
              )
            }
          />
        </div>
      ) : (
        <TableContainer>
          <Table>
            <THead>
              <tr>
                <Th>Exam</Th>
                <Th>Status</Th>
                <Th className="hidden md:table-cell">Papers</Th>
                <Th className="hidden md:table-cell">Cohorts</Th>
                <Th className="hidden lg:table-cell">Updated</Th>
              </tr>
            </THead>
            <TBody>
              {exams.isPending ? (
                <TableSkeletonRows cols={5} rows={4} />
              ) : (
                rows.map((x) => (
                  <tr key={x.id}>
                    <Td className="w-full max-w-0">
                      <Link
                        to={`/admin/exams/${x.id}`}
                        className="block truncate font-medium text-fg hover:underline"
                      >
                        {x.name}
                      </Link>
                      <p className="truncate text-[13px] text-fg-subtle">
                        {KIND_LABEL[x.kind]} · {x.term.name}, {x.term.session_code} · {x.grading_scheme_name}
                      </p>
                    </Td>
                    <Td className="whitespace-nowrap">
                      <ExamStatusBadge status={x.status} />
                    </Td>
                    <Td className="hidden tabular text-fg-muted md:table-cell">{x.papers}</Td>
                    <Td className="hidden tabular text-fg-muted md:table-cell">{x.cohorts}</Td>
                    <Td className="hidden whitespace-nowrap text-fg-subtle lg:table-cell">
                      {formatRelative(x.updated_at)}
                    </Td>
                  </tr>
                ))
              )}
            </TBody>
          </Table>
        </TableContainer>
      )}
      {creating && <NewExamDialog onClose={() => setCreating(false)} />}
    </>
  );
}
