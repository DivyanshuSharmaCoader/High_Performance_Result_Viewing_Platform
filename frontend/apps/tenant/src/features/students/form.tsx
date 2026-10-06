import { zodResolver } from "@hookform/resolvers/zod";
import { api, type Student } from "@scorecode/api-client";
import { Field, Input, Select, toast } from "@scorecode/ui";
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { FormDialog } from "../../components/form-dialog";
import { applyServerError } from "../../lib/forms";
import { S, useCurrentCohorts, useInvalidateStudents } from "./api";

const schema = z.object({
  enrollment_no: z
    .string()
    .trim()
    .min(1, "Enter the enrollment number")
    .max(40)
    .regex(/^[A-Za-z0-9][A-Za-z0-9/._\- ]*$/, "Use letters, digits and / . _ - only"),
  full_name: z.string().trim().min(1, "Enter the student's name").max(200),
  email: z.union([z.literal(""), z.email("Enter a valid email address")]),
  phone: z.string().trim().max(32),
  date_of_birth: z.string(),
  guardian_name: z.string().trim().max(200),
  admission_year: z.string().regex(/^(|\d{4})$/, "Use four digits, e.g. 2024"),
  cohort_id: z.string(),
});
type Values = z.infer<typeof schema>;
const FIELDS = [
  "enrollment_no",
  "full_name",
  "email",
  "phone",
  "date_of_birth",
  "guardian_name",
  "admission_year",
  "cohort_id",
] as const;

export function StudentDialog({
  student,
  onClose,
  onSaved,
}: {
  student?: Student;
  onClose: () => void;
  onSaved?: (s: Student) => void;
}) {
  const { cohorts, session } = useCurrentCohorts();
  const invalidate = useInvalidateStudents();
  const [error, setError] = useState<unknown>(null);
  const frozen = Boolean(student && student.account !== "none");
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      enrollment_no: student?.enrollment_no ?? "",
      full_name: student?.full_name ?? "",
      email: student?.email ?? "",
      phone: student?.phone ?? "",
      date_of_birth: student?.date_of_birth ?? "",
      guardian_name: student?.guardian_name ?? "",
      admission_year: student?.admission_year ? String(student.admission_year) : "",
      cohort_id: "",
    },
  });
  const save = useMutation({
    mutationFn: (v: Values) => {
      const body = {
        enrollment_no: v.enrollment_no,
        full_name: v.full_name,
        email: v.email || null,
        phone: v.phone || null,
        date_of_birth: v.date_of_birth || null,
        guardian_name: v.guardian_name || null,
        admission_year: v.admission_year ? Number(v.admission_year) : null,
      };
      return student
        ? api.put<Student>(`${S}/${student.id}`, { ...body, version: student.version })
        : api.post<Student>(S, { ...body, cohort_ids: v.cohort_id ? [v.cohort_id] : [] });
    },
    onSuccess: (s) => {
      invalidate();
      toast.success(student ? "Student updated" : `${s.full_name} added`, {
        description: student ? undefined : `Enrollment no. ${s.enrollment_no}`,
      });
      onSaved?.(s);
      onClose();
    },
    onError: (e) => setError(applyServerError(e, form.setError, FIELDS) ? e : null),
  });
  const errors = form.formState.errors;
  return (
    <FormDialog
      open
      onOpenChange={(o) => !o && onClose()}
      title={student ? `Edit ${student.full_name}` : "Add a student"}
      description={
        student ? undefined : "Students can also be added in bulk from a spreadsheet with Import students."
      }
      submitLabel={student ? "Save changes" : "Add student"}
      submitting={save.isPending}
      error={error}
      formId="student-form"
      size="lg"
    >
      <form
        id="student-form"
        noValidate
        className="flex flex-col gap-5"
        onSubmit={form.handleSubmit((v) => {
          setError(null);
          save.mutate(v);
        })}
      >
        <div className="grid gap-5 sm:grid-cols-[200px_1fr]">
          <Field
            label="Enrollment no."
            error={errors.enrollment_no?.message}
            description={frozen ? "Locked: it's this student's login." : "Also their login ID."}
          >
            <Input
              autoFocus={!student}
              autoComplete="off"
              spellCheck={false}
              readOnly={frozen}
              className="font-mono"
              {...form.register("enrollment_no")}
            />
          </Field>
          <Field label="Full name" error={errors.full_name?.message}>
            <Input autoFocus={Boolean(student)} autoComplete="off" {...form.register("full_name")} />
          </Field>
        </div>
        <div className="grid gap-5 sm:grid-cols-2">
          <Field label="Email" optional error={errors.email?.message}>
            <Input type="email" autoComplete="off" {...form.register("email")} />
          </Field>
          <Field label="Phone" optional error={errors.phone?.message}>
            <Input type="tel" autoComplete="off" {...form.register("phone")} />
          </Field>
          <Field label="Date of birth" optional error={errors.date_of_birth?.message}>
            <Input type="date" {...form.register("date_of_birth")} />
          </Field>
          <Field label="Admission year" optional error={errors.admission_year?.message}>
            <Input inputMode="numeric" placeholder="2025" {...form.register("admission_year")} />
          </Field>
        </div>
        <Field label="Parent or guardian" optional error={errors.guardian_name?.message}>
          <Input autoComplete="off" {...form.register("guardian_name")} />
        </Field>
        {!student && (
          <Field
            label="Cohort"
            optional
            description={session ? `In ${session.name}.` : "Create a session and cohorts first."}
            error={errors.cohort_id?.message}
          >
            <Select {...form.register("cohort_id")} disabled={cohorts.length === 0}>
              <option value="">Not in a cohort yet</option>
              {cohorts.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.code} — {c.name}
                </option>
              ))}
            </Select>
          </Field>
        )}
      </form>
    </FormDialog>
  );
}
