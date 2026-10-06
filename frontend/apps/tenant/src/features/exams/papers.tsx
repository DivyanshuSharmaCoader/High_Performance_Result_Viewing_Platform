import {
  api,
  type Course,
  type CourseList,
  type Exam,
  type ExamPaper,
  type Staff,
} from "@scorecode/api-client";
import { Button, Checkbox, Field, Input, Select, Switch, toast } from "@scorecode/ui";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";

import { FormDialog } from "../../components/form-dialog";
import { applyServerError } from "../../lib/forms";
import { COMPONENT_PRESETS, E, trimNum, useSetExam, type ComponentDraft } from "./api";

function ComponentsEditor({
  value,
  onChange,
}: {
  value: ComponentDraft[];
  onChange: (next: ComponentDraft[]) => void;
}) {
  const update = (i: number, patch: Partial<ComponentDraft>) =>
    onChange(value.map((c, j) => (j === i ? { ...c, ...patch } : c)));
  const total = value.reduce((sum, c) => sum + (Number(c.max) || 0), 0);
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-1.5">
        {COMPONENT_PRESETS.map((p) => (
          <Button
            key={p.label}
            type="button"
            variant="secondary"
            size="sm"
            onClick={() => onChange(p.components.map((c) => ({ ...c })))}
          >
            {p.label}
          </Button>
        ))}
      </div>
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full text-sm">
          <thead className="bg-surface-2/60 text-left text-xs text-fg-subtle">
            <tr>
              <th className="px-3 py-2 font-medium">Code</th>
              <th className="px-3 py-2 font-medium">Name</th>
              <th className="px-3 py-2 font-medium">Out of</th>
              <th className="px-3 py-2 font-medium">Minimum to pass</th>
              <th className="w-10 px-2 py-2">
                <span className="sr-only">Remove</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {value.map((c, i) => (
              <tr key={i} className="border-t border-border">
                <td className="px-3 py-2">
                  <Input
                    aria-label={`Component ${i + 1} code`}
                    value={c.code}
                    onChange={(e) => update(i, { code: e.target.value.toUpperCase() })}
                    className="h-8 w-20 font-mono"
                  />
                </td>
                <td className="px-3 py-2">
                  <Input
                    aria-label={`Component ${i + 1} name`}
                    value={c.label}
                    onChange={(e) => update(i, { label: e.target.value })}
                    className="h-8 min-w-32"
                  />
                </td>
                <td className="px-3 py-2">
                  <Input
                    aria-label={`Component ${i + 1} maximum`}
                    inputMode="decimal"
                    value={c.max}
                    onChange={(e) => update(i, { max: e.target.value })}
                    className="h-8 w-20"
                  />
                </td>
                <td className="px-3 py-2">
                  <Input
                    aria-label={`Component ${i + 1} minimum to pass`}
                    inputMode="decimal"
                    value={c.min_pass}
                    placeholder="—"
                    onChange={(e) => update(i, { min_pass: e.target.value })}
                    className="h-8 w-20"
                  />
                </td>
                <td className="px-2 py-2">
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    aria-label={`Remove component ${c.code || i + 1}`}
                    disabled={value.length <= 1}
                    onClick={() => onChange(value.filter((_, j) => j !== i))}
                  >
                    <Trash2 />
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-between">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          leadingIcon={<Plus />}
          disabled={value.length >= 10}
          onClick={() => onChange([...value, { code: "", label: "", max: "", min_pass: "" }])}
        >
          Add component
        </Button>
        <p className="text-[13px] text-fg-muted">
          Paper total: <span className="font-semibold tabular text-fg">{trimNum(total.toFixed(2))}</span>
        </p>
      </div>
    </div>
  );
}

const toBody = (comps: ComponentDraft[]) =>
  comps.map((c) => ({
    code: c.code.trim(),
    label: c.label.trim() || c.code.trim(),
    max: c.max.trim() || "0",
    min_pass: c.min_pass.trim() || null,
  }));

/** Add a paper (course × exam) or edit an existing one's components, pass mark and credits. */
export function PaperDialog({
  exam,
  paper,
  onClose,
}: {
  exam: Exam;
  paper?: ExamPaper;
  onClose: () => void;
}) {
  const setExam = useSetExam();
  const courses = useQuery({
    queryKey: ["academics", "courses", "all-active"],
    queryFn: () => api.get<CourseList>("/api/v1/admin/courses", { query: { limit: 200 } }),
    enabled: !paper,
  });
  const taken = new Set(exam.papers.map((p) => p.course_id));
  const options: Course[] = (courses.data?.items ?? []).filter((c) => !c.archived_at && !taken.has(c.id));
  const [courseId, setCourseId] = useState("");
  const course = options.find((c) => c.id === (courseId || options[0]?.id));
  const [components, setComponents] = useState<ComponentDraft[]>(
    paper
      ? paper.components.map((c) => ({
          code: c.code,
          label: c.label,
          max: trimNum(c.max),
          min_pass: trimNum(c.min_pass),
        }))
      : COMPONENT_PRESETS[0]!.components.map((c) => ({ ...c })),
  );
  const [passTotal, setPassTotal] = useState(trimNum(paper?.pass_total));
  const [courseCredits, setCourseCredits] = useState(!paper);
  const [credits, setCredits] = useState(trimNum(paper?.credits));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<unknown>(null);
  const save = useMutation({
    mutationFn: () => {
      const body = {
        components: toBody(components),
        pass_total: passTotal.trim() || null,
        credits: courseCredits && !paper ? null : credits.trim() || null,
      };
      return paper
        ? api.put<Exam>(`${E}/${exam.id}/papers/${paper.id}`, body)
        : api.post<Exam>(`${E}/${exam.id}/papers`, {
            ...body,
            course_id: course?.id,
            use_course_credits: courseCredits,
          });
    },
    onSuccess: (e) => {
      setExam(e);
      toast.success(paper ? `${paper.course_code} updated` : `${course?.code} added`);
      onClose();
    },
    onError: (e) => {
      const placed: Record<string, string> = {};
      const msg = applyServerError(
        e,
        (field, err) => {
          placed[String(field)] = err.message ?? "";
        },
        ["course_id", "pass_total", "credits"],
      );
      setErrors(placed);
      setError(msg ? e : null);
    },
  });
  return (
    <FormDialog
      open
      onOpenChange={(o) => !o && onClose()}
      title={paper ? `${paper.course_code} — ${paper.course_name}` : "Add a paper"}
      description="A paper is one course in this exam, made of the components faculty enter marks for."
      submitLabel={paper ? "Save paper" : "Add paper"}
      submitting={save.isPending}
      error={error}
      formId="paper-form"
      size="lg"
    >
      <form
        id="paper-form"
        noValidate
        className="flex flex-col gap-5"
        onSubmit={(e) => {
          e.preventDefault();
          setErrors({});
          setError(null);
          save.mutate();
        }}
      >
        {!paper && (
          <Field
            label="Course"
            error={errors.course_id}
            description={
              options.length ? undefined : "Every course is already a paper, or no courses exist yet."
            }
          >
            <Select
              value={course?.id ?? ""}
              onChange={(e) => setCourseId(e.target.value)}
              disabled={!options.length}
            >
              {options.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.code} — {c.name}
                </option>
              ))}
            </Select>
          </Field>
        )}
        <Field label="Components">
          <ComponentsEditor value={components} onChange={setComponents} />
        </Field>
        <div className="grid gap-5 sm:grid-cols-2">
          <Field
            label="Pass mark (out of the total)"
            optional
            error={errors.pass_total}
            description="Leave empty to use the grading scheme's pass percentage."
          >
            <Input inputMode="decimal" value={passTotal} onChange={(e) => setPassTotal(e.target.value)} />
          </Field>
          <Field label="Credits" optional error={errors.credits}>
            {!paper ? (
              <div className="flex flex-col gap-2">
                <Switch
                  checked={courseCredits}
                  onCheckedChange={setCourseCredits}
                  label={`Use the course's credits${course?.credits ? ` (${trimNum(course.credits)})` : ""}`}
                />
                {!courseCredits && (
                  <Input
                    aria-label="Credits"
                    inputMode="decimal"
                    value={credits}
                    onChange={(e) => setCredits(e.target.value)}
                  />
                )}
              </div>
            ) : (
              <Input inputMode="decimal" value={credits} onChange={(e) => setCredits(e.target.value)} />
            )}
          </Field>
        </div>
      </form>
    </FormDialog>
  );
}

