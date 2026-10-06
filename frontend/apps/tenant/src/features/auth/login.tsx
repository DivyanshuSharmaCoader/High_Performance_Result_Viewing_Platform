import { zodResolver } from "@hookform/resolvers/zod";
import { api, ApiError, type SessionOut } from "@scorecode/api-client";
import { Button, Callout, Field, Input } from "@scorecode/ui";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate, useSearchParams } from "react-router";
import { z } from "zod";

import { AuthLayout } from "../../components/auth-layout";
import { PasswordInput } from "../../components/password-input";
import { homePathFor, meKey, safeNext } from "../../lib/session";
import type { Me } from "@scorecode/api-client";

const schema = z.object({
  login_id: z.string().trim().min(1, "Enter your email or enrollment number"),
  password: z.string().min(1, "Enter your password"),
});
type Values = z.infer<typeof schema>;

export default function LoginPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [formError, setFormError] = useState<{ message: string; retryAt?: number } | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { login_id: "", password: "" },
  });

  useEffect(() => {
    if (!formError?.retryAt) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [formError?.retryAt]);

  const login = useMutation({
    mutationFn: (values: Values) => api.post<SessionOut>("/api/v1/auth/login", values),
    onSuccess: async () => {
      const me = await qc.fetchQuery({ queryKey: meKey, queryFn: () => api.get<Me>("/api/v1/me") });
      void navigate(safeNext(params.get("next")) ?? homePathFor(me), { replace: true });
    },
    onError: (error) => {
      form.setValue("password", "");
      if (error instanceof ApiError && error.status === 429) {
        setFormError({
          message: "Too many sign-in attempts.",
          retryAt: Date.now() + (error.retryAfter ?? 30) * 1000,
        });
      } else if (error instanceof ApiError && error.status === 401) {
        setFormError({ message: error.detail });
      } else {
        setFormError({
          message: error instanceof ApiError ? error.detail : "Something went wrong. Please try again.",
        });
      }
    },
  });

  const waitSeconds = formError?.retryAt ? Math.max(0, Math.ceil((formError.retryAt - now) / 1000)) : 0;

  return (
    <AuthLayout
      title="Sign in"
      subtitle="Use the email or enrollment number your institution registered for you."
      footer={
        <>
          First time here?{" "}
          <Link to="/activate" className="font-medium text-brand-ink hover:underline">
            Activate your student account
          </Link>
        </>
      }
    >
      <form
        noValidate
        onSubmit={form.handleSubmit((values) => {
          setFormError(null);
          login.mutate(values);
        })}
        className="flex flex-col gap-5"
      >
        {formError && (
          <Callout tone="danger" title={formError.retryAt ? formError.message : "We couldn't sign you in"}>
            {formError.retryAt
              ? waitSeconds > 0
                ? `Please wait ${waitSeconds} second${waitSeconds === 1 ? "" : "s"} before trying again.`
                : "You can try again now."
              : formError.message}
          </Callout>
        )}
        <Field label="Email or enrollment number" error={form.formState.errors.login_id?.message}>
          <Input
            autoComplete="username"
            autoCapitalize="none"
            spellCheck={false}
            autoFocus
            {...form.register("login_id")}
          />
        </Field>
        <Field
          label="Password"
          error={form.formState.errors.password?.message}
          aside={
            <Link to="/forgot-password" className="text-[13px] font-medium text-brand-ink hover:underline">
              Forgot password?
            </Link>
          }
        >
          <PasswordInput autoComplete="current-password" {...form.register("password")} />
        </Field>
        <Button type="submit" size="lg" loading={login.isPending} disabled={waitSeconds > 0}>
          Sign in
        </Button>
      </form>
    </AuthLayout>
  );
}
