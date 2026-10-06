import { zodResolver } from "@hookform/resolvers/zod";
import { api, type AcademicSession, type Term } from "@scorecode/api-client";
import {
  Badge,
  Button,
  Checkbox,
  ConfirmDialog,
  EmptyState,
  Field,
  Input,
  Menu,
  MenuContent,
  MenuItem,
  MenuSeparator,
  MenuTrigger,
  Select,
  Skeleton,
  TBody,
  THead,
  Table,
  TableContainer,
  Td,
  Th,
  cn,
  formatDate,
  toast,
} from "@scorecode/ui";
import { useMutation } from "@tanstack/react-query";
import {
  Archive,
  ArchiveRestore,
  CalendarRange,
  Copy,
  MoreHorizontal,
  Pencil,
  Plus,
  Star,
} from "lucide-react";
import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { FormDialog } from "../../components/form-dialog";
import { applyServerError, toastError } from "../../lib/forms";
import { useCan } from "../../lib/session";
import { academicsApi, useInvalidateAcademics, useSessions, useTerms } from "./api";

const A = academicsApi.base;

const sessionSchema = z
  .object({
    code: z.string().trim().min(1, "Enter a code, e.g. 2025-26").max(32),
    name: z.string().trim().min(1, "Enter a name").max(100),
    starts_on: z.string().min(1, "Choose a start date"),
    ends_on: z.string().min(1, "Choose an end date"),
    make_current: z.boolean(),
  })
  .refine((v) => !v.starts_on || !v.ends_on || v.starts_on < v.ends_on, {
    path: ["ends_on"],
    message: "Must be after the start date",
  });
type SessionValues = z.infer<typeof sessionSchema>;

function SessionDialog({
  session,
  open,
  onOpenChange,
  onSaved,
}: {
  session?: AcademicSession;
  open: boolean;
  onOpenChange: (o: boolean) => void;
  onSaved: (s: AcademicSession) => void;
}) {
  const invalidate = useInvalidateAcademics();
  const [error, setError] = useState<unknown>(null);
  const form = useForm<SessionValues>({
    resolver: zodResolver(sessionSchema),
    defaultValues: session
      ? {
          code: session.code,
          name: session.name,
          starts_on: session.starts_on,
          ends_on: session.ends_on,
          make_current: false,
        }
      : { code: "", name: "", starts_on: "", ends_on: "", make_current: true },
  });
  const makeCurrent = useWatch({ control: form.control, name: "make_current" });
  const save = useMutation({
    mutationFn: (v: SessionValues) =>
      session
        ? api.put<AcademicSession>(`${A}/academic-sessions/${session.id}`, {
            code: v.code,
            name: v.name,
            starts_on: v.starts_on,
            ends_on: v.ends_on,
          })
        : api.post<AcademicSession>(`${A}/academic-sessions`, v),
    onSuccess: (s) => {
      invalidate();
      toast.success(session ? "Session updated" : `Session ${s.code} created`);
      onSaved(s);
      onOpenChange(false);
    },
    onError: (e) => {
      const msg = applyServerError(e, form.setError, ["code", "name", "starts_on", "ends_on"]);
      setError(msg ? e : null);
    },
  });
  return (
    <FormDialog
      open={open}
      onOpenChange={onOpenChange}
      title={session ? `Edit ${session.code}` : "New academic session"}
      description="A session is your academic year. Terms, cohorts and exams belong to a session."
      submitLabel={session ? "Save changes" : "Create session"}
      submitting={save.isPending}
      error={error}
      formId="session-form"
    >
      <form
        id="session-form"
        noValidate
        className="flex flex-col gap-5"
        onSubmit={form.handleSubmit((v) => {
          setError(null);
          save.mutate(v);
        })}
      >
        <div className="grid gap-5 sm:grid-cols-[160px_1fr]">
          <Field label="Code" error={form.formState.errors.code?.message}>
            <Input placeholder="2025-26" autoFocus {...form.register("code")} />
          </Field>
          <Field label="Name" error={form.formState.errors.name?.message}>
            <Input placeholder="Academic year 2025–26" {...form.register("name")} />
          </Field>
        </div>
        <div className="grid gap-5 sm:grid-cols-2">
          <Field label="Starts on" error={form.formState.errors.starts_on?.message}>
            <Input type="date" {...form.register("starts_on")} />
          </Field>
          <Field label="Ends on" error={form.formState.errors.ends_on?.message}>
            <Input type="date" {...form.register("ends_on")} />
          </Field>
        </div>
        {!session && (
          <Checkbox
            checked={makeCurrent}
            onCheckedChange={(c) => form.setValue("make_current", c)}
            label="Make this the current session"
            description="New exams and cohorts default to the current session."
          />
        )}
      </form>
    </FormDialog>
  );
}