/** Choose which faculty may enter marks for one paper, cohort by cohort. */
export function FacultyDialog({
  exam,
  paper,
  onClose,
}: {
  exam: Exam;
  paper: ExamPaper;
  onClose: () => void;
}) {
  const setExam = useSetExam();
  const staff = useQuery({ queryKey: ["staff"], queryFn: () => api.get<Staff[]>("/api/v1/admin/staff") });
  const faculty = (staff.data ?? []).filter((s) => s.role === "faculty" && s.status !== "disabled");
  const [picked, setPicked] = useState<Record<string, string[]>>(() =>
    Object.fromEntries(
      exam.cohorts.map((c) => [
        c.id,
        paper.assignments.filter((a) => a.cohort_id === c.id).map((a) => a.user_id),
      ]),
    ),
  );
  const [error, setError] = useState<unknown>(null);
  const save = useMutation({
    mutationFn: async () => {
      let latest = exam;
      for (const c of exam.cohorts) {
        const before = paper.assignments
          .filter((a) => a.cohort_id === c.id)
          .map((a) => a.user_id)
          .sort();
        const after = [...(picked[c.id] ?? [])].sort();
        if (before.join() !== after.join())
          latest = await api.put<Exam>(`${E}/${exam.id}/papers/${paper.id}/assignments`, {
            cohort_id: c.id,
            user_ids: after,
          });
      }
      return latest;
    },
    onSuccess: (e) => {
      setExam(e);
      toast.success("Faculty assigned");
      onClose();
    },
    onError: (e) => setError(e),
  });
  return (
    <FormDialog
      open
      onOpenChange={(o) => !o && onClose()}
      title={`Faculty for ${paper.course_code}`}
      description="Assigned faculty can enter and submit marks for this paper in their cohorts. Administrators can always enter marks."
      submitLabel="Save"
      submitting={save.isPending}
      error={error}
      formId="faculty-form"
    >
      <form
        id="faculty-form"
        className="flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        {faculty.length === 0 ? (
          <p className="text-sm text-fg-muted">Invite faculty from the Staff page first.</p>
        ) : (
          exam.cohorts.map((c) => (
            <fieldset key={c.id} className="rounded-lg border border-border p-3">
              <legend className="px-1 text-[13px] font-semibold text-fg">
                {c.code} <span className="font-normal text-fg-subtle">· {c.name}</span>
              </legend>
              <div className="grid gap-2 sm:grid-cols-2">
                {faculty.map((f) => (
                  <Checkbox
                    key={f.id}
                    checked={(picked[c.id] ?? []).includes(f.id)}
                    onCheckedChange={(on) =>
                      setPicked((p) => ({
                        ...p,
                        [c.id]: on ? [...(p[c.id] ?? []), f.id] : (p[c.id] ?? []).filter((x) => x !== f.id),
                      }))
                    }
                    label={f.full_name}
                    description={f.designation ?? f.email ?? undefined}
                  />
                ))}
              </div>
            </fieldset>
          ))
        )}
      </form>
    </FormDialog>
  );
}
