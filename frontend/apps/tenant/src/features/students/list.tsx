import type { AccountState, Student, StudentStatus } from "@scorecode/api-client";
import {
  Avatar,
  Badge,
  Button,
  EmptyState,
  LoadMore,
  PageHeader,
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
  formatNumber,
} from "@scorecode/ui";
import { FileSpreadsheet, GraduationCap, KeyRound, UserPlus } from "lucide-react";
import { useDeferredValue, useState } from "react";
import { Link, useNavigate } from "react-router";

import { useCan } from "../../lib/session";
import {
  ACCOUNT_LABEL,
  STATUS_LABEL,
  useCurrentCohorts,
  useStudentCounts,
  useStudentList,
  type StudentFilters,
} from "./api";
import { StudentDialog } from "./form";

export function AccountBadge({ account }: { account: AccountState }) {
  const tone = { none: "neutral", pending: "warning", active: "success", disabled: "neutral" } as const;
  return (
    <Badge tone={tone[account]} dot>
      {ACCOUNT_LABEL[account]}
    </Badge>
  );
}

export function StatusBadge({ status }: { status: StudentStatus }) {
  if (status === "active") return null;
  const tone = { graduated: "info", withdrawn: "warning", archived: "neutral" } as const;
  return <Badge tone={tone[status]}>{STATUS_LABEL[status]}</Badge>;
}

export function currentCohort(s: Student): string | null {
  return s.memberships.find((m) => m.session_is_current)?.cohort_code ?? null;
}

