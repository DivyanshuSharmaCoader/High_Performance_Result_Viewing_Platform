import { api, type ActivationCodes, type Student, type StudentStatus } from "@scorecode/api-client";
import {
  Avatar,
  Button,
  Callout,
  ConfirmDialog,
  DescriptionList,
  Menu,
  MenuContent,
  MenuItem,
  MenuSeparator,
  MenuTrigger,
  PageHeader,
  Section,
  Select,
  Skeleton,
  formatDate,
  toast,
} from "@scorecode/ui";
import { useMutation } from "@tanstack/react-query";
import {
  Archive,
  ArchiveRestore,
  ChevronDown,
  GraduationCap,
  KeyRound,
  LogOut,
  Pencil,
  Trash2,
  UserCheck,
} from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router";

import { toastError } from "../../lib/forms";
import { useCan } from "../../lib/session";
import { S, STATUS_LABEL, useCurrentCohorts, useInvalidateStudents, useStudent } from "./api";
import { StudentDialog } from "./form";
import { AccountBadge, StatusBadge } from "./list";
import { SlipsDialog } from "./slips";

const STATUS_ACTIONS: { to: StudentStatus; label: string; icon: typeof GraduationCap; hint: string }[] = [
  {
    to: "graduated",
    label: "Mark as graduated",
    icon: GraduationCap,
    hint: "Graduates keep access to their published results. They stop counting towards your student limit.",
  },
  {
    to: "withdrawn",
    label: "Mark as withdrawn",
    icon: LogOut,
    hint: "Withdrawn students can't sign in. Their records are kept, and they stop counting towards your limit.",
  },
  {
    to: "archived",
    label: "Archive",
    icon: Archive,
    hint: "Archived students are hidden from lists and can't sign in. Nothing is deleted; you can restore them.",
  },
];