const termSchema = z.object({
  code: z.string().trim().min(1, "Enter a code").max(32),
  name: z.string().trim().min(1, "Enter a name").max(100),
  sequence: z.string().regex(/^\d{1,2}$/, "A whole number from 1"),
  starts_on: z.string(),
  ends_on: z.string(),
});
type TermValues = z.infer<typeof termSchema>;

function TermDialog({
  session,
  term,
  nextSequence,
  open,
  onOpenChange,
}: {
  session: AcademicSession;
  term?: Term;
  nextSequence: number;
  open: boolean;
  onOpenChange: (o: boolean) => void;
}) {
  const invalidate = useInvalidateAcademics();
  const [error, setError] = useState<unknown>(null);
  const form = useForm<TermValues>({
    resolver: zodResolver(termSchema),
    defaultValues: term
      ? {
          code: term.code,
          name: term.name,
          sequence: String(term.sequence),
          starts_on: term.starts_on ?? "",
          ends_on: term.ends_on ?? "",
        }
      : { code: "", name: "", sequence: String(nextSequence), starts_on: "", ends_on: "" },
  });
  const save = useMutation({
    mutationFn: (v: TermValues) => {
      const body = {
        code: v.code,
        name: v.name,
        sequence: Number(v.sequence),
        starts_on: v.starts_on || null,
        ends_on: v.ends_on || null,
      };
      return term
        ? api.put<Term>(`${A}/terms/${term.id}`, body)
        : api.post<Term>(`${A}/academic-sessions/${session.id}/terms`, body);
    },
    onSuccess: () => {
      invalidate();
      toast.success(term ? "Term updated" : "Term added");
      onOpenChange(false);
    },
    onError: (e) => {
      const msg = applyServerError(e, form.setError, ["code", "name", "sequence", "starts_on", "ends_on"]);
      setError(msg ? e : null);
    },
  });
  return (
    <FormDialog
      open={open}
      onOpenChange={onOpenChange}
      title={term ? `Edit ${term.name}` : `Add a term to ${session.code}`}
      description="Semesters, terms or phases. Dates are optional but must fall inside the session."
      submitLabel={term ? "Save changes" : "Add term"}
      submitting={save.isPending}
      error={error}
      formId="term-form"
    >
      <form
        id="term-form"
        noValidate
        className="flex flex-col gap-5"
        onSubmit={form.handleSubmit((v) => {
          setError(null);
          save.mutate(v);
        })}
      >
        <div className="grid gap-5 sm:grid-cols-[140px_1fr_100px]">
          <Field label="Code" error={form.formState.errors.code?.message}>
            <Input placeholder="ODD" autoFocus {...form.register("code")} />
          </Field>
          <Field label="Name" error={form.formState.errors.name?.message}>
            <Input placeholder="Odd semester" {...form.register("name")} />
          </Field>
          <Field label="Order" error={form.formState.errors.sequence?.message}>
            <Input type="number" min={1} {...form.register("sequence")} />
          </Field>
        </div>
        <div className="grid gap-5 sm:grid-cols-2">
          <Field label="Starts on" optional error={form.formState.errors.starts_on?.message}>
            <Input
              type="date"
              min={session.starts_on}
              max={session.ends_on}
              {...form.register("starts_on")}
            />
          </Field>
          <Field label="Ends on" optional error={form.formState.errors.ends_on?.message}>
            <Input type="date" min={session.starts_on} max={session.ends_on} {...form.register("ends_on")} />
          </Field>
        </div>
      </form>
    </FormDialog>
  );
}