export default function StudentsPage() {
  const canManage = useCan("students.manage");
  const canImport = useCan("imports.manage");
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<StudentStatus>("active");
  const [cohortId, setCohortId] = useState("");
  const [account, setAccount] = useState<AccountState | "">("");
  const [adding, setAdding] = useState(false);
  const filters: StudentFilters = { q: useDeferredValue(q.trim()), status, cohortId, account };
  const list = useStudentList(filters);
  const counts = useStudentCounts();
  const { cohorts } = useCurrentCohorts();
  const rows = list.data?.pages.flatMap((p) => p.items) ?? [];
  const total = list.data?.pages[0]?.total ?? 0;
  const anyStudents = (counts.data && Object.values(counts.data).some((n) => n > 0)) ?? true;
  const filtered = Boolean(filters.q || cohortId || account);

  const open = (s: Student) => void navigate(`/admin/students/${s.id}`);

  return (
    <>
      <PageHeader
        title="Students"
        description="Everyone enrolled at your institution. A student's enrollment number is their login."
        actions={
          <>
            {canManage && (
              <Button variant="secondary" asChild>
                <Link to="/admin/students/activation">
                  <KeyRound aria-hidden />
                  Activation codes
                </Link>
              </Button>
            )}
            {canImport && (
              <Button variant="secondary" asChild>
                <Link to="/admin/imports">
                  <FileSpreadsheet aria-hidden />
                  Import
                </Link>
              </Button>
            )}
            {canManage && (
              <Button leadingIcon={<UserPlus />} onClick={() => setAdding(true)}>
                Add student
              </Button>
            )}
          </>
        }
      />
      <Toolbar>
        <SearchInput
          value={q}
          onValueChange={setQ}
          placeholder="Search name, enrollment no. or email"
          className="w-full sm:w-80"
          aria-label="Search students"
        />
        <Select
          value={cohortId}
          onChange={(e) => setCohortId(e.target.value)}
          className="w-full sm:w-52"
          aria-label="Filter by cohort"
        >
          <option value="">All cohorts</option>
          {cohorts.map((c) => (
            <option key={c.id} value={c.id}>
              {c.code} — {c.name}
            </option>
          ))}
        </Select>
        <Select
          value={account}
          onChange={(e) => setAccount(e.target.value as AccountState | "")}
          className="w-full sm:w-48"
          aria-label="Filter by account"
        >
          <option value="">Any account state</option>
          {(Object.keys(ACCOUNT_LABEL) as AccountState[]).map((a) => (
            <option key={a} value={a}>
              {ACCOUNT_LABEL[a]}
            </option>
          ))}
        </Select>
      </Toolbar>
      <div className="mb-3 overflow-x-auto">
        <Segmented
          label="Filter by status"
          value={status}
          onChange={setStatus}
          options={(Object.keys(STATUS_LABEL) as StudentStatus[]).map((s) => ({
            value: s,
            label: STATUS_LABEL[s],
            count: counts.data?.[s],
          }))}
        />
      </div>

      {!list.isPending && rows.length === 0 ? (
        <div className="rounded-xl border border-border bg-surface">
          {filtered || status !== "active" || anyStudents ? (
            <EmptyState
              compact
              title="No students match"
              description={
                filtered
                  ? "Try a different search or filter."
                  : `No ${STATUS_LABEL[status].toLowerCase()} students.`
              }
            />
          ) : (
            <EmptyState
              icon={<GraduationCap />}
              title="Add your students"
              description="Import a spreadsheet of your students — any layout works, you'll map the columns — or add them one by one."
              action={
                <div className="flex flex-wrap justify-center gap-2">
                  {canImport && (
                    <Button asChild>
                      <Link to="/admin/imports">
                        <FileSpreadsheet aria-hidden />
                        Import a spreadsheet
                      </Link>
                    </Button>
                  )}
                  {canManage && (
                    <Button variant="secondary" leadingIcon={<UserPlus />} onClick={() => setAdding(true)}>
                      Add one student
                    </Button>
                  )}
                </div>
              }
            />
          )}
        </div>
      ) : (
        <>
          <ul className="flex flex-col gap-2 md:hidden" aria-label="Students">
            {list.isPending
              ? Array.from({ length: 4 }, (_, i) => (
                  <li key={i} className="h-16 animate-pulse rounded-lg bg-surface-2" />
                ))
              : rows.map((s) => (
                  <li key={s.id}>
                    <Link
                      to={`/admin/students/${s.id}`}
                      className="flex items-center gap-3 rounded-lg border border-border bg-surface p-3 shadow-xs hover:bg-surface-2/50"
                    >
                      <Avatar name={s.full_name} />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium">{s.full_name}</p>
                        <p className="truncate font-mono text-xs text-fg-subtle">
                          {s.enrollment_no}
                          {currentCohort(s) && <span className="font-sans"> · {currentCohort(s)}</span>}
                        </p>
                      </div>
                      <AccountBadge account={s.account} />
                    </Link>
                  </li>
                ))}
          </ul>
          <TableContainer className="hidden md:block">
            <Table>
              <THead>
                <tr>
                  <Th>Student</Th>
                  <Th>Enrollment no.</Th>
                  <Th>Cohort</Th>
                  <Th>Account</Th>
                </tr>
              </THead>
              <TBody>
                {list.isPending ? (
                  <TableSkeletonRows cols={4} rows={8} />
                ) : (
                  rows.map((s) => (
                    <tr key={s.id} className="cursor-pointer hover:bg-surface-2/60" onClick={() => open(s)}>
                      <Td className="w-full max-w-0">
                        <div className="flex min-w-0 items-center gap-3">
                          <Avatar name={s.full_name} size="sm" />
                          <Link
                            to={`/admin/students/${s.id}`}
                            className="truncate font-medium text-fg hover:underline"
                            onClick={(e) => e.stopPropagation()}
                          >
                            {s.full_name}
                          </Link>
                          <StatusBadge status={s.status} />
                        </div>
                      </Td>
                      <Td className="whitespace-nowrap font-mono text-[13px] text-fg-muted">
                        {s.enrollment_no}
                      </Td>
                      <Td className="whitespace-nowrap text-fg-muted">{currentCohort(s) ?? "—"}</Td>
                      <Td className="whitespace-nowrap">
                        <AccountBadge account={s.account} />
                      </Td>
                    </tr>
                  ))
                )}
              </TBody>
            </Table>
          </TableContainer>
          {!list.isPending && (
            <p className="px-1 pt-3 text-[13px] text-fg-subtle tabular">
              Showing {formatNumber(rows.length)} of {formatNumber(total)}
            </p>
          )}
          <LoadMore
            hasMore={Boolean(list.hasNextPage)}
            loading={list.isFetchingNextPage}
            onLoadMore={() => void list.fetchNextPage()}
          />
        </>
      )}
      {adding && <StudentDialog onClose={() => setAdding(false)} onSaved={open} />}
    </>
  );
}
