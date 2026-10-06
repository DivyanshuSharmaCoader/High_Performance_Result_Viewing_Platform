import { api, type TenantList } from "@scorecode/api-client";
import {
  Badge,
  EmptyState,
  OffsetPagination,
  PageHeader,
  SearchInput,
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
  formatDate,
  formatNumber,
} from "@scorecode/ui";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Building2 } from "lucide-react";
import { useDeferredValue } from "react";
import { useNavigate, useSearchParams } from "react-router";

export const STATUS_TONE: Record<string, "success" | "warning" | "danger" | "neutral"> = {
  active: "success",
  suspended: "danger",
  closing: "warning",
  closed: "neutral",
};

const LIMIT = 25;

export default function TenantsPage() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const q = params.get("q") ?? "";
  const status = params.get("status") ?? "";
  const plan = params.get("plan") ?? "";
  const offset = Number(params.get("offset") ?? 0);
  const deferredQ = useDeferredValue(q);
  const update = (patch: Record<string, string>) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(patch)) {
      if (v) next.set(k, v);
      else next.delete(k);
    }
    if (!("offset" in patch)) next.delete("offset");
    setParams(next, { replace: true });
  };
  const list = useQuery({
    queryKey: ["tenants", deferredQ, status, plan, offset],
    queryFn: () =>
      api.get<TenantList>("/api/v1/platform/tenants", {
        query: { q: deferredQ, status, plan, offset, limit: LIMIT },
      }),
    placeholderData: keepPreviousData,
  });
  return (
    <>
      <PageHeader
        title="Institutions"
        description="Every tenant on the platform. Open one to change its plan, adjust limits or suspend it."
      />
      <Toolbar>
        <SearchInput
          value={q}
          onValueChange={(v) => update({ q: v })}
          placeholder="Search name or address"
          className="w-full sm:w-72"
          aria-label="Search institutions"
        />
        <Select
          value={status}
          onChange={(e) => update({ status: e.target.value })}
          className="w-40"
          aria-label="Status"
        >
          <option value="">All statuses</option>
          <option value="active">Active</option>
          <option value="suspended">Suspended</option>
          <option value="closing">Closing</option>
        </Select>
        <Select
          value={plan}
          onChange={(e) => update({ plan: e.target.value })}
          className="w-40"
          aria-label="Plan"
        >
          <option value="">All plans</option>
          {["free", "starter", "growth", "pro", "enterprise"].map((p) => (
            <option key={p} value={p}>
              {p[0]!.toUpperCase() + p.slice(1)}
            </option>
          ))}
        </Select>
      </Toolbar>
      <TableContainer>
        <Table>
          <THead>
            <tr>
              <Th>Institution</Th>
              <Th>Plan</Th>
              <Th>Status</Th>
              <Th className="text-right">Students</Th>
              <Th className="hidden text-right lg:table-cell">Staff</Th>
              <Th className="hidden lg:table-cell">Created</Th>
            </tr>
          </THead>
          <TBody>
            {list.isPending ? (
              <TableSkeletonRows cols={6} />
            ) : list.data?.items.length === 0 ? (
              <tr>
                <td colSpan={6}>
                  <EmptyState
                    icon={<Building2 />}
                    title="No institutions match"
                    description="Try clearing the filters."
                  />
                </td>
              </tr>
            ) : (
              list.data?.items.map((t) => (
                <Tr key={t.id} interactive onClick={() => void navigate(`/tenants/${t.id}`)}>
                  <Td className="w-full max-w-0">
                    <a
                      href={`/tenants/${t.id}`}
                      onClick={(e) => e.preventDefault()}
                      className="block truncate font-medium text-fg hover:underline"
                    >
                      {t.name}
                    </a>
                    <span className="block truncate font-mono text-xs text-fg-subtle">{t.host}</span>
                  </Td>
                  <Td>{t.plan_name}</Td>
                  <Td>
                    <Badge tone={STATUS_TONE[t.status] ?? "neutral"} dot>
                      {t.status}
                    </Badge>
                  </Td>
                  <Td className="tabular text-right">{formatNumber(t.active_students)}</Td>
                  <Td className="tabular hidden text-right lg:table-cell">{formatNumber(t.staff_users)}</Td>
                  <Td className="hidden whitespace-nowrap text-fg-subtle lg:table-cell">
                    {formatDate(t.created_at)}
                  </Td>
                </Tr>
              ))
            )}
          </TBody>
        </Table>
      </TableContainer>
      {list.data && (
        <OffsetPagination
          offset={offset}
          limit={LIMIT}
          total={list.data.total}
          onChange={(o) => update({ offset: String(o) })}
        />
      )}
    </>
  );
}