function CopyDialog({
  target,
  sessions,
  open,
  onOpenChange,
}: {
  target: AcademicSession;
  sessions: AcademicSession[];
  open: boolean;
  onOpenChange: (o: boolean) => void;
}) {
  const others = sessions.filter((s) => s.id !== target.id);
  const [source, setSource] = useState(others[0]?.id ?? "");
  const invalidate = useInvalidateAcademics();
  const copy = useMutation({
    mutationFn: () =>
      api.post<{ terms: number; cohorts: number }>(`${A}/academic-sessions/${target.id}/copy-structure`, {
        source_session_id: source,
      }),
    onSuccess: (r) => {
      invalidate();
      toast.success("Structure copied", {
        description:
          r.terms + r.cohorts === 0
            ? "Everything already existed — nothing new to copy."
            : `${r.terms} terms and ${r.cohorts} cohorts added to ${target.code}.`,
      });
      onOpenChange(false);
    },
    onError: (e) => toastError(e),
  });
  return (
    <FormDialog
      open={open}
      onOpenChange={onOpenChange}
      title={`Copy structure into ${target.code}`}
      description="Copies terms and active cohorts. Anything with the same code already in this session is left as it is, so you can run it again safely."
      submitLabel="Copy structure"
      submitting={copy.isPending}
      error={null}
      formId="copy-form"
      size="sm"
    >
      <form
        id="copy-form"
        onSubmit={(e) => {
          e.preventDefault();
          if (source) copy.mutate();
        }}
      >
        <Field label="Copy from">
          <Select value={source} onChange={(e) => setSource(e.target.value)}>
            {others.map((s) => (
              <option key={s.id} value={s.id}>
                {s.code} — {s.name}
              </option>
            ))}
          </Select>
        </Field>
      </form>
    </FormDialog>
  );
}

