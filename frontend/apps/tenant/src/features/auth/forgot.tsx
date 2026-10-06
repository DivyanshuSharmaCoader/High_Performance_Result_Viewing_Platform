import { zodResolver } from "@hookform/resolvers/zod";
import { api, ApiError } from "@scorecode/api-client";
import { Button, Callout, Field, Input } from "@scorecode/ui";
import { useMutation } from "@tanstack/react-query";
import { MailCheck } from "lucide-react";
import { useForm } from "react-hook-form";
import { Link } from "react-router";
import { z } from "zod";

import { AuthLayout } from "../../components/auth-layout";

const schema = z.object({ identifier: z.string().trim().min(1, "Enter your email or enrollment number") });
type Values = z.infer<typeof schema>;

export default function ForgotPasswordPage() {
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { identifier: "" } });
  const send = useMutation({ mutationFn: (v: Values) => api.post("/api/v1/auth/password/forgot", v) });

  if (send.isSuccess) {
    return (
      <AuthLayout title="Check your email">
        <div className="flex flex-col gap-5">
          <div className="flex size-11 items-center justify-center rounded-xl bg-brand-soft text-brand-ink">
            <MailCheck className="size-5" aria-hidden />
          </div>
          <p className="text-sm leading-6 text-fg-muted">
            If an account with an email address matches{" "}
            <span className="font-medium text-fg">{form.getValues("identifier")}</span>, we've sent a link to
            reset the password. It works once and expires in 60 minutes.
          </p>
          <p className="text-sm leading-6 text-fg-subtle">
            Students without an email on file should ask their institution for a new activation code.
          </p>
          <Link to="/login" className="text-sm font-medium text-brand-ink hover:underline">
            ← Back to sign in
          </Link>
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      title="Reset your password"
      subtitle="Enter the email or enrollment number on your account and we'll email you a reset link."
      footer={
        <Link to="/login" className="font-medium text-brand-ink hover:underline">
          ← Back to sign in
        </Link>
      }
    >
      <form noValidate className="flex flex-col gap-5" onSubmit={form.handleSubmit((v) => send.mutate(v))}>
        {send.error && (
          <Callout tone="danger">
            {send.error instanceof ApiError ? send.error.detail : "Something went wrong. Please try again."}
          </Callout>
        )}
        <Field label="Email or enrollment number" error={form.formState.errors.identifier?.message}>
          <Input autoComplete="username" autoFocus {...form.register("identifier")} />
        </Field>
        <Button type="submit" size="lg" loading={send.isPending}>
          Send reset link
        </Button>
      </form>
    </AuthLayout>
  );
}
