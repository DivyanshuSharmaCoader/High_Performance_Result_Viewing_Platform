import { zodResolver } from "@hookform/resolvers/zod";
import { api } from "@scorecode/api-client";
import {
  Badge,
  Button,
  Callout,
  ConfirmDialog,
  DescriptionList,
  Field,
  formatRelative,
  PageHeader,
  PasswordInput,
  PasswordStrength,
  Section,
  SkeletonText,
  toast,
} from "@scorecode/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Laptop, LogOut, Smartphone } from "lucide-react";
import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { useNavigate } from "react-router";
import { z } from "zod";

import { applyServerError } from "../../lib/forms";
import { useSession } from "../../lib/session";

interface SessionItem {
  current: boolean;
  created_at: string;
  last_seen_at: string;
  ip: string | null;
  user_agent: string | null;
}

function deviceLabel(ua: string | null): { label: string; mobile: boolean } {
  if (!ua) return { label: "Unknown device", mobile: false };
  const mobile = /Mobile|Android|iPhone/i.test(ua);
  const browser = /Edg\//.test(ua)
    ? "Edge"
    : /Chrome\//.test(ua)
      ? "Chrome"
      : /Firefox\//.test(ua)
        ? "Firefox"
        : /Safari\//.test(ua)
          ? "Safari"
          : "Browser";
  const os = /Windows/.test(ua)
    ? "Windows"
    : /Mac OS X/.test(ua)
      ? "macOS"
      : /Android/.test(ua)
        ? "Android"
        : /iPhone|iPad/.test(ua)
          ? "iOS"
          : /Linux/.test(ua)
            ? "Linux"
            : "";
  return { label: os ? `${browser} on ${os}` : browser, mobile };
}

function ChangePassword({ staff }: { staff: boolean }) {
  const min = staff ? 12 : 10;
  const schema = z
    .object({
      current_password: z.string().min(1, "Enter your current password"),
      new_password: z.string().min(min, `Use at least ${min} characters`),
      confirm: z.string(),
    })
    .refine((v) => v.new_password === v.confirm, { path: ["confirm"], message: "Passwords don't match" });
  type Values = z.infer<typeof schema>;
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { current_password: "", new_password: "", confirm: "" },
  });
  const newPassword = useWatch({ control: form.control, name: "new_password" });
  const qc = useQueryClient();
  const [formError, setFormError] = useState<string | null>(null);
  const change = useMutation({
    mutationFn: (v: Values) =>
      api.put("/api/v1/me/password", { current_password: v.current_password, new_password: v.new_password }),
    onSuccess: () => {
      form.reset();
      void qc.invalidateQueries({ queryKey: ["my-sessions"] });
      toast.success("Password changed", { description: "Your other devices were signed out." });
    },
    onError: (e) =>
      setFormError(applyServerError(e, form.setError, ["current_password", "new_password", "password"])),
  });
  return (
    <form
      noValidate
      onSubmit={form.handleSubmit((v) => {
        setFormError(null);
        change.mutate(v);
      })}
      className="flex max-w-md flex-col gap-4"
    >
      {formError && <Callout tone="danger">{formError}</Callout>}
      <Field label="Current password" error={form.formState.errors.current_password?.message}>
        <PasswordInput autoComplete="current-password" {...form.register("current_password")} />
      </Field>
      <Field label="New password" error={form.formState.errors.new_password?.message}>
        <PasswordInput autoComplete="new-password" {...form.register("new_password")} />
      </Field>
      <PasswordStrength value={newPassword} minLength={min} />
      <Field label="Confirm new password" error={form.formState.errors.confirm?.message}>
        <PasswordInput autoComplete="new-password" {...form.register("confirm")} />
      </Field>
      <div>
        <Button type="submit" loading={change.isPending}>
          Change password
        </Button>
      </div>
    </form>
  );
}

export default function AccountPage() {
  const me = useSession();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [confirmAll, setConfirmAll] = useState(false);
  const sessions = useQuery({
    queryKey: ["my-sessions"],
    queryFn: () => api.get<SessionItem[]>("/api/v1/me/sessions"),
  });
  const logoutAll = useMutation({
    mutationFn: () => api.post("/api/v1/auth/logout-all"),
    onSuccess: () => {
      qc.clear();
      void navigate("/login", { replace: true });
    },
  });
  return (
    <>
      <PageHeader
        title="Account & security"
        description="Your sign-in details and the devices signed in to your account."
      />
      <div className="flex flex-col gap-6">
        <Section title="Profile">
          <DescriptionList
            items={[
              { term: "Name", detail: me.full_name },
              {
                term: me.kind === "student" ? "Enrollment number" : "Email",
                detail: me.kind === "student" ? me.login_id : (me.email ?? me.login_id),
              },
              { term: "Institution", detail: me.tenant.name },
              {
                term: "Role",
                detail: me.roles.map((r) => r.replace("institution_", "").replace("_", " ")).join(", "),
              },
            ]}
          />
        </Section>
        <Section title="Password" description="Use a long passphrase you don't use anywhere else.">
          <ChangePassword staff={me.kind === "staff"} />
        </Section>
        <Section
          title="Where you're signed in"
          actions={
            <Button
              variant="danger-outline"
              size="sm"
              leadingIcon={<LogOut />}
              onClick={() => setConfirmAll(true)}
            >
              Sign out everywhere
            </Button>
          }
        >
          {sessions.isPending ? (
            <SkeletonText lines={3} />
          ) : (
            <ul className="divide-y divide-border">
              {sessions.data?.map((s, i) => {
                const d = deviceLabel(s.user_agent);
                return (
                  <li key={i} className="flex items-center gap-3 py-3 first:pt-0 last:pb-0">
                    <span className="flex size-9 items-center justify-center rounded-lg bg-surface-2 text-fg-subtle">
                      {d.mobile ? <Smartphone className="size-4" /> : <Laptop className="size-4" />}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center gap-2 text-sm font-medium">
                        {d.label}
                        {s.current && <Badge tone="success">This device</Badge>}
                      </span>
                      <span className="block text-[13px] text-fg-subtle">
                        {s.ip ?? "Unknown IP"} · active {formatRelative(s.last_seen_at)}
                      </span>
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </Section>
      </div>
      <ConfirmDialog
        open={confirmAll}
        onOpenChange={setConfirmAll}
        title="Sign out of every device?"
        description="Including this one. You'll need your password to sign in again."
        confirmLabel="Sign out everywhere"
        variant="danger"
        loading={logoutAll.isPending}
        onConfirm={() => logoutAll.mutate()}
      />
    </>
  );
}
