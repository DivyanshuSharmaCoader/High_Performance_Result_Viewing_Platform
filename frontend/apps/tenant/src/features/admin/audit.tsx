import { api, type AuditEntry, type Page } from "@scorecode/api-client";
import {
  Avatar,
  Badge,
  EmptyState,
  LoadMore,
  PageHeader,
  Select,
  TBody,
  THead,
  Table,
  TableContainer,
  TableSkeletonRows,
  Td,
  Th,
  Toolbar,
  formatDateTime,
} from "@scorecode/ui";
import { useInfiniteQuery } from "@tanstack/react-query";
import { ChevronRight, ScrollText } from "lucide-react";
import { Fragment, useState } from "react";

import { ACTION_FILTERS, describeAction } from "./audit-format";

function Value({ value }: { value: unknown }) {
  if (value === null || value === undefined || value === "")
    return <span className="text-fg-disabled">empty</span>;
  if (typeof value === "boolean") return <>{value ? "Yes" : "No"}</>;
  if (typeof value === "object") return <code className="font-mono text-xs">{JSON.stringify(value)}</code>;
  return <>{String(value)}</>;
}

function Diff({ entry }: { entry: AuditEntry }) {
  const keys = Array.from(new Set([...Object.keys(entry.before ?? {}), ...Object.keys(entry.after ?? {})]));
  if (keys.length === 0 && !entry.reason)
    return <p className="text-[13px] text-fg-subtle">No field changes recorded.</p>;
  return (
    <div className="flex flex-col gap-3">
      {entry.reason && (
        <p className="text-[13px]">
          <span className="font-medium text-fg">Reason:</span>{" "}
          <span className="text-fg-muted">{entry.reason}</span>
        </p>
      )}
      {keys.length > 0 && (
        <table className="w-full max-w-3xl text-[13px]">
          <thead>
            <tr className="text-left text-xs text-fg-subtle">
              <th className="py-1 pr-4 font-medium">Field</th>
              <th className="py-1 pr-4 font-medium">Before</th>
              <th className="py-1 font-medium">After</th>
            </tr>
          </thead>
          <tbody>
            {keys.map((k) => (
              <tr key={k} className="align-top">
                <td className="py-1 pr-4 font-mono text-xs text-fg-muted">{k}</td>
                <td className="py-1 pr-4 text-danger line-through decoration-danger/40">
                  <Value value={entry.before?.[k]} />
                </td>
                <td className="py-1 text-success">
                  <Value value={entry.after?.[k]} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="text-xs text-fg-subtle">
        {entry.ip && <>IP {entry.ip} · </>}Event {entry.id}
      </p>
    </div>
  );
}

export default function AuditLogPage() {
  const [action, setAction] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const q = useInfiniteQuery({
    queryKey: ["audit", action],
    queryFn: ({ pageParam }) =>
      api.get<Page<AuditEntry>>("/api/v1/admin/audit-logs", {
        query: { action, cursor: pageParam, limit: 50 },
      }),
    initialPageParam: "" as string,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
  const rows = q.data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <>
      <PageHeader
        title="Audit log"
        description="Every change in your institution, who made it and when. Entries can't be edited or deleted."
      />
      <Toolbar>
        <Select
          value={action}
          onChange={(e) => setAction(e.target.value)}
          className="w-56"
          aria-label="Filter activity"
        >
          {ACTION_FILTERS.map((f) => (
            <option key={f.value} value={f.value}>
              {f.label}
            </option>
          ))}
        </Select>
      </Toolbar>
      <TableContainer>
        <Table>
          <THead>
            <tr>
              <Th className="w-8">
                <span className="sr-only">Expand</span>
              </Th>
              <Th>When</Th>
              <Th>Who</Th>
              <Th>What</Th>
            </tr>
          </THead>
          <TBody>
            {q.isPending ? (
              <TableSkeletonRows cols={4} rows={8} />
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={4}>
                  <EmptyState
                    icon={<ScrollText />}
                    title="No activity yet"
                    description="Changes made in your institution will be recorded here."
                  />
                </td>
              </tr>
            ) : (
              rows.map((e) => {
                const expanded = open === e.id;
                return (
                  <Fragment key={e.id}>
                    <tr
                      className="cursor-pointer hover:bg-surface-2/60"
                      onClick={() => setOpen(expanded ? null : e.id)}
                    >
                      <Td>
                        <button
                          type="button"
                          aria-expanded={expanded}
                          aria-label={expanded ? "Hide details" : "Show details"}
                          className="rounded p-0.5 text-fg-subtle hover:text-fg"
                          onClick={(ev) => {
                            ev.stopPropagation();
                            setOpen(expanded ? null : e.id);
                          }}
                        >
                          <ChevronRight
                            className={"size-4 transition-transform " + (expanded ? "rotate-90" : "")}
                          />
                        </button>
                      </Td>
                      <Td className="whitespace-nowrap text-fg-subtle tabular">
                        {formatDateTime(e.occurred_at)}
                      </Td>
                      <Td>
                        <div className="flex items-center gap-2">
                          {e.actor_type === "system" ? (
                            <Badge>System</Badge>
                          ) : (
                            <Avatar name={e.actor_label ?? "?"} size="sm" />
                          )}
                          <span className="truncate">{e.actor_type === "system" ? null : e.actor_label}</span>
                        </div>
                      </Td>
                      <Td>
                        <span className="text-fg">{e.summary ?? describeAction(e.action)}</span>
                        <span className="ml-2 font-mono text-xs text-fg-subtle">{e.action}</span>
                      </Td>
                    </tr>
                    {expanded && (
                      <tr className="bg-surface-2/40">
                        <td />
                        <td colSpan={3} className="px-4 py-4">
                          <Diff entry={e} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })
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
