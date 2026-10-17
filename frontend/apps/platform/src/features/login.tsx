import { zodResolver } from "@hookform/resolvers/zod";
import { api, ApiError } from "@scorecode/api-client";
import { Button, Callout, Field, Input, PasswordInput } from "@scorecode/ui";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ShieldCheck } from "lucide-react";
import { useForm } from "react-hook-form";
import { useNavigate, useSearchParams } from "react-router";
import { z } from "zod";

import { meKey, safeNext } from "../lib/session";

const schema = z.object({
  email: z.email("Enter your work email"),
  password: z.string().min(1, "Enter your password"),
  totp_code: z
    .string()
    .trim()
    .transform((v) => v.replace(/\s/g, ""))
    .pipe(z.string().regex(/^\d{6}$/, "Enter the 6-digit code from your authenticator app")),
});
type Values = z.input<typeof schema>;

export default function LoginPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const qc = useQueryClient();
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { email: "", password: "", totp_code: "" },
  });
  const login = useMutation({
    mutationFn: (v: z.output<typeof schema>) => api.post("/api/v1/platform/auth/login", v),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: meKey });
      void navigate(safeNext(params.get("next")), { replace: true });
    },
    onError: () => form.resetField("totp_code"),
  });
  return (
    <main className="flex min-h-dvh items-center justify-center bg-bg px-4 py-12">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex items-center gap-2.5">
          <span className="flex size-9 items-center justify-center rounded-lg bg-white">
            <img src="/logo-mark.png" alt="" className="size-7" width={28} height={28} />
          </span>
          <div>
            <p className="text-sm font-semibold">ScoreCode Console</p>
            <p className="text-xs text-fg-subtle">Staff access only</p>
          </div>
        </div>
        <div className="rounded-xl border border-border bg-surface p-6 shadow-sm">
          <h1 className="text-lg font-semibold">Sign in</h1>
          <p className="mt-1 text-sm text-fg-subtle">
            Two-factor authentication is required for every sign-in.
          </p>
          <form
            noValidate
            className="mt-6 flex flex-col gap-4"
            onSubmit={form.handleSubmit((v) => login.mutate(schema.parse(v)))}
          >
            {login.error && (
              <Callout tone="danger">
                {login.error instanceof ApiError && login.error.status === 429
                  ? "Too many attempts. Wait a minute and try again."
                  : "Those details didn't match. Check your email, password and code."}
              </Callout>
            )}
            <Field label="Work email" error={form.formState.errors.email?.message}>
              <Input type="email" autoComplete="username" autoFocus {...form.register("email")} />
            </Field>
            <Field label="Password" error={form.formState.errors.password?.message}>
              <PasswordInput autoComplete="current-password" {...form.register("password")} />
            </Field>
            <Field label="Authenticator code" error={form.formState.errors.totp_code?.message}>
              <Input
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={7}
                className="font-mono tracking-[0.3em]"
                leading={<ShieldCheck />}
                {...form.register("totp_code")}
              />
            </Field>
            <Button type="submit" size="lg" loading={login.isPending} className="mt-2">
              Sign in
            </Button>
          </form>
        </div>
      </div>
    </main>
  );
}