function CohortPlacement({ student, canManage }: { student: Student; canManage: boolean }) {
  const { cohorts, session } = useCurrentCohorts();
  const invalidate = useInvalidateStudents();
  const [choice, setChoice] = useState("");
  const assign = useMutation({
    mutationFn: (cohortId: string) =>
      api.post<Student>(`${S}/${student.id}/cohorts`, { cohort_id: cohortId }),
    onSuccess: () => {
      invalidate();
      setChoice("");
      toast.success("Cohort updated");
    },
    onError: (e) => toastError(e),
  });
  const remove = useMutation({
    mutationFn: (cohortId: string) => api.delete<Student>(`${S}/${student.id}/cohorts/${cohortId}`),
    onSuccess: () => {
      invalidate();
      toast.success("Removed from cohort");
    },
    onError: (e) => toastError(e),
  });
  const available = cohorts.filter((c) => !student.memberships.some((m) => m.cohort_id === c.id));
  return (
    <Section
      title="Cohorts"
      description="A student is in at most one cohort of a program per session. Choosing a sibling cohort moves them."
    >
      {student.memberships.length === 0 ? (
        <p className="text-sm text-fg-subtle">Not in any cohort yet.</p>
      ) : (
        <ul className="divide-y divide-border">
          {student.memberships.map((m) => (
            <li key={m.cohort_id} className="flex items-center justify-between gap-3 py-2.5 first:pt-0">
              <div className="min-w-0">
                <p className="text-sm font-medium text-fg">
                  {m.cohort_code} <span className="font-normal text-fg-subtle">· {m.cohort_name}</span>
                </p>
                <p className="text-[13px] text-fg-subtle">
                  {m.program_code} · {m.session_code}
                  {m.session_is_current && " (current session)"}
                </p>
              </div>
              {canManage && (
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label={`Remove from ${m.cohort_code}`}
                  loading={remove.isPending && remove.variables === m.cohort_id}
                  onClick={() => remove.mutate(m.cohort_id)}
                >
                  <Trash2 />
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
      {canManage && session && available.length > 0 && (
        <form
          className="mt-4 flex flex-wrap items-center gap-2 border-t border-border pt-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (choice) assign.mutate(choice);
          }}
        >
          <Select
            value={choice}
            onChange={(e) => setChoice(e.target.value)}
            className="w-full sm:w-72"
            aria-label={`Add to a cohort in ${session.name}`}
          >
            <option value="">Add to a cohort in {session.code}…</option>
            {available.map((c) => (
              <option key={c.id} value={c.id}>
                {c.code} — {c.name}
              </option>
            ))}
          </Select>
          <Button type="submit" variant="secondary" disabled={!choice} loading={assign.isPending}>
            Add
          </Button>
        </form>
      )}
    </Section>
  );
}

export default function StudentDetailPage() {
  const { studentId = "" } = useParams();
  const canManage = useCan("students.manage");
  const q = useStudent(studentId);
  const invalidate = useInvalidateStudents();
  const [editing, setEditing] = useState(false);
  const [statusTo, setStatusTo] = useState<StudentStatus | null>(null);
  const [slips, setSlips] = useState<ActivationCodes | null>(null);
  const setStatus = useMutation({
    mutationFn: ({ to, reason }: { to: StudentStatus; reason?: string }) =>
      api.put<Student>(`${S}/${studentId}/status`, { status: to, reason: reason || null }),
    onSuccess: (s) => {
      invalidate();
      setStatusTo(null);
      toast.success(
        s.status === "active" ? "Student restored" : `Marked as ${STATUS_LABEL[s.status].toLowerCase()}`,
      );
    },
    onError: (e) => {
      setStatusTo(null);
      toastError(e);
    },
  });
  const issue = useMutation({
    mutationFn: (replace: boolean) =>
      api.post<ActivationCodes>("/api/v1/admin/activation-codes", {
        student_ids: [studentId],
        replace_existing: replace,
      }),
    onSuccess: (r) => {
      invalidate();
      if (r.issued.length) setSlips(r);
      else toast.info("No code issued", { description: "This student already has an account." });
    },
    onError: (e) => toastError(e),
  });

  if (q.isPending) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-10 w-72" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }
  if (q.error) {
    return <Callout tone="danger">This student couldn't be loaded. They may have been removed.</Callout>;
  }
  const s = q.data;
  const pendingAction = STATUS_ACTIONS.find((a) => a.to === statusTo);
  const canActivate = canManage && (s.status === "active" || s.status === "graduated");
  return (
    <>
      <PageHeader
        breadcrumb={
          <Link to="/admin/students" className="hover:text-fg">
            Students
          </Link>
        }
        title={
          <span className="flex items-center gap-3">
            <Avatar name={s.full_name} size="lg" />
            <span className="min-w-0">
              <span className="block truncate">{s.full_name}</span>
              <span className="block font-mono text-sm font-normal text-fg-subtle">{s.enrollment_no}</span>
            </span>
          </span>
        }
        meta={
          <>
            <StatusBadge status={s.status} />
            <AccountBadge account={s.account} />
          </>
        }
        actions={
          canManage && (
            <>
              <Button variant="secondary" leadingIcon={<Pencil />} onClick={() => setEditing(true)}>
                Edit
              </Button>
              <Menu>
                <MenuTrigger asChild>
                  <Button variant="secondary">
                    More <ChevronDown aria-hidden />
                  </Button>
                </MenuTrigger>
                <MenuContent align="end">
                  {canActivate && s.account !== "active" && (
                    <MenuItem icon={<KeyRound />} onSelect={() => issue.mutate(s.account === "pending")}>
                      {s.account === "pending" ? "Replace activation code" : "Issue activation code"}
                    </MenuItem>
                  )}
                  {s.status !== "active" ? (
                    <MenuItem
                      icon={s.status === "archived" ? <ArchiveRestore /> : <UserCheck />}
                      onSelect={() => setStatus.mutate({ to: "active" })}
                    >
                      {s.status === "archived" ? "Restore" : "Mark as active"}
                    </MenuItem>
                  ) : null}
                  <MenuSeparator />
                  {STATUS_ACTIONS.filter((a) => a.to !== s.status).map((a) => (
                    <MenuItem
                      key={a.to}
                      icon={<a.icon />}
                      destructive={a.to === "archived"}
                      onSelect={() => setStatusTo(a.to)}
                    >
                      {a.label}
                    </MenuItem>
                  ))}
                </MenuContent>
              </Menu>
            </>
          )
        }
      />
      <div className="grid gap-5 lg:grid-cols-[1fr_380px]">
        <div className="flex flex-col gap-5">
          <Section title="Details">
            <DescriptionList
              items={[
                { term: "Email", detail: s.email ?? "—" },
                { term: "Phone", detail: s.phone ?? "—" },
                { term: "Date of birth", detail: s.date_of_birth ? formatDate(s.date_of_birth) : "—" },
                { term: "Admission year", detail: s.admission_year ?? "—" },
                { term: "Parent or guardian", detail: s.guardian_name ?? "—" },
                { term: "Added", detail: formatDate(s.created_at) },
              ]}
            />
          </Section>
          <CohortPlacement student={s} canManage={canManage} />
        </div>
        <Section title="Portal account">
          <div className="flex flex-col gap-3 text-sm">
            <AccountBadge account={s.account} />
            <p className="text-fg-muted">
              {s.account === "none" &&
                "This student hasn't been given an activation code yet. Issue one to let them set a password and see their results."}
              {s.account === "pending" &&
                "An activation code has been issued but not used yet. If the slip was lost, replace the code — the old one stops working."}
              {s.account === "active" &&
                `Signs in with enrollment no. ${s.enrollment_no} and their own password.`}
              {s.account === "disabled" &&
                "Sign-in is disabled because the student is withdrawn or archived."}
            </p>
            {canActivate && s.account !== "active" && s.account !== "disabled" && (
              <Button
                variant="secondary"
                leadingIcon={<KeyRound />}
                loading={issue.isPending}
                onClick={() => issue.mutate(s.account === "pending")}
                className="self-start"
              >
                {s.account === "pending" ? "Replace code" : "Issue activation code"}
              </Button>
            )}
          </div>
        </Section>
      </div>

      {editing && <StudentDialog student={s} onClose={() => setEditing(false)} />}
      {pendingAction && (
        <ConfirmDialog
          open
          onOpenChange={(o) => !o && setStatusTo(null)}
          title={`${pendingAction.label} — ${s.full_name}?`}
          description={pendingAction.hint}
          confirmLabel={pendingAction.label}
          variant={pendingAction.to === "archived" ? "danger" : "primary"}
          requireReason={pendingAction.to !== "graduated"}
          loading={setStatus.isPending}
          onConfirm={(reason) => setStatus.mutate({ to: pendingAction.to, reason })}
        />
      )}
      {slips && <SlipsDialog codes={slips} onClose={() => setSlips(null)} />}
    </>
  );
}
