import { api, type Page, type PlatformAuditEntry } from "@scorecode/api-client";
import {
  EmptyState,
  LoadMore,
  PageHeader,
  TBody,
  THead,
  Table,
  TableContainer,
  TableSkeletonRows,
  Td,
  Th,
  formatDateTime,
} from "@scorecode/ui";
import { useInfiniteQuery } from "@tanstack/react-query";
import { ScrollText } from "lucide-react";
import { Link } from "react-router";

export default function PlatformAuditPage() {
  const q = useInfiniteQuery({
    queryKey: ["platform-audit"],
    queryFn: ({ pageParam }) =>
      api.get<Page<PlatformAuditEntry>>("/api/v1/platform/audit-logs", {
        query: { cursor: pageParam, limit: 50 },
      }),
    initialPageParam: "" as string,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
  const rows = q.data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <>
      <PageHeader
        title="Platform audit log"
        description="Every action by ScoreCode staff. Actions affecting an institution also appear in its own audit log."
      />
      <TableContainer>
        <Table>
          <THead>
            <tr>
              <Th>When</Th>
              <Th>Who</Th>
              <Th>Action</Th>
              <Th>Institution</Th>
              <Th>Reason</Th>
            </tr>
          </THead>
          <TBody>
            {q.isPending ? (
              <TableSkeletonRows cols={5} />
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={5}>
                  <EmptyState icon={<ScrollText />} title="No staff actions yet" />
                </td>
              </tr>
            ) : (
              rows.map((r) => (
                <tr key={r.id}>
                  <Td className="whitespace-nowrap text-fg-subtle">{formatDateTime(r.occurred_at)}</Td>
                  <Td>{r.actor_label ?? "System"}</Td>
                  <Td className="font-mono text-[13px]">{r.action}</Td>
                  <Td>
                    {r.target_tenant_id ? (
                      <Link to={`/tenants/${r.target_tenant_id}`} className="text-brand-ink hover:underline">
                        Open
                      </Link>
                    ) : (
                      "—"
                    )}
                  </Td>
                  <Td className="max-w-xs truncate text-fg-subtle">{r.reason ?? "—"}</Td>
                </tr>
              ))
            )}
          </TBody>
        </Table>
      </TableContainer>
      <LoadMore
        hasMore={Boolean(q.hasNextPage)}
        loading={q.isFetchingNextPage}
        onLoadMore={() => void q.fetchNextPage()}
      />
    </>
  );
}
