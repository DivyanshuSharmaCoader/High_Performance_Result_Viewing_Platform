import { zodResolver } from "@hookform/resolvers/zod";
import { api, ApiError, type Staff } from "@scorecode/api-client";
import {
  Avatar,
  Badge,
  Button,
  Callout,
  ConfirmDialog,
  Dialog,
  DialogContent,
  EmptyState,
  Field,
  Input,
  Menu,
  MenuContent,
  MenuItem,
  MenuSeparator,
  MenuTrigger,
  PageHeader,
  RadioCards,
  SearchInput,
  Segmented,
  Select,
  TBody,
  THead,
  Table,
  TableContainer,
  TableSkeletonRows,
  Td,
  Th,
  Toolbar,
  Tr,
  formatRelative,
  toast,
} from "@scorecode/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Crown,
  MailPlus,
  MoreHorizontal,
  Pencil,
  RotateCw,
  ShieldCheck,
  UserCheck,
  UserPlus,
  UserX,
  Users,
  KeyRound,
} from "lucide-react";
import { useDeferredValue, useMemo, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { FormDialog } from "../../components/form-dialog";
import { PlanLimitCallout } from "../../components/limit-callout";
import { useReauth } from "../../components/reauth";
import { applyServerError, toastError } from "../../lib/forms";
import { useCan, useSession } from "../../lib/session";
import { useDepartments } from "../academics/api";

const ROLE: Record<string, { label: string; tone: "brand" | "info" | "neutral" }> = {
  institution_owner: { label: "Owner", tone: "brand" },
  institution_admin: { label: "Administrator", tone: "info" },
  faculty: { label: "Faculty", tone: "neutral" },
};

function StatusBadge({ status }: { status: string }) {
  if (status === "active")
    return (
      <Badge tone="success" dot>
        Active
      </Badge>
    );
  if (status === "invited")
    return (
      <Badge tone="warning" dot>
        Invitation sent
      </Badge>
    );
  return <Badge dot>Disabled</Badge>;
}

const inviteSchema = z.object({
  full_name: z.string().trim().min(2, "Enter their full name"),
  email: z.email("Enter a valid email address"),
  role: z.enum(["faculty", "institution_admin"]),
});
type InviteValues = z.infer<typeof inviteSchema>;

function InviteDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const qc = useQueryClient();
  const [error, setError] = useState<unknown>(null);
  const form = useForm<InviteValues>({
    resolver: zodResolver(inviteSchema),
    defaultValues: { full_name: "", email: "", role: "faculty" },
  });
  const role = useWatch({ control: form.control, name: "role" });
  const invite = useMutation({
    mutationFn: (v: InviteValues) => api.post<Staff>("/api/v1/admin/staff", v),
    onSuccess: (staff) => {
      void qc.invalidateQueries({ queryKey: ["staff"] });
      void qc.invalidateQueries({ queryKey: ["subscription"] });
      void qc.invalidateQueries({ queryKey: ["onboarding"] });
      toast.success("Invitation sent", {
        description: `${staff.full_name} will get an email to set their password.`,
      });
      form.reset();
      onOpenChange(false);
    },
    onError: (e) => {
      const msg = applyServerError(e, form.setError, ["email", "full_name", "role"]);
      setError(msg ? e : null);
    },
  });
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) {
          form.reset();
          setError(null);
        }
        onOpenChange(next);
      }}
    >
      <DialogContent
        title="Invite a staff member"
        description="They'll receive an email with a link to set their password. Invitations expire after 7 days."
        dismissible={!invite.isPending}
        footer={
          <>
            <Button variant="secondary" onClick={() => onOpenChange(false)} disabled={invite.isPending}>
              Cancel
            </Button>
            <Button type="submit" form="invite-form" loading={invite.isPending} leadingIcon={<MailPlus />}>
              Send invitation
            </Button>
          </>
        }
      >
        <form
          id="invite-form"
          noValidate
          className="flex flex-col gap-5"
          onSubmit={form.handleSubmit((v) => {
            setError(null);
            invite.mutate(v);
          })}
        >
          {error instanceof ApiError && error.status === 402 ? (
            <PlanLimitCallout error={error} />
          ) : error instanceof ApiError ? (
            <Callout tone="danger">{error.detail}</Callout>
          ) : null}
          <div className="grid gap-5 sm:grid-cols-2">
            <Field label="Full name" error={form.formState.errors.full_name?.message} required>
              <Input autoFocus autoComplete="off" {...form.register("full_name")} />
            </Field>
            <Field label="Work email" error={form.formState.errors.email?.message} required>
              <Input type="email" autoComplete="off" {...form.register("email")} />
            </Field>
          </div>
          <Field label="Role" error={form.formState.errors.role?.message}>
            <RadioCards
              name="role"
              value={role}
              onChange={(v) => form.setValue("role", v)}
              options={[
                {
                  value: "faculty",
                  label: "Faculty",
                  icon: <Users />,
                  description: "Enters and submits marks for the papers they're assigned.",
                },
                {
                  value: "institution_admin",
                  label: "Administrator",
                  icon: <ShieldCheck />,
                  description: "Manages students, exams, results and settings.",
                },
              ]}
            />
          </Field>
        </form>
      </DialogContent>
    </Dialog>
  );
}

