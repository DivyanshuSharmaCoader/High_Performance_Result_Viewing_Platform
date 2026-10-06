import { zodResolver } from "@hookform/resolvers/zod";
import { api, type Cohort, type Course, type Department, type Program } from "@scorecode/api-client";
import {
  Button,
  Checkbox,
  EmptyState,
  Field,
  Input,
  OffsetPagination,
  SearchInput,
  Select,
  TBody,
  THead,
  Table,
  TableContainer,
  TableSkeletonRows,
  Td,
  Th,
  Toolbar,
  formatNumber,
  toast,
} from "@scorecode/ui";
import { useMutation } from "@tanstack/react-query";
import { BookOpen, Building, GraduationCap, Plus, Users2 } from "lucide-react";
import { useDeferredValue, useMemo, useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { FormDialog } from "../../components/form-dialog";
import { applyServerError } from "../../lib/forms";
import { useCan } from "../../lib/session";
import { useFeature } from "../../lib/tenant";
import {
  academicsApi,
  useCohorts,
  useCourses,
  useDepartments,
  useInvalidateAcademics,
  usePrograms,
  useSessions,
} from "./api";
import { NameCell, RowActions } from "./shared";

const A = academicsApi.base;
const code = (label = "Enter a code") => z.string().trim().min(1, label).max(40);
const name = z.string().trim().min(1, "Enter a name").max(200);

function useSave<V, R>(
  path: (v: V) => [method: "post" | "put", url: string, body: unknown],
  fields: string[],
  onDone: (r: R) => void,
) {
  const invalidate = useInvalidateAcademics();
  const [error, setError] = useState<unknown>(null);
  const mutation = useMutation({
    mutationFn: (v: V) => {
      const [method, url, body] = path(v);
      return method === "post" ? api.post<R>(url, body) : api.put<R>(url, body);
    },
    onSuccess: (r) => {
      invalidate();
      onDone(r);
    },
  });
  return { mutation, error, setError, fields };
}

function ListShell({
  toolbar,
  columns,
  loading,
  empty,
  children,
  hasRows,
}: {
  toolbar?: ReactNode;
  columns: ReactNode;
  loading: boolean;
  empty: ReactNode;
  children: ReactNode;
  hasRows: boolean;
}) {
  return (
    <>
      {toolbar && <Toolbar>{toolbar}</Toolbar>}
      <TableContainer>
        <Table>
          <THead>
            <tr>{columns}</tr>
          </THead>
          <TBody>
            {loading ? (
              <TableSkeletonRows cols={4} rows={5} />
            ) : !hasRows ? (
              <tr>
                <td colSpan={6}>{empty}</td>
              </tr>
            ) : (
              children
            )}
          </TBody>
        </Table>
      </TableContainer>
    </>
  );
}

// ---- departments --------------------------------------------------------------------------------

const deptSchema = z.object({ code: code(), name });
type DeptValues = z.infer<typeof deptSchema>;

function DepartmentDialog({ item, onClose }: { item?: Department; onClose: () => void }) {
  const form = useForm<DeptValues>({
    resolver: zodResolver(deptSchema),
    defaultValues: item ? { code: item.code, name: item.name } : { code: "", name: "" },
  });
  const { mutation, error, setError } = useSave<DeptValues, Department>(
    (v) => (item ? ["put", `${A}/departments/${item.id}`, v] : ["post", `${A}/departments`, v]),
    ["code", "name"],
    (d) => {
      toast.success(item ? "Department updated" : `Department ${d.code} created`);
      onClose();
    },
  );
  return (
    <FormDialog
      open
      onOpenChange={(o) => !o && onClose()}
      title={item ? `Edit ${item.code}` : "New department"}
      submitLabel={item ? "Save changes" : "Create department"}
      submitting={mutation.isPending}
      error={error}
      formId="dept-form"
      size="sm"
    >
      <form
        id="dept-form"
        noValidate
        className="flex flex-col gap-5"
        onSubmit={form.handleSubmit((v) => {
          setError(null);
          mutation.mutate(v, {
            onError: (e) => setError(applyServerError(e, form.setError, ["code", "name"]) ? e : null),
          });
        })}
      >
        <Field label="Code" error={form.formState.errors.code?.message}>
          <Input placeholder="CSED" autoFocus {...form.register("code")} />
        </Field>
        <Field label="Name" error={form.formState.errors.name?.message}>
          <Input placeholder="Computer Science & Engineering" {...form.register("name")} />
        </Field>
      </form>
    </FormDialog>
  );
}

export function DepartmentsPage() {
  const canManage = useCan("academics.manage");
  const multiple = useFeature("multiple_departments");
  const [archived, setArchived] = useState(false);
  const [editing, setEditing] = useState<Department | "new" | null>(null);
  const q = useDepartments(archived);
  const rows = q.data ?? [];
  const activeCount = rows.filter((d) => !d.archived_at).length;
  return (
    <>
      <ListShell
        loading={q.isPending}
        hasRows={rows.length > 0}
        toolbar={
          <>
            <Checkbox checked={archived} onCheckedChange={setArchived} label="Show archived" />
            <div className="ml-auto flex items-center gap-3">
              {!multiple && activeCount >= 1 && (
                <span className="text-[13px] text-fg-subtle">Your plan includes one department.</span>
              )}
              {canManage && (
                <Button size="sm" leadingIcon={<Plus />} onClick={() => setEditing("new")}>
                  New department
                </Button>
              )}
            </div>
          </>
        }
        columns={
          <>
            <Th>Department</Th>
            <Th className="w-12 px-2">
              <span className="sr-only">Actions</span>
            </Th>
          </>
        }
        empty={
          <EmptyState
            compact
            icon={<Building />}
            title="No departments"
            description="Departments are optional. Use them to group programs and courses — for example wings, faculties or streams."
          />
        }
      >
        {rows.map((d) => (
          <tr key={d.id}>
            <Td className="w-full max-w-0">
              <NameCell code={d.code} name={d.name} archived={Boolean(d.archived_at)} />
            </Td>
            <Td className="px-2">
              {canManage && (
                <RowActions
                  item={d}
                  resource="departments"
                  noun="department"
                  onEdit={setEditing}
                  archiveHint="Archived departments can't be chosen for new programs or courses. Existing ones keep it."
                />
              )}
            </Td>
          </tr>
        ))}
      </ListShell>
      {editing && (
        <DepartmentDialog item={editing === "new" ? undefined : editing} onClose={() => setEditing(null)} />
      )}
    </>
  );
}

// ---- programs -----------------------------------------------------------------------------------

const programSchema = z.object({
  code: code(),
  name,
  department_id: z.string(),
  level: z.string().trim().max(60),
  duration_terms: z.string().regex(/^\d{0,2}$/, "Whole number of terms"),
});
type ProgramValues = z.infer<typeof programSchema>;

function ProgramDialog({
  item,
  departments,
  onClose,
}: {
  item?: Program;
  departments: Department[];
  onClose: () => void;
}) {
  const form = useForm<ProgramValues>({
    resolver: zodResolver(programSchema),
    defaultValues: item
      ? {
          code: item.code,
          name: item.name,
          department_id: item.department_id ?? "",
          level: item.level ?? "",
          duration_terms: item.duration_terms ? String(item.duration_terms) : "",
        }
      : { code: "", name: "", department_id: departments[0]?.id ?? "", level: "", duration_terms: "" },
  });
  const toBody = (v: ProgramValues) => ({
    code: v.code,
    name: v.name,
    department_id: v.department_id || null,
    level: v.level || null,
    duration_terms: v.duration_terms ? Number(v.duration_terms) : null,
  });
  const { mutation, error, setError } = useSave<ProgramValues, Program>(
    (v) => (item ? ["put", `${A}/programs/${item.id}`, toBody(v)] : ["post", `${A}/programs`, toBody(v)]),
    [],
    (p) => {
      toast.success(item ? "Program updated" : `Program ${p.code} created`);
      onClose();
    },
  );
  return (
    <FormDialog
      open
      onOpenChange={(o) => !o && onClose()}
      title={item ? `Edit ${item.code}` : "New program"}
      description="A class, degree or course of study — e.g. Class 8, B.E. Computer Engineering, JEE 2027."
      submitLabel={item ? "Save changes" : "Create program"}
      submitting={mutation.isPending}
      error={error}
      formId="program-form"
    >
      <form
        id="program-form"
        noValidate
        className="flex flex-col gap-5"
        onSubmit={form.handleSubmit((v) => {
          setError(null);
          mutation.mutate(v, {
            onError: (e) =>
              setError(
                applyServerError(e, form.setError, [
                  "code",
                  "name",
                  "department_id",
                  "level",
                  "duration_terms",
                ])
                  ? e
                  : null,
              ),
          });
        })}
      >
        <div className="grid gap-5 sm:grid-cols-[160px_1fr]">
          <Field label="Code" error={form.formState.errors.code?.message}>
            <Input placeholder="BE-COE" autoFocus {...form.register("code")} />
          </Field>
          <Field label="Name" error={form.formState.errors.name?.message}>
            <Input placeholder="B.E. Computer Engineering" {...form.register("name")} />
          </Field>
        </div>
        <Field label="Department" optional error={form.formState.errors.department_id?.message}>
          <Select {...form.register("department_id")}>
            <option value="">No department</option>
            {departments.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name} ({d.code})
              </option>
            ))}
          </Select>
        </Field>
        <div className="grid gap-5 sm:grid-cols-2">
          <Field label="Level" optional description="e.g. Undergraduate, Secondary">
            <Input {...form.register("level")} />
          </Field>
          <Field label="Duration (terms)" optional error={form.formState.errors.duration_terms?.message}>
            <Input inputMode="numeric" {...form.register("duration_terms")} />
          </Field>
        </div>
      </form>
    </FormDialog>
  );
}

