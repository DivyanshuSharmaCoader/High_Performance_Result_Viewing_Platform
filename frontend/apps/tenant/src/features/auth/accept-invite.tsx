import { zodResolver } from "@hookform/resolvers/zod";
import { api, isApiError, type SessionOut } from "@scorecode/api-client";
import { Button, Callout, Field, Input, Skeleton } from "@scorecode/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { Link, useNavigate, useSearchParams } from "react-router";
import { z } from "zod";

import { AuthLayout } from "../../components/auth-layout";
import { PasswordInput, PasswordStrength } from "../../components/password-input";
import { applyServerError } from "../../lib/forms";
import { meKey } from "../../lib/session";

const schema = z
  .object({
    password: z.string().min(12, "Staff passwords need at least 12 characters"),
    confirm: z.string(),
  })
  .refine((v) => v.password === v.confirm, { path: ["confirm"], message: "Passwords don't match" });
type Values = z.infer<typeof schema>;

export default function AcceptInvitePage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [formError, setFormError] = useState<string | null>(null);
  const invite = useQuery({
    queryKey: ["invite", token],
    queryFn: () =>
      api.get<{ full_name: string; email: string }>(`/api/v1/auth/invitations/${encodeURIComponent(token)}`),
    enabled: token.length > 0,
    retry: false,
  });
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { password: "", confirm: "" },
  });
  const password = useWatch({ control: form.control, name: "password" });
  const accept = useMutation({
    mutationFn: (v: Values) =>
      api.post<SessionOut>("/api/v1/auth/invitations/accept", { token, password: v.password }),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: meKey });
      void navigate("/", { replace: true });
    },
    onError: (e) => setFormError(applyServerError(e, form.setError, ["password"])),
  });

  if (!token || (invite.error && isApiError(invite.error, 404))) {
    return (
      <AuthLayout title="This invitation isn't valid">
        <p className="text-sm leading-6 text-fg-muted">
          It may have expired or already been used. Ask the person who invited you to send a new invitation,
          or{" "}
          <Link to="/login" className="font-medium text-brand-ink hover:underline">
            sign in
          </Link>{" "}
          if you've already set up your account.
        </p>
      </AuthLayout>
    );
  }
  return (
    <AuthLayout
      title="Join your institution"
      subtitle="Choose a password to finish setting up your staff account."
    >
      {invite.isPending ? (
        <div className="flex flex-col gap-4" aria-busy="true">
          <Skeleton className="h-16" />
          <Skeleton className="h-9" />
          <Skeleton className="h-9" />
        </div>
      ) : (
        <form
          noValidate
          className="flex flex-col gap-5"
          onSubmit={form.handleSubmit((v) => {
            setFormError(null);
            accept.mutate(v);
          })}
        >
          {formError && <Callout tone="danger">{formError}</Callout>}
          <Field label="Name">
            <Input value={invite.data?.full_name ?? ""} readOnly disabled />
          </Field>
          <Field label="Email (your sign-in)">
            <Input value={invite.data?.email ?? ""} readOnly disabled autoComplete="username" />
          </Field>
          <Field label="Password" error={form.formState.errors.password?.message}>
            <PasswordInput autoComplete="new-password" autoFocus {...form.register("password")} />
          </Field>
          <PasswordStrength value={password} minLength={12} />
          <Field label="Confirm password" error={form.formState.errors.confirm?.message}>
            <PasswordInput autoComplete="new-password" {...form.register("confirm")} />
          </Field>
          <Button type="submit" size="lg" loading={accept.isPending}>
            Create account
          </Button>
        </form>
      )}
    </AuthLayout>
  );
}