const profileSchema = z.object({
  full_name: z.string().trim().min(2, "Enter their full name").max(200),
  employee_code: z.string().trim().max(40),
  designation: z.string().trim().max(100),
  department_id: z.string(),
  phone: z.string().trim().max(32),
});
type ProfileValues = z.infer<typeof profileSchema>;

function ProfileDialog({ member, onClose }: { member: Staff; onClose: () => void }) {
  const qc = useQueryClient();
  const departments = useDepartments();
  const [error, setError] = useState<unknown>(null);
  const form = useForm<ProfileValues>({
    resolver: zodResolver(profileSchema),
    defaultValues: {
      full_name: member.full_name,
      employee_code: member.employee_code ?? "",
      designation: member.designation ?? "",
      department_id: member.department_id ?? "",
      phone: member.phone ?? "",
    },
  });
  const save = useMutation({
    mutationFn: (v: ProfileValues) =>
      api.put<Staff>(`/api/v1/admin/staff/${member.id}/profile`, {
        full_name: v.full_name,
        employee_code: v.employee_code || null,
        designation: v.designation || null,
        department_id: v.department_id || null,
        phone: v.phone || null,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["staff"] });
      toast.success("Profile updated");
      onClose();
    },
    onError: (e) =>
      setError(
        applyServerError(e, form.setError, [
          "full_name",
          "employee_code",
          "designation",
          "department_id",
          "phone",
        ])
          ? e
          : null,
      ),
  });
  const errors = form.formState.errors;
  return (
    <FormDialog
      open
      onOpenChange={(o) => !o && onClose()}
      title={`Edit ${member.full_name}`}
      submitLabel="Save profile"
      submitting={save.isPending}
      error={error}
      formId="profile-form"
    >
      <form
        id="profile-form"
        noValidate
        className="flex flex-col gap-5"
        onSubmit={form.handleSubmit((v) => {
          setError(null);
          save.mutate(v);
        })}
      >
        <Field label="Full name" error={errors.full_name?.message}>
          <Input autoFocus {...form.register("full_name")} />
        </Field>
        <div className="grid gap-5 sm:grid-cols-2">
          <Field label="Designation" optional error={errors.designation?.message}>
            <Input placeholder="Assistant Professor" {...form.register("designation")} />
          </Field>
          <Field label="Employee code" optional error={errors.employee_code?.message}>
            <Input {...form.register("employee_code")} />
          </Field>
          <Field label="Department" optional error={errors.department_id?.message}>
            <Select {...form.register("department_id")}>
              <option value="">No department</option>
              {(departments.data ?? []).map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name} ({d.code})
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Phone" optional error={errors.phone?.message}>
            <Input type="tel" {...form.register("phone")} />
          </Field>
        </div>
      </form>
    </FormDialog>
  );
}

type PendingAction =
  | { kind: "disable"; member: Staff }
  | { kind: "enable"; member: Staff }
  | { kind: "role"; member: Staff; role: "faculty" | "institution_admin" }
  | { kind: "owner"; member: Staff }
  | { kind: "mfa"; member: Staff }
  | null;