export function ProgramsPage() {
  const canManage = useCan("academics.manage");
  const [archived, setArchived] = useState(false);
  const [editing, setEditing] = useState<Program | "new" | null>(null);
  const q = usePrograms(archived);
  const departments = useDepartments(false);
  const deptName = useMemo(
    () => new Map((departments.data ?? []).map((d) => [d.id, d.name])),
    [departments.data],
  );
  const rows = q.data ?? [];
  return (
    <>
      <ListShell
        loading={q.isPending}
        hasRows={rows.length > 0}
        toolbar={
          <>
            <Checkbox checked={archived} onCheckedChange={setArchived} label="Show archived" />
            {canManage && (
              <Button size="sm" className="ml-auto" leadingIcon={<Plus />} onClick={() => setEditing("new")}>
                New program
              </Button>
            )}
          </>
        }
        columns={
          <>
            <Th>Program</Th>
            <Th className="hidden md:table-cell">Department</Th>
            <Th className="hidden md:table-cell">Level</Th>
            <Th className="hidden text-right md:table-cell">Terms</Th>
            <Th className="w-12 px-2">
              <span className="sr-only">Actions</span>
            </Th>
          </>
        }
        empty={
          <EmptyState
            compact
            icon={<GraduationCap />}
            title="No programs yet"
            description="Add the classes, degrees or courses of study you run."
          />
        }
      >
        {rows.map((p) => (
          <tr key={p.id}>
            <Td className="w-full max-w-0">
              <NameCell code={p.code} name={p.name} archived={Boolean(p.archived_at)} />
            </Td>
            <Td className="hidden whitespace-nowrap text-fg-muted md:table-cell">
              {p.department_id ? (deptName.get(p.department_id) ?? "—") : "—"}
            </Td>
            <Td className="hidden whitespace-nowrap text-fg-muted md:table-cell">{p.level ?? "—"}</Td>
            <Td className="tabular hidden text-right md:table-cell">{p.duration_terms ?? "—"}</Td>
            <Td className="px-2">
              {canManage && (
                <RowActions
                  item={p}
                  resource="programs"
                  noun="program"
                  onEdit={setEditing}
                  archiveHint="Archived programs can't get new cohorts. Existing cohorts and results are kept."
                />
              )}
            </Td>
          </tr>
        ))}
      </ListShell>
      {editing && (
        <ProgramDialog
          item={editing === "new" ? undefined : editing}
          departments={departments.data ?? []}
          onClose={() => setEditing(null)}
        />
      )}
    </>
  );
}