export default function SessionsPage() {
  const canManage = useCan("academics.manage");
  const [showArchived, setShowArchived] = useState(false);
  const sessions = useSessions(showArchived);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [dialog, setDialog] = useState<
    null | { kind: "session"; session?: AcademicSession } | { kind: "term"; term?: Term } | { kind: "copy" }
  >(null);
  const [confirm, setConfirm] = useState<null | "archive" | "restore" | "current">(null);
  const invalidate = useInvalidateAcademics();
  const list = sessions.data ?? [];
  const selected = list.find((s) => s.id === selectedId) ?? list.find((s) => s.is_current) ?? list[0];
  const terms = useTerms(selected?.id);

  const action = useMutation({
    mutationFn: (kind: "archive" | "restore" | "current") =>
      kind === "current"
        ? api.post(`${A}/academic-sessions/${selected!.id}/make-current`)
        : api.put(`${A}/academic-sessions/${selected!.id}/archived`, { archived: kind === "archive" }),
    onSuccess: (_d, kind) => {
      invalidate();
      toast.success(
        kind === "current"
          ? `${selected!.code} is now the current session`
          : kind === "archive"
            ? "Session archived"
            : "Session restored",
      );
      setConfirm(null);
    },
    onError: (e) => {
      toastError(e);
      setConfirm(null);
    },
  });

  if (sessions.isPending) {
    return (
      <div className="grid gap-6 xl:grid-cols-[280px_1fr]">
        <Skeleton className="h-64 rounded-xl" />
        <Skeleton className="h-80 rounded-xl" />
      </div>
    );
  }
  if (list.length === 0 && !showArchived) {
    return (
      <>
        <div className="rounded-xl border border-dashed border-border-strong bg-surface">
          <EmptyState
            icon={<CalendarRange />}
            title="Create your first academic session"
            description="Start with the current academic year (for example 2025-26). You'll add terms, cohorts and exams inside it."
            action={
              canManage && (
                <Button leadingIcon={<Plus />} onClick={() => setDialog({ kind: "session" })}>
                  New session
                </Button>
              )
            }
          />
        </div>
        {dialog?.kind === "session" && (
          <SessionDialog
            open
            onOpenChange={(o) => !o && setDialog(null)}
            onSaved={(s) => setSelectedId(s.id)}
          />
        )}
      </>
    );
  }
  const termRows = terms.data ?? [];
  return (
    <div className="grid gap-6 xl:grid-cols-[280px_minmax(0,1fr)]">
      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold">Sessions</h2>
          {canManage && (
            <Button
              size="sm"
              variant="secondary"
              leadingIcon={<Plus />}
              onClick={() => setDialog({ kind: "session" })}
            >
              New
            </Button>
          )}
        </div>
        <ul className="grid gap-1.5 sm:grid-cols-2 xl:grid-cols-1" aria-label="Academic sessions">
          {list.map((s) => (
            <li key={s.id}>
              <button
                type="button"
                onClick={() => setSelectedId(s.id)}
                aria-current={selected?.id === s.id}
                className={cn(
                  "flex w-full items-center gap-3 rounded-lg border px-3.5 py-3 text-left transition-colors",
                  selected?.id === s.id
                    ? "border-brand bg-brand-soft"
                    : "border-border bg-surface hover:border-border-strong",
                )}
              >
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-semibold">{s.code}</span>
                  <span className="block truncate text-[13px] text-fg-subtle">
                    {formatDate(s.starts_on)} – {formatDate(s.ends_on)}
                  </span>
                </span>
                {s.is_current && <Badge tone="brand">Current</Badge>}
                {s.archived_at && <Badge>Archived</Badge>}
              </button>
            </li>
          ))}
        </ul>
        <Checkbox checked={showArchived} onCheckedChange={setShowArchived} label="Show archived sessions" />
      </div>

      {selected && (
        <section
          className="rounded-xl border border-border bg-surface shadow-xs"
          aria-labelledby="session-title"
        >
          <div className="flex flex-wrap items-start justify-between gap-4 border-b border-border px-5 py-4">
            <div>
              <div className="flex items-center gap-2">
                <h2 id="session-title" className="text-[15px] font-semibold">
                  {selected.name}
                </h2>
                {selected.is_current && <Badge tone="brand">Current</Badge>}
              </div>
              <p className="mt-0.5 text-[13px] text-fg-subtle">
                {selected.code} · {formatDate(selected.starts_on)} – {formatDate(selected.ends_on)}
              </p>
            </div>
            {canManage && (
              <div className="flex items-center gap-2">
                <Button
                  size="sm"
                  variant="secondary"
                  leadingIcon={<Plus />}
                  onClick={() => setDialog({ kind: "term" })}
                  disabled={Boolean(selected.archived_at)}
                >
                  Add term
                </Button>
                <Menu>
                  <MenuTrigger asChild>
                    <Button size="icon-sm" variant="ghost" aria-label="Session actions">
                      <MoreHorizontal />
                    </Button>
                  </MenuTrigger>
                  <MenuContent>
                    <MenuItem
                      icon={<Pencil />}
                      onSelect={() => setDialog({ kind: "session", session: selected })}
                    >
                      Edit session
                    </MenuItem>
                    {!selected.is_current && !selected.archived_at && (
                      <MenuItem icon={<Star />} onSelect={() => setConfirm("current")}>
                        Make current
                      </MenuItem>
                    )}
                    {list.length > 1 && !selected.archived_at && (
                      <MenuItem icon={<Copy />} onSelect={() => setDialog({ kind: "copy" })}>
                        Copy structure from another session…
                      </MenuItem>
                    )}
                    <MenuSeparator />
                    {selected.archived_at ? (
                      <MenuItem icon={<ArchiveRestore />} onSelect={() => setConfirm("restore")}>
                        Restore session
                      </MenuItem>
                    ) : (
                      <MenuItem
                        icon={<Archive />}
                        destructive
                        disabled={selected.is_current}
                        onSelect={() => setConfirm("archive")}
                      >
                        Archive session
                      </MenuItem>
                    )}
                  </MenuContent>
                </Menu>
              </div>
            )}
          </div>
          <div className="p-5">
            <h3 className="mb-3 text-[13px] font-semibold uppercase tracking-wide text-fg-subtle">Terms</h3>
            {terms.isPending ? (
              <Skeleton className="h-24" />
            ) : termRows.length === 0 ? (
              <p className="rounded-lg border border-dashed border-border-strong px-4 py-6 text-center text-sm text-fg-subtle">
                No terms yet. Add semesters, terms or phases — exams are scheduled within a term.
              </p>
            ) : (
              <TableContainer className="shadow-none">
                <Table>
                  <THead>
                    <tr>
                      <Th className="w-14">#</Th>
                      <Th>Term</Th>
                      <Th className="hidden sm:table-cell">Dates</Th>
                      <Th className="w-12">
                        <span className="sr-only">Edit</span>
                      </Th>
                    </tr>
                  </THead>
                  <TBody>
                    {termRows.map((t) => (
                      <tr key={t.id}>
                        <Td className="tabular text-fg-subtle">{t.sequence}</Td>
                        <Td>
                          <span className="block font-medium">{t.name}</span>
                          <span className="block font-mono text-xs text-fg-subtle">{t.code}</span>
                        </Td>
                        <Td className="hidden text-fg-subtle sm:table-cell">
                          {t.starts_on || t.ends_on
                            ? `${formatDate(t.starts_on)} – ${formatDate(t.ends_on)}`
                            : "—"}
                        </Td>
                        <Td className="px-2">
                          {canManage && (
                            <Button
                              size="icon-sm"
                              variant="ghost"
                              aria-label={`Edit ${t.name}`}
                              onClick={() => setDialog({ kind: "term", term: t })}
                            >
                              <Pencil />
                            </Button>
                          )}
                        </Td>
                      </tr>
                    ))}
                  </TBody>
                </Table>
              </TableContainer>
            )}
          </div>
        </section>
      )}

      {dialog?.kind === "session" && (
        <SessionDialog
          session={dialog.session}
          open
          onOpenChange={(o) => !o && setDialog(null)}
          onSaved={(s) => setSelectedId(s.id)}
        />
      )}
      {dialog?.kind === "term" && selected && (
        <TermDialog
          session={selected}
          term={dialog.term}
          nextSequence={termRows.reduce((m, t) => Math.max(m, t.sequence), 0) + 1}
          open
          onOpenChange={(o) => !o && setDialog(null)}
        />
      )}
      {dialog?.kind === "copy" && selected && (
        <CopyDialog
          target={selected}
          sessions={list.filter((s) => !s.archived_at)}
          open
          onOpenChange={(o) => !o && setDialog(null)}
        />
      )}
      <ConfirmDialog
        open={confirm !== null}
        onOpenChange={(o) => !o && setConfirm(null)}
        loading={action.isPending}
        onConfirm={() => {
          if (confirm) action.mutate(confirm);
        }}
        title={
          confirm === "current"
            ? `Make ${selected?.code} the current session?`
            : confirm === "archive"
              ? `Archive ${selected?.code}?`
              : `Restore ${selected?.code}?`
        }
        description={
          confirm === "current"
            ? "New cohorts and exams will default to this session. Nothing in other sessions changes."
            : confirm === "archive"
              ? "Archived sessions are hidden from lists and pickers. Their cohorts, exams and results are kept."
              : "The session will appear in lists and pickers again."
        }
        confirmLabel={confirm === "current" ? "Make current" : confirm === "archive" ? "Archive" : "Restore"}
        variant={confirm === "archive" ? "danger" : "primary"}
      />
    </div>
  );
}
