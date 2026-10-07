import { api, type Exam, type ExamAction, type ExamKind } from "@scorecode/api-client";
import {
  Badge,
  Button,
  Callout,
  Checkbox,
  ConfirmDialog,
  EmptyState,
  Field,
  Input,
  Menu,
  MenuContent,
  MenuItem,
  MenuTrigger,
  PageHeader,
  Section,
  Select,
  Skeleton,
  Textarea,
  formatNumber,
  toast,
} from "@scorecode/ui";
import { useMutation } from "@tanstack/react-query";
import {
  CheckCircle2,
  Circle,
  FileDown,
  FileText,
  FileUp,
  MoreHorizontal,
  Pencil,
  Plus,
  Trash2,
  Users,
} from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { toastError } from "../../lib/forms";
import { useCan } from "../../lib/session";
import { useCohorts } from "../academics/api";
import { useSchemes } from "../grading/api";
import { templateUrl } from "../imports/api";
import { E, KIND_LABEL, SETUP_EDITABLE, trimNum, useExam, useSetExam } from "./api";
import { ExamStatusBadge } from "./list";
import { FacultyDialog, PaperDialog } from "./papers";

function Lifecycle({ exam, canManage }: { exam: Exam; canManage: boolean }) {
  const setExam = useSetExam();
  const canImport = useCan("imports.manage");
  const [pending, setPending] = useState<ExamAction | null>(null);
  const ready = exam.checks.every((c) => c.ok);
  const move = useMutation({
    mutationFn: ({ action, reason }: { action: string; reason?: string }) =>
      api.post<Exam>(`${E}/${exam.id}/transitions`, { action, reason: reason || null }),
    onSuccess: (e) => {
      setExam(e);
      setPending(null);
      toast.success(`Status: ${e.status.replaceAll("_", " ")}`);
    },
    onError: (e) => {
      setPending(null);
      toastError(e);
    },
  });
  const descriptions: Record<string, string> = {
    open_entry: "Faculty assigned to each paper can start entering marks. Papers can still be added.",
    close_entry: "Faculty can no longer change marks. You can reopen entry later (with a reason).",
    reopen_entry: "Faculty can change marks again. The reason is kept in the audit log.",
  };
  return (
    <Section
      title={exam.status === "draft" ? "Ready to open marks entry?" : "Marks entry"}
      actions={
        canManage &&
        exam.actions.map((a) => (
          <Button
            key={a.action}
            size="sm"
            variant={a.action === "open_entry" ? "primary" : "secondary"}
            disabled={a.action === "open_entry" && !ready}
            onClick={() => setPending(a)}
          >
            {a.label}
          </Button>
        ))
      }
    >
      {exam.status === "draft" ? (
        <ul className="grid gap-2 sm:grid-cols-2" aria-label="Readiness">
          {exam.checks.map((c) => (
            <li key={c.key} className="flex items-start gap-2 text-sm">
              {c.ok ? (
                <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" aria-label="Done" />
              ) : (
                <Circle className="mt-0.5 size-4 shrink-0 text-fg-disabled" aria-label="To do" />
              )}
              <span className={c.ok ? "text-fg-muted" : "text-fg"}>{c.message}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-fg-muted">
          {exam.status === "marks_entry_open"
            ? "Marks entry is open. Faculty see the papers assigned to them."
            : exam.status === "marks_entry_closed"
              ? "Marks entry is closed. Reopen it if marks need to change."
              : "This exam has moved past marks entry."}
        </p>
      )}
      {canImport && (exam.status === "marks_entry_open" || exam.status === "marks_entry_closed") && (
        <div className="mt-3 flex flex-wrap gap-2">
          <Button size="sm" variant="secondary" asChild>
            <Link to={`/admin/imports?kind=marks&exam=${exam.id}`}>
              <FileUp aria-hidden /> Import marks from Excel
            </Link>
          </Button>
          <Button size="sm" variant="ghost" asChild>
            <a href={templateUrl("marks", { exam_id: exam.id })}>
              <FileDown aria-hidden /> Template for all papers
            </a>
          </Button>
        </div>
      )}
      {pending && (
        <ConfirmDialog
          open
          onOpenChange={(o) => !o && setPending(null)}
          title={`${pending.label}?`}
          description={descriptions[pending.action]}
          confirmLabel={pending.label}
          requireReason={pending.needs_reason}
          loading={move.isPending}
          onConfirm={(reason) => move.mutate({ action: pending.action, reason })}
        />
      )}
    </Section>
  );
}

function Details({ exam, canManage }: { exam: Exam; canManage: boolean }) {
  const setExam = useSetExam();
  const schemes = useSchemes();
  const [name, setName] = useState(exam.name);
  const [kind, setKind] = useState<ExamKind>(exam.kind);
  const [schemeId, setSchemeId] = useState(exam.grading_scheme_id);
  const [deadline, setDeadline] = useState(exam.marks_deadline ? exam.marks_deadline.slice(0, 16) : "");
  const [notes, setNotes] = useState(exam.notes ?? "");
  const editable = canManage;
  const schemeLocked = !SETUP_EDITABLE.includes(exam.status);
  const dirty =
    name !== exam.name ||
    kind !== exam.kind ||
    schemeId !== exam.grading_scheme_id ||
    deadline !== (exam.marks_deadline ? exam.marks_deadline.slice(0, 16) : "") ||
    notes !== (exam.notes ?? "");
  const save = useMutation({
    mutationFn: () =>
      api.put<Exam>(`${E}/${exam.id}`, {
        version: exam.version,
        name,
        kind,
        grading_scheme_id: schemeId,
        marks_deadline: deadline ? new Date(deadline).toISOString() : null,
        notes: notes || null,
      }),
    onSuccess: (e) => {
      setExam(e);
      toast.success("Exam details saved");
    },
    onError: (e) => toastError(e),
  });
  return (
    <Section
      title="Details"
      actions={
        editable &&
        dirty && (
          <Button size="sm" loading={save.isPending} onClick={() => save.mutate()}>
            Save details
          </Button>
        )
      }
    >
      <div className="grid gap-5 sm:grid-cols-2">
        <Field label="Name">
          <Input value={name} disabled={!editable} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field label="Kind">
          <Select value={kind} disabled={!editable} onChange={(e) => setKind(e.target.value as ExamKind)}>
            {(Object.keys(KIND_LABEL) as ExamKind[]).map((k) => (
              <option key={k} value={k}>
                {KIND_LABEL[k]}
              </option>
            ))}
          </Select>
        </Field>
        <Field
          label="Grading scheme"
          description={
            <>
              {schemeLocked ? "Fixed once results are processed. " : ""}
              <Link to={`/admin/grading/${exam.grading_scheme_id}`} className="underline">
                View the scheme
              </Link>
            </>
          }
        >
          <Select
            value={schemeId}
            disabled={!editable || schemeLocked}
            onChange={(e) => setSchemeId(e.target.value)}
          >
            {(schemes.data ?? []).map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
            {!schemes.data?.some((s) => s.id === exam.grading_scheme_id) && (
              <option value={exam.grading_scheme_id}>{exam.grading_scheme_name}</option>
            )}
          </Select>
        </Field>
        <Field
          label="Marks due by"
          optional
          description="Shown to faculty; entry doesn't close automatically."
        >
          <Input
            type="datetime-local"
            value={deadline}
            disabled={!editable}
            onChange={(e) => setDeadline(e.target.value)}
          />
        </Field>
      </div>
      <Field label="Notes for staff" optional className="mt-5">
        <Textarea rows={2} value={notes} disabled={!editable} onChange={(e) => setNotes(e.target.value)} />
      </Field>
    </Section>
  );
}

function Cohorts({ exam, canManage }: { exam: Exam; canManage: boolean }) {
  const setExam = useSetExam();
  const all = useCohorts(exam.term.session_id, "");
  const [editing, setEditing] = useState(false);
  const [picked, setPicked] = useState<string[]>(exam.cohorts.map((c) => c.id));
  const draft = exam.status === "draft";
  const save = useMutation({
    mutationFn: () => api.put<Exam>(`${E}/${exam.id}/cohorts`, { cohort_ids: picked }),
    onSuccess: (e) => {
      setExam(e);
      setEditing(false);
      toast.success("Cohorts updated");
    },
    onError: (e) => toastError(e),
  });
  const editable = canManage && SETUP_EDITABLE.includes(exam.status);
  const options = (all.data ?? []).filter((c) => !c.archived_at && c.session_id === exam.term.session_id);
  return (
    <Section
      title="Cohorts"
      description={`Who sits this exam (cohorts of ${exam.term.session_code}).`}
      actions={
        editable &&
        (editing ? (
          <>
            <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>
              Cancel
            </Button>
            <Button size="sm" loading={save.isPending} onClick={() => save.mutate()}>
              Save cohorts
            </Button>
          </>
        ) : (
          <Button size="sm" variant="secondary" leadingIcon={<Pencil />} onClick={() => setEditing(true)}>
            Change
          </Button>
        ))
      }
    >
      {editing ? (
        <div className="grid gap-2 sm:grid-cols-2">
          {options.map((c) => {
            const was = exam.cohorts.some((x) => x.id === c.id);
            return (
              <Checkbox
                key={c.id}
                checked={picked.includes(c.id)}
                disabled={was && !draft}
                onCheckedChange={(on) => setPicked((p) => (on ? [...p, c.id] : p.filter((x) => x !== c.id)))}
                label={`${c.code} — ${c.name}`}
                description={was && !draft ? "Can't be removed after marks entry opens" : undefined}
              />
            );
          })}
        </div>
      ) : exam.cohorts.length === 0 ? (
        <p className="text-sm text-fg-subtle">No cohorts yet.</p>
      ) : (
        <ul className="flex flex-wrap gap-2">
          {exam.cohorts.map((c) => (
            <li key={c.id} className="rounded-lg border border-border bg-surface-2/40 px-3 py-2 text-sm">
              <span className="font-semibold text-fg">{c.code}</span>
              <span className="text-fg-muted"> · {c.name}</span>
              <span className={c.students ? "ml-2 text-fg-subtle" : "ml-2 text-warning"}>
                {formatNumber(c.students)} students
              </span>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

function Papers({ exam, canManage }: { exam: Exam; canManage: boolean }) {
  const setExam = useSetExam();
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [assigning, setAssigning] = useState<string | null>(null);
  const [removing, setRemoving] = useState<string | null>(null);
  const editable = canManage && SETUP_EDITABLE.includes(exam.status);
  const remove = useMutation({
    mutationFn: (paperId: string) => api.delete<Exam>(`${E}/${exam.id}/papers/${paperId}`),
    onSuccess: (e) => {
      setExam(e);
      setRemoving(null);
      toast.success("Paper removed");
    },
    onError: (e) => {
      setRemoving(null);
      toastError(e);
    },
  });
  const byId = (id: string | null) => exam.papers.find((p) => p.id === id);
  return (
    <Section
      title="Papers"
      description="Each paper is one course with the components marks are entered for."
      actions={
        editable && (
          <Button size="sm" leadingIcon={<Plus />} onClick={() => setAdding(true)}>
            Add paper
          </Button>
        )
      }
    >
      {exam.papers.length === 0 ? (
        <EmptyState
          compact
          icon={<FileText />}
          title="No papers yet"
          description="Add the courses examined, e.g. Internal 40 + External 60."
        />
      ) : (
        <ul className="divide-y divide-border" aria-label="Papers">
          {exam.papers.map((p) => (
            <li
              key={p.id}
              className="flex flex-col gap-2 py-3 first:pt-0 last:pb-0 sm:flex-row sm:items-start"
            >
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-fg">
                  {p.course_code} <span className="font-normal text-fg-muted">— {p.course_name}</span>
                </p>
                <p className="mt-0.5 text-[13px] text-fg-muted">
                  {p.components
                    .map(
                      (c) =>
                        `${c.label} ${trimNum(c.max)}${c.min_pass !== null ? ` (min ${trimNum(c.min_pass)})` : ""}`,
                    )
                    .join(" + ")}{" "}
                  = <span className="font-medium text-fg">{trimNum(p.max_total)}</span>
                  {p.pass_total !== null && <> · pass {trimNum(p.pass_total)}</>}
                  {p.credits !== null && <> · {trimNum(p.credits)} credits</>}
                </p>
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {exam.cohorts.map((c) => {
                    const names = p.assignments.filter((a) => a.cohort_id === c.id).map((a) => a.full_name);
                    return (
                      <Badge key={c.id} tone={names.length ? "neutral" : "warning"}>
                        {c.code}: {names.length ? names.join(", ") : "admins only"}
                      </Badge>
                    );
                  })}
                </div>
              </div>
              {canManage && (
                <Menu>
                  <MenuTrigger asChild>
                    <Button variant="ghost" size="icon-sm" aria-label={`Actions for ${p.course_code}`}>
                      <MoreHorizontal />
                    </Button>
                  </MenuTrigger>
                  <MenuContent align="end">
                    <MenuItem
                      icon={<Users />}
                      onSelect={() => setAssigning(p.id)}
                      disabled={!exam.cohorts.length}
                    >
                      Assign faculty
                    </MenuItem>
                    {editable && (
                      <MenuItem icon={<Pencil />} onSelect={() => setEditing(p.id)}>
                        Edit components
                      </MenuItem>
                    )}
                    {exam.status === "draft" && canManage && (
                      <MenuItem icon={<Trash2 />} destructive onSelect={() => setRemoving(p.id)}>
                        Remove paper
                      </MenuItem>
                    )}
                  </MenuContent>
                </Menu>
              )}
            </li>
          ))}
        </ul>
      )}
      {adding && <PaperDialog exam={exam} onClose={() => setAdding(false)} />}
      {byId(editing) && <PaperDialog exam={exam} paper={byId(editing)} onClose={() => setEditing(null)} />}
      {byId(assigning) && (
        <FacultyDialog exam={exam} paper={byId(assigning)!} onClose={() => setAssigning(null)} />
      )}
      {byId(removing) && (
        <ConfirmDialog
          open
          onOpenChange={(o) => !o && setRemoving(null)}
          title={`Remove ${byId(removing)?.course_code}?`}
          description="The paper and its faculty assignments are removed from this draft exam."
          confirmLabel="Remove paper"
          variant="danger"
          loading={remove.isPending}
          onConfirm={() => remove.mutate(removing!)}
        />
      )}
    </Section>
  );
}

export default function ExamWorkspacePage() {
  const { examId = "" } = useParams();
  const navigate = useNavigate();
  const canManage = useCan("exams.manage");
  const q = useExam(examId);
  const [deleting, setDeleting] = useState(false);
  const del = useMutation({
    mutationFn: () => api.delete(`${E}/${examId}`),
    onSuccess: () => {
      toast.success("Draft exam deleted");
      void navigate("/admin/exams");
    },
    onError: (e) => toastError(e),
  });
  if (q.isPending) return <Skeleton className="h-96 w-full" />;
  if (q.error) return <Callout tone="danger">This exam couldn't be loaded.</Callout>;
  const exam = q.data;
  return (
    <>
      <PageHeader
        breadcrumb={<Link to="/admin/exams">Exams</Link>}
        title={exam.name}
        meta={
          <>
            <ExamStatusBadge status={exam.status} />
            <span className="text-[13px] text-fg-subtle">
              {KIND_LABEL[exam.kind]} · {exam.term.name}, {exam.term.session_code} ·{" "}
              {exam.grading_scheme_name}
            </span>
          </>
        }
        actions={
          canManage &&
          exam.status === "draft" && (
            <Button variant="ghost" leadingIcon={<Trash2 />} onClick={() => setDeleting(true)}>
              Delete draft
            </Button>
          )
        }
      />
      <nav aria-label="Exam sections" className="mb-5 flex gap-1 border-b border-border">
        <span
          aria-current="page"
          className="-mb-px border-b-2 border-brand px-3 pb-2 text-sm font-semibold text-brand-ink"
        >
          Setup
        </span>
      </nav>
      <div className="flex flex-col gap-5">
        <Lifecycle exam={exam} canManage={canManage} />
        <Papers exam={exam} canManage={canManage} />
        <div className="grid items-start gap-5 lg:grid-cols-2">
          <Cohorts key={exam.version + exam.cohorts.length} exam={exam} canManage={canManage} />
          <Details key={exam.version} exam={exam} canManage={canManage} />
        </div>
      </div>
      <ConfirmDialog
        open={deleting}
        onOpenChange={setDeleting}
        title={`Delete “${exam.name}”?`}
        description="Draft exams have no marks yet; deleting removes its papers and assignments."
        confirmLabel="Delete exam"
        variant="danger"
        loading={del.isPending}
        onConfirm={() => del.mutate()}
      />
    </>
  );
}