export default function StaffPage() {
  const me = useSession();
  const canManage = useCan("staff.manage");
  const isOwner = me.roles.includes("institution_owner");
  const qc = useQueryClient();
  const withReauth = useReauth();
  const [q, setQ] = useState("");
  const [role, setRole] = useState<"all" | "institution_admin" | "faculty">("all");
  const [inviteOpen, setInviteOpen] = useState(false);
  const [pending, setPending] = useState<PendingAction>(null);
  const [editing, setEditing] = useState<Staff | null>(null);
  const departments = useDepartments();
  const deptCode = (id: string | null | undefined) => departments.data?.find((d) => d.id === id)?.code;
  const deferredQ = useDeferredValue(q);

  const staff = useQuery({
    queryKey: ["staff"],
    queryFn: () => api.get<Staff[]>("/api/v1/admin/staff"),
  });
  const rows = useMemo(() => {
    const needle = deferredQ.trim().toLowerCase();
    return (staff.data ?? []).filter(
      (s) =>
        (role === "all" ||
          s.role === role ||
          (role === "institution_admin" && s.role === "institution_owner")) &&
        (!needle ||
          s.full_name.toLowerCase().includes(needle) ||
          (s.email ?? "").toLowerCase().includes(needle)),
    );
  }, [staff.data, deferredQ, role]);

  const counts = useMemo(() => {
    const all = staff.data ?? [];
    return {
      all: all.length,
      admins: all.filter((s) => s.role !== "faculty").length,
      faculty: all.filter((s) => s.role === "faculty").length,
    };
  }, [staff.data]);

  const act = useMutation({
    mutationFn: async (action: NonNullable<PendingAction>) => {
      const id = action.member.id;
      if (action.kind === "disable" || action.kind === "enable") {
        return api.put(`/api/v1/admin/staff/${id}/status`, { disabled: action.kind === "disable" });
      }
      if (action.kind === "role") {
        return withReauth(() => api.put(`/api/v1/admin/staff/${id}/role`, { role: action.role }));
      }
      if (action.kind === "mfa") {
        return withReauth(() => api.post(`/api/v1/admin/staff/${id}/mfa/reset`));
      }
      return withReauth(() => api.post(`/api/v1/admin/staff/${id}/transfer-ownership`));
    },
    onSuccess: (_d, action) => {
      void qc.invalidateQueries({ queryKey: ["staff"] });
      void qc.invalidateQueries({ queryKey: ["subscription"] });
      const name = action.member.full_name;
      const messages = {
        disable: `${name} can no longer sign in.`,
        enable: `${name} can sign in again.`,
        role: `${name} is now ${action.kind === "role" ? ROLE[action.role]?.label.toLowerCase() : ""}.`,
        owner: `${name} is now the owner. You remain an administrator.`,
        mfa: `Two-step sign-in reset for ${name}. They sign in with their password and set it up again.`,
      };
      toast.success(messages[action.kind]);
      if (action.kind === "owner") void qc.invalidateQueries({ queryKey: ["me"] });
      setPending(null);
    },
    onError: (e) => {
      if (e instanceof ApiError && e.code === "reauth-cancelled") return;
      toastError(e);
    },
  });

  const resend = useMutation({
    mutationFn: (m: Staff) => api.post(`/api/v1/admin/staff/${m.id}/resend-invite`),
    onSuccess: (_d, m) =>
      toast.success("Invitation re-sent", { description: `A new link was emailed to ${m.email}.` }),
    onError: (e) => toastError(e),
  });

  const actionsFor = (m: Staff) => {
    const isMe = m.id === me.id;
    if (!canManage) return null;
    const limited = isMe || m.role === "institution_owner";
    return (
      <Menu>
        <MenuTrigger asChild>
          <Button variant="ghost" size="icon-sm" aria-label={`Actions for ${m.full_name}`}>
            <MoreHorizontal />
          </Button>
        </MenuTrigger>
        <MenuContent>
          <MenuItem icon={<Pencil />} onSelect={() => setEditing(m)}>
            Edit profile
          </MenuItem>
          {!limited && <MenuSeparator />}
          {!limited && m.status === "invited" && (
            <MenuItem icon={<RotateCw />} onSelect={() => resend.mutate(m)}>
              Resend invitation
            </MenuItem>
          )}
          {limited ? null : m.role === "faculty" ? (
            <MenuItem
              icon={<ShieldCheck />}
              onSelect={() => setPending({ kind: "role", member: m, role: "institution_admin" })}
            >
              Make administrator
            </MenuItem>
          ) : (
            <MenuItem
              icon={<Users />}
              onSelect={() => setPending({ kind: "role", member: m, role: "faculty" })}
            >
              Change to faculty
            </MenuItem>
          )}
          {!limited && m.mfa_enabled && (
            <MenuItem icon={<KeyRound />} onSelect={() => setPending({ kind: "mfa", member: m })}>
              Reset two-step sign-in
            </MenuItem>
          )}
          {!limited && isOwner && m.role === "institution_admin" && m.status === "active" && (
            <MenuItem icon={<Crown />} onSelect={() => setPending({ kind: "owner", member: m })}>
              Transfer ownership
            </MenuItem>
          )}
          {!limited && <MenuSeparator />}
          {limited ? null : m.status === "disabled" ? (
            <MenuItem icon={<UserCheck />} onSelect={() => setPending({ kind: "enable", member: m })}>
              Re-enable account
            </MenuItem>
          ) : (
            <MenuItem
              destructive
              icon={<UserX />}
              onSelect={() => setPending({ kind: "disable", member: m })}
            >
              Disable account
            </MenuItem>
          )}
        </MenuContent>
      </Menu>
    );
  };

  return (
    <>
      <PageHeader
        title="Staff"
        description="Administrators manage your institution; faculty enter marks for the papers they're assigned."
        actions={
          canManage && (
            <Button leadingIcon={<UserPlus />} onClick={() => setInviteOpen(true)}>
              Invite staff
            </Button>
          )
        }
      />
      <Toolbar>
        <SearchInput
          value={q}
          onValueChange={setQ}
          placeholder="Search by name or email"
          className="w-full sm:w-72"
          aria-label="Search staff"
        />
        <Segmented
          label="Filter by role"
          value={role}
          onChange={setRole}
          options={[
            { value: "all", label: "All", count: counts.all },
            { value: "institution_admin", label: "Admins", count: counts.admins },
            { value: "faculty", label: "Faculty", count: counts.faculty },
          ]}
        />
      </Toolbar>
      <ul className="flex flex-col gap-2 md:hidden" aria-label="Staff">
        {staff.isPending
          ? Array.from({ length: 3 }, (_, i) => (
              <li key={i} className="h-20 animate-pulse rounded-lg bg-surface-2" />
            ))
          : rows.map((m) => {
              const r = ROLE[m.role] ?? { label: m.role, tone: "neutral" as const };
              return (
                <li
                  key={m.id}
                  className="flex items-start gap-3 rounded-lg border border-border bg-surface p-3.5 shadow-xs"
                >
                  <Avatar name={m.full_name} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">
                      {m.full_name}
                      {m.id === me.id && <span className="ml-1 font-normal text-fg-subtle">(you)</span>}
                    </p>
                    <p className="truncate text-[13px] text-fg-subtle">{m.email}</p>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      <Badge tone={r.tone}>{r.label}</Badge>
                      <StatusBadge status={m.status} />
                    </div>
                  </div>
                  {actionsFor(m)}
                </li>
              );
            })}
      </ul>
      <TableContainer className="hidden md:block">
        <Table>
          <THead>
            <tr>
              <Th>Name</Th>
              <Th>Role</Th>
              <Th>Status</Th>
              <Th className="hidden md:table-cell">Last sign-in</Th>
              <Th className="w-12 px-2">
                <span className="sr-only">Actions</span>
              </Th>
            </tr>
          </THead>
          <TBody>
            {staff.isPending ? (
              <TableSkeletonRows cols={5} rows={5} />
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={5}>
                  {staff.data && staff.data.length > 1 ? (
                    <EmptyState
                      compact
                      title="No staff match your search"
                      description="Try a different name, email or role."
                    />
                  ) : (
                    <EmptyState
                      icon={<Users />}
                      title="Invite your team"
                      description="Add administrators to share the work, and faculty to enter marks for their papers."
                      action={
                        canManage && (
                          <Button leadingIcon={<UserPlus />} onClick={() => setInviteOpen(true)}>
                            Invite staff
                          </Button>
                        )
                      }
                    />
                  )}
                </td>
              </tr>
            ) : (
              rows.map((m) => {
                const isMe = m.id === me.id;
                const r = ROLE[m.role] ?? { label: m.role, tone: "neutral" as const };
                return (
                  <Tr key={m.id}>
                    <Td className="w-full max-w-0">
                      <div className="flex min-w-0 items-center gap-3">
                        <Avatar name={m.full_name} />
                        <div className="min-w-0">
                          <p className="truncate font-medium text-fg">
                            {m.full_name}
                            {isMe && <span className="ml-1.5 font-normal text-fg-subtle">(you)</span>}
                          </p>
                          <p className="truncate text-[13px] text-fg-subtle">
                            {[m.designation, deptCode(m.department_id), m.email].filter(Boolean).join(" · ")}
                          </p>
                        </div>
                      </div>
                    </Td>
                    <Td>
                      <Badge tone={r.tone} icon={m.role === "institution_owner" ? <Crown /> : undefined}>
                        {r.label}
                      </Badge>
                    </Td>
                    <Td>
                      <StatusBadge status={m.status} />
                    </Td>
                    <Td className="hidden text-fg-subtle md:table-cell">
                      {m.status === "invited" ? "—" : formatRelative(m.last_login_at)}
                    </Td>
                    <Td className="px-2">{actionsFor(m)}</Td>
                  </Tr>
                );
              })
            )}
          </TBody>
        </Table>
      </TableContainer>

      <InviteDialog open={inviteOpen} onOpenChange={setInviteOpen} />
      {editing && <ProfileDialog member={editing} onClose={() => setEditing(null)} />}

      {pending && (
        <ConfirmDialog
          open
          onOpenChange={(o) => !o && setPending(null)}
          loading={act.isPending}
          onConfirm={() => act.mutate(pending)}
          variant={pending.kind === "disable" || pending.kind === "mfa" ? "danger" : "primary"}
          confirmText={pending.kind === "owner" ? "TRANSFER" : undefined}
          title={
            pending.kind === "disable"
              ? `Disable ${pending.member.full_name}?`
              : pending.kind === "enable"
                ? `Re-enable ${pending.member.full_name}?`
                : pending.kind === "role"
                  ? `Change ${pending.member.full_name}'s role?`
                  : pending.kind === "mfa"
                    ? `Reset ${pending.member.full_name}'s two-step sign-in?`
                    : `Make ${pending.member.full_name} the owner?`
          }
          description={
            pending.kind === "disable"
              ? "They'll be signed out everywhere and can't sign in. Their past work and audit history are kept. This frees a staff seat."
              : pending.kind === "enable"
                ? "They'll be able to sign in again. This uses a staff seat on your plan."
                : pending.kind === "role"
                  ? pending.role === "institution_admin"
                    ? "Administrators can manage students, exams, results, staff and settings. They'll be signed out and need to sign in again."
                    : "They'll lose administrator access and keep only faculty access. They'll be signed out and need to sign in again."
                  : pending.kind === "mfa"
                    ? "Only for a lost or replaced phone. Their sign-in falls back to the password until they set two-step up again. Make sure you're really talking to them."
                    : "The owner controls billing and can transfer ownership. You'll become an administrator. This can only be undone by the new owner."
          }
          confirmLabel={
            pending.kind === "disable"
              ? "Disable account"
              : pending.kind === "enable"
                ? "Re-enable"
                : pending.kind === "role"
                  ? "Change role"
                  : pending.kind === "mfa"
                    ? "Reset two-step"
                    : "Transfer ownership"
          }
        />
      )}
    </>
  );
}