// ---- cohorts ------------------------------------------------------------------------------------

const cohortSchema = z.object({
  code: code("Enter a code, e.g. 8A"),
  name,
  program_id: z.string().min(1, "Choose a program"),
  session_id: z.string().min(1, "Choose a session"),
});
type CohortValues = z.infer<typeof cohortSchema>;

function CohortDialog({
  item,
  programs,
  sessions,
  defaults,
  onClose,
}: {
  item?: Cohort;
  programs: Program[];
  sessions: { id: string; code: string }[];
  defaults: { session_id: string; program_id: string };
  onClose: () => void;
}) {
  const form = useForm<CohortValues>({
    resolver: zodResolver(cohortSchema),
    defaultValues: item
      ? { code: item.code, name: item.name, program_id: item.program_id, session_id: item.session_id }
      : {
          code: "",
          name: "",
          program_id: defaults.program_id || programs[0]?.id || "",
          session_id: defaults.session_id || sessions[0]?.id || "",
        },
  });
  const { mutation, error, setError } = useSave<CohortValues, Cohort>(
    (v) =>
      item ? ["put", `${A}/cohorts/${item.id}`, { code: v.code, name: v.name }] : ["post", `${A}/cohorts`, v],
    [],
    (c) => {
      toast.success(item ? "Cohort updated" : `Cohort ${c.code} created`);
      onClose();
    },
  );
  return (
    <FormDialog
      open
      onOpenChange={(o) => !o && onClose()}
      title={item ? `Edit ${item.code}` : "New cohort"}
      description="A section, batch or group of students in one program for one session."
      submitLabel={item ? "Save changes" : "Create cohort"}
      submitting={mutation.isPending}
      error={error}
      formId="cohort-form"
    >
      <form
        id="cohort-form"
        noValidate
        className="flex flex-col gap-5"
        onSubmit={form.handleSubmit((v) => {
          setError(null);
          mutation.mutate(v, {
            onError: (e) =>
              setError(
                applyServerError(e, form.setError, ["code", "name", "program_id", "session_id"]) ? e : null,
              ),
          });
        })}
      >
        <div className="grid gap-5 sm:grid-cols-2">
          <Field label="Session" error={form.formState.errors.session_id?.message}>
            <Select disabled={Boolean(item)} {...form.register("session_id")}>
              {sessions.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.code}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Program" error={form.formState.errors.program_id?.message}>
            <Select disabled={Boolean(item)} {...form.register("program_id")}>
              {programs.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <div className="grid gap-5 sm:grid-cols-[160px_1fr]">
          <Field label="Code" error={form.formState.errors.code?.message}>
            <Input placeholder="8A" autoFocus {...form.register("code")} />
          </Field>
          <Field label="Name" error={form.formState.errors.name?.message}>
            <Input placeholder="Class 8 · Section A" {...form.register("name")} />
          </Field>
        </div>
      </form>
    </FormDialog>
  );
}

export function CohortsPage() {
  const canManage = useCan("academics.manage");
  const sessions = useSessions(false);
  const programs = usePrograms(false);
  const current = sessions.data?.find((s) => s.is_current)?.id ?? sessions.data?.[0]?.id ?? "";
  const [sessionId, setSessionId] = useState("");
  const [programId, setProgramId] = useState("");
  const [archived, setArchived] = useState(false);
  const [editing, setEditing] = useState<Cohort | "new" | null>(null);
  const effectiveSession = sessionId || current;
  const q = useCohorts(effectiveSession, programId, archived);
  const progName = useMemo(() => new Map((programs.data ?? []).map((p) => [p.id, p.name])), [programs.data]);
  const rows = q.data ?? [];
  const noPrereqs = (sessions.data?.length ?? 0) === 0 || (programs.data?.length ?? 0) === 0;
  return (
    <>
      <ListShell
        loading={q.isPending || sessions.isPending}
        hasRows={rows.length > 0}
        toolbar={
          <>
            <Select
              value={effectiveSession}
              onChange={(e) => setSessionId(e.target.value)}
              className="w-40"
              aria-label="Session"
            >
              {(sessions.data ?? []).map((s) => (
                <option key={s.id} value={s.id}>
                  {s.code}
                  {s.is_current ? " (current)" : ""}
                </option>
              ))}
            </Select>
            <Select
              value={programId}
              onChange={(e) => setProgramId(e.target.value)}
              className="w-56"
              aria-label="Program"
            >
              <option value="">All programs</option>
              {(programs.data ?? []).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </Select>
            <Checkbox checked={archived} onCheckedChange={setArchived} label="Show archived" />
            {canManage && (
              <Button
                size="sm"
                className="ml-auto"
                leadingIcon={<Plus />}
                onClick={() => setEditing("new")}
                disabled={noPrereqs}
              >
                New cohort
              </Button>
            )}
          </>
        }
        columns={
          <>
            <Th>Cohort</Th>
            <Th className="hidden md:table-cell">Program</Th>
            <Th className="w-12 px-2">
              <span className="sr-only">Actions</span>
            </Th>
          </>
        }
        empty={
          <EmptyState
            compact
            icon={<Users2 />}
            title={noPrereqs ? "Add a session and a program first" : "No cohorts in this session"}
            description={
              noPrereqs
                ? "Cohorts belong to a program in a session."
                : "Create sections or batches, or copy them from a previous session on the Sessions tab."
            }
          />
        }
      >
        {rows.map((c) => (
          <tr key={c.id}>
            <Td className="w-full max-w-0">
              <NameCell code={c.code} name={c.name} archived={Boolean(c.archived_at)} />
            </Td>
            <Td className="hidden whitespace-nowrap text-fg-muted md:table-cell">
              {progName.get(c.program_id) ?? "—"}
            </Td>
            <Td className="px-2">
              {canManage && (
                <RowActions
                  item={c}
                  resource="cohorts"
                  noun="cohort"
                  onEdit={setEditing}
                  archiveHint="Archived cohorts are hidden from pickers. Their students and results are kept."
                />
              )}
            </Td>
          </tr>
        ))}
      </ListShell>
      {editing && (
        <CohortDialog
          item={editing === "new" ? undefined : editing}
          programs={programs.data ?? []}
          sessions={sessions.data ?? []}
          defaults={{ session_id: effectiveSession, program_id: programId }}
          onClose={() => setEditing(null)}
        />
      )}
    </>
  );
}

// ---- courses ------------------------------------------------------------------------------------

const courseSchema = z.object({
  code: code("Enter a code, e.g. UCS301"),
  name,
  department_id: z.string(),
  credits: z.string().regex(/^$|^\d{1,2}(\.\d)?$/, "Up to one decimal place, e.g. 3.5"),
});
type CourseValues = z.infer<typeof courseSchema>;

function CourseDialog({
  item,
  departments,
  onClose,
}: {
  item?: Course;
  departments: Department[];
  onClose: () => void;
}) {
  const form = useForm<CourseValues>({
    resolver: zodResolver(courseSchema),
    defaultValues: item
      ? {
          code: item.code,
          name: item.name,
          department_id: item.department_id ?? "",
          credits: item.credits ?? "",
        }
      : { code: "", name: "", department_id: "", credits: "" },
  });
  const toBody = (v: CourseValues) => ({
    code: v.code,
    name: v.name,
    department_id: v.department_id || null,
    credits: v.credits || null,
  });
  const { mutation, error, setError } = useSave<CourseValues, Course>(
    (v) => (item ? ["put", `${A}/courses/${item.id}`, toBody(v)] : ["post", `${A}/courses`, toBody(v)]),
    [],
    (c) => {
      toast.success(item ? "Course updated" : `Course ${c.code} created`);
      onClose();
    },
  );
  return (
    <FormDialog
      open
      onOpenChange={(o) => !o && onClose()}
      title={item ? `Edit ${item.code}` : "New course"}
      description="A subject in your catalogue. Exams add papers for courses."
      submitLabel={item ? "Save changes" : "Create course"}
      submitting={mutation.isPending}
      error={error}
      formId="course-form"
    >
      <form
        id="course-form"
        noValidate
        className="flex flex-col gap-5"
        onSubmit={form.handleSubmit((v) => {
          setError(null);
          mutation.mutate(v, {
            onError: (e) =>
              setError(
                applyServerError(e, form.setError, ["code", "name", "department_id", "credits"]) ? e : null,
              ),
          });
        })}
      >
        <div className="grid gap-5 sm:grid-cols-[160px_1fr]">
          <Field label="Code" error={form.formState.errors.code?.message}>
            <Input placeholder="UCS301" autoFocus {...form.register("code")} />
          </Field>
          <Field label="Name" error={form.formState.errors.name?.message}>
            <Input placeholder="Data Structures" {...form.register("name")} />
          </Field>
        </div>
        <div className="grid gap-5 sm:grid-cols-2">
          <Field label="Department" optional>
            <Select {...form.register("department_id")}>
              <option value="">No department</option>
              {departments.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field
            label="Credits"
            optional
            description="For credit-based grading (SGPA)."
            error={form.formState.errors.credits?.message}
          >
            <Input inputMode="decimal" placeholder="4.0" {...form.register("credits")} />
          </Field>
        </div>
      </form>
    </FormDialog>
  );
}

const PAGE = 50;

export function CoursesPage() {
  const canManage = useCan("academics.manage");
  const [search, setSearch] = useState("");
  const [departmentId, setDepartmentId] = useState("");
  const [archived, setArchived] = useState(false);
  const [offset, setOffset] = useState(0);
  const [editing, setEditing] = useState<Course | "new" | null>(null);
  const deferred = useDeferredValue(search.trim());
  const departments = useDepartments(false);
  const q = useCourses(deferred, departmentId, archived, offset, PAGE);
  const deptName = useMemo(
    () => new Map((departments.data ?? []).map((d) => [d.id, d.name])),
    [departments.data],
  );
  const rows = q.data?.items ?? [];
  return (
    <>
      <ListShell
        loading={q.isPending}
        hasRows={rows.length > 0}
        toolbar={
          <>
            <SearchInput
              value={search}
              onValueChange={(v) => {
                setSearch(v);
                setOffset(0);
              }}
              placeholder="Search code or name"
              className="w-full sm:w-64"
              aria-label="Search courses"
            />
            {(departments.data?.length ?? 0) > 0 && (
              <Select
                value={departmentId}
                onChange={(e) => {
                  setDepartmentId(e.target.value);
                  setOffset(0);
                }}
                className="w-56"
                aria-label="Department"
              >
                <option value="">All departments</option>
                {(departments.data ?? []).map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name}
                  </option>
                ))}
              </Select>
            )}
            <Checkbox
              checked={archived}
              onCheckedChange={(c) => {
                setArchived(c);
                setOffset(0);
              }}
              label="Show archived"
            />
            {canManage && (
              <Button size="sm" className="ml-auto" leadingIcon={<Plus />} onClick={() => setEditing("new")}>
                New course
              </Button>
            )}
          </>
        }
        columns={
          <>
            <Th>Course</Th>
            <Th className="hidden md:table-cell">Department</Th>
            <Th className="text-right">Credits</Th>
            <Th className="w-12 px-2">
              <span className="sr-only">Actions</span>
            </Th>
          </>
        }
        empty={
          deferred ? (
            <EmptyState compact title="No courses match" description="Try another code or name." />
          ) : (
            <EmptyState
              compact
              icon={<BookOpen />}
              title="No courses yet"
              description="Add the subjects you examine. Credits are optional and used for SGPA."
            />
          )
        }
      >
        {rows.map((c) => (
          <tr key={c.id}>
            <Td className="w-full max-w-0">
              <NameCell code={c.code} name={c.name} archived={Boolean(c.archived_at)} />
            </Td>
            <Td className="hidden whitespace-nowrap text-fg-muted md:table-cell">
              {c.department_id ? (deptName.get(c.department_id) ?? "—") : "—"}
            </Td>
            <Td className="tabular text-right">{c.credits ? formatNumber(Number(c.credits), 1) : "—"}</Td>
            <Td className="px-2">
              {canManage && (
                <RowActions
                  item={c}
                  resource="courses"
                  noun="course"
                  onEdit={setEditing}
                  archiveHint="Archived courses can't be added to new exams. Past papers and results are kept."
                />
              )}
            </Td>
          </tr>
        ))}
      </ListShell>
      {q.data && <OffsetPagination offset={offset} limit={PAGE} total={q.data.total} onChange={setOffset} />}
      {editing && (
        <CourseDialog
          item={editing === "new" ? undefined : editing}
          departments={departments.data ?? []}
          onClose={() => setEditing(null)}
        />
      )}
    </>
  );
}
