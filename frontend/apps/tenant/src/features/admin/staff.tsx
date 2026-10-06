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
  RotateCw,
  ShieldCheck,
  UserCheck,
  UserPlus,
  UserX,
  Users,
} from "lucide-react";
import { useDeferredValue, useMemo, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { PlanLimitCallout } from "../../components/limit-callout";
import { useReauth } from "../../components/reauth";
import { applyServerError, toastError } from "../../lib/forms";
import { useCan, useSession } from "../../lib/session";

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

type PendingAction =
  | { kind: "disable"; member: Staff }
  | { kind: "enable"; member: Staff }
  | { kind: "role"; member: Staff; role: "faculty" | "institution_admin" }
  | { kind: "owner"; member: Staff }
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
    if (!canManage || isMe || m.role === "institution_owner") return null;
    return (
      <Menu>
        <MenuTrigger asChild>
          <Button variant="ghost" size="icon-sm" aria-label={`Actions for ${m.full_name}`}>
            <MoreHorizontal />
          </Button>
        </MenuTrigger>
        <MenuContent>
          {m.status === "invited" && (
            <MenuItem icon={<RotateCw />} onSelect={() => resend.mutate(m)}>
              Resend invitation
            </MenuItem>
          )}
          {m.role === "faculty" ? (
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
          {isOwner && m.role === "institution_admin" && m.status === "active" && (
            <MenuItem icon={<Crown />} onSelect={() => setPending({ kind: "owner", member: m })}>
              Transfer ownership
            </MenuItem>
          )}
          <MenuSeparator />
          {m.status === "disabled" ? (
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
                          <p className="truncate text-[13px] text-fg-subtle">{m.email}</p>
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

      {pending && (
        <ConfirmDialog
          open
          onOpenChange={(o) => !o && setPending(null)}
          loading={act.isPending}
          onConfirm={() => act.mutate(pending)}
          variant={pending.kind === "disable" ? "danger" : "primary"}
          confirmText={pending.kind === "owner" ? "TRANSFER" : undefined}
          title={
            pending.kind === "disable"
              ? `Disable ${pending.member.full_name}?`
              : pending.kind === "enable"
                ? `Re-enable ${pending.member.full_name}?`
                : pending.kind === "role"
                  ? `Change ${pending.member.full_name}'s role?`
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
                  : "The owner controls billing and can transfer ownership. You'll become an administrator. This can only be undone by the new owner."
          }
          confirmLabel={
            pending.kind === "disable"
              ? "Disable account"
              : pending.kind === "enable"
                ? "Re-enable"
                : pending.kind === "role"
                  ? "Change role"
                  : "Transfer ownership"
          }
        />
      )}
    </>
  );
}
