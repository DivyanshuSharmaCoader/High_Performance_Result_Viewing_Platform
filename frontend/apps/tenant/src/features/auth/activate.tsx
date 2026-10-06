import { zodResolver } from "@hookform/resolvers/zod";
import { api, type SessionOut } from "@scorecode/api-client";
import { Button, Callout, Field, Input } from "@scorecode/ui";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { Link, useNavigate } from "react-router";
import { z } from "zod";

import { AuthLayout } from "../../components/auth-layout";
import { PasswordInput, PasswordStrength } from "../../components/password-input";
import { applyServerError } from "../../lib/forms";
import { meKey } from "../../lib/session";

const schema = z
  .object({
    enrollment_no: z.string().trim().min(1, "Enter your enrollment or roll number"),
    code: z
      .string()
      .trim()
      .transform((v) => v.replace(/[\s-]/g, "").toUpperCase())
      .pipe(z.string().min(8, "The code on your slip has 10 characters")),
    password: z.string().min(10, "Use at least 10 characters"),
    confirm: z.string(),
  })
  .refine((v) => v.password === v.confirm, { path: ["confirm"], message: "Passwords don't match" });
type Values = z.input<typeof schema>;

export default function ActivatePage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [formError, setFormError] = useState<string | null>(null);
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { enrollment_no: "", code: "", password: "", confirm: "" },
  });
  const password = useWatch({ control: form.control, name: "password" });

  const activate = useMutation({
    mutationFn: (v: z.output<typeof schema>) =>
      api.post<SessionOut>("/api/v1/auth/activate", {
        enrollment_no: v.enrollment_no,
        code: v.code,
        password: v.password,
      }),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: meKey });
      void navigate("/", { replace: true });
    },
    onError: (error) =>
      setFormError(applyServerError(error, form.setError, ["enrollment_no", "code", "password"])),
  });

  return (
    <AuthLayout
      title="Activate your account"
      subtitle="Enter the activation code from the slip or email your institution gave you, then choose a password."
      footer={
        <>
          Already activated?{" "}
          <Link to="/login" className="font-medium text-brand-ink hover:underline">
            Sign in
          </Link>
        </>
      }
    >
      <form
        noValidate
        className="flex flex-col gap-5"
        onSubmit={form.handleSubmit((values) => {
          setFormError(null);
          activate.mutate(schema.parse(values));
        })}
      >
        {formError && <Callout tone="danger">{formError}</Callout>}
        <Field label="Enrollment / roll number" error={form.formState.errors.enrollment_no?.message}>
          <Input
            autoComplete="username"
            autoCapitalize="characters"
            spellCheck={false}
            autoFocus
            {...form.register("enrollment_no")}
          />
        </Field>
        <Field
          label="Activation code"
          description="10 characters, like 7KQ3-M9XD-PA. Letters O and I are read as 0 and 1."
          error={form.formState.errors.code?.message}
        >
          <Input
            autoComplete="one-time-code"
            autoCapitalize="characters"
            spellCheck={false}
            className="font-mono tracking-wider"
            {...form.register("code")}
          />
        </Field>
        <Field label="New password" error={form.formState.errors.password?.message}>
          <PasswordInput autoComplete="new-password" {...form.register("password")} />
        </Field>
        <PasswordStrength value={password} minLength={10} />
        <Field label="Confirm password" error={form.formState.errors.confirm?.message}>
          <PasswordInput autoComplete="new-password" {...form.register("confirm")} />
        </Field>
        <Button type="submit" size="lg" loading={activate.isPending}>
          Activate and sign in
        </Button>
      </form>
    </AuthLayout>
  );
}
