import { zodResolver } from "@hookform/resolvers/zod";
import { api } from "@scorecode/api-client";
import { Button, Callout, Field, toast } from "@scorecode/ui";
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { Link, useNavigate, useSearchParams } from "react-router";
import { z } from "zod";

import { AuthLayout } from "../../components/auth-layout";
import { PasswordInput, PasswordStrength } from "../../components/password-input";
import { applyServerError } from "../../lib/forms";

const schema = z
  .object({ password: z.string().min(10, "Use at least 10 characters"), confirm: z.string() })
  .refine((v) => v.password === v.confirm, { path: ["confirm"], message: "Passwords don't match" });
type Values = z.infer<typeof schema>;

export default function ResetPasswordPage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const navigate = useNavigate();
  const [formError, setFormError] = useState<string | null>(null);
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { password: "", confirm: "" },
  });
  const password = useWatch({ control: form.control, name: "password" });
  const reset = useMutation({
    mutationFn: (v: Values) => api.post("/api/v1/auth/password/reset", { token, password: v.password }),
    onSuccess: () => {
      toast.success("Password updated", {
        description: "Sign in with your new password. Other devices were signed out.",
      });
      void navigate("/login", { replace: true });
    },
    onError: (e) => setFormError(applyServerError(e, form.setError, ["password"])),
  });

  if (!token) {
    return (
      <AuthLayout title="This link is incomplete">
        <p className="text-sm leading-6 text-fg-muted">
          Open the link from your email again, or{" "}
          <Link to="/forgot-password" className="font-medium text-brand-ink hover:underline">
            request a new one
          </Link>
          .
        </p>
      </AuthLayout>
    );
  }
  return (
    <AuthLayout title="Choose a new password" subtitle="You'll be signed out of other devices.">
      <form
        noValidate
        className="flex flex-col gap-5"
        onSubmit={form.handleSubmit((v) => {
          setFormError(null);
          reset.mutate(v);
        })}
      >
        {formError && (
          <Callout
            tone="danger"
            action={
              <Link to="/forgot-password" className="text-[13px] font-medium text-brand-ink hover:underline">
                New link
              </Link>
            }
          >
            {formError}
          </Callout>
        )}
        <Field label="New password" error={form.formState.errors.password?.message}>
          <PasswordInput autoComplete="new-password" autoFocus {...form.register("password")} />
        </Field>
        <PasswordStrength value={password} minLength={10} />
        <Field label="Confirm password" error={form.formState.errors.confirm?.message}>
          <PasswordInput autoComplete="new-password" {...form.register("confirm")} />
        </Field>
        <Button type="submit" size="lg" loading={reset.isPending}>
          Update password
        </Button>
      </form>
    </AuthLayout>
  );
}
