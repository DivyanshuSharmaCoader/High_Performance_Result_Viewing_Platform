import { api, type PlatformOverview } from "@scorecode/api-client";
import {
  Badge,
  PageHeader,
  Section,
  Skeleton,
  StatTile,
  TBody,
  THead,
  Table,
  TableContainer,
  Td,
  Th,
  formatNumber,
} from "@scorecode/ui";
import { useQuery } from "@tanstack/react-query";
import { Building2, GraduationCap, Megaphone, Users } from "lucide-react";

const STATUS_TONE: Record<string, "success" | "warning" | "danger" | "neutral"> = {
  active: "success",
  suspended: "danger",
  closing: "warning",
  closed: "neutral",
};

export default function OverviewPage() {
  const q = useQuery({
    queryKey: ["overview"],
    queryFn: () => api.get<PlatformOverview>("/api/v1/platform/metrics/overview"),
    refetchInterval: 30_000,
  });
  const d = q.data;
  const totalTenants = d ? Object.values(d.tenants.by_status).reduce((a, b) => a + b, 0) : 0;
  return (
    <>
      <PageHeader
        title="Overview"
        description="Institutions, usage and background work across the platform. Refreshes every 30 seconds."
      />
      {q.isPending || !d ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-28 rounded-xl" />
          ))}
        </div>
      ) : (
        <div className="flex flex-col gap-6">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatTile
              label="Institutions"
              value={formatNumber(totalTenants)}
              icon={<Building2 />}
              hint={`${d.tenants.new_last_7_days} new this week`}
            />
            <StatTile
              label="Active students"
              value={formatNumber(d.users.active_students)}
              icon={<GraduationCap />}
            />
            <StatTile label="Staff accounts" value={formatNumber(d.users.staff)} icon={<Users />} />
            <StatTile
              label="Publications live"
              value={formatNumber(d.publications.live)}
              icon={<Megaphone />}
              hint={`${d.publications.last_7_days} published this week`}
            />
          </div>
          <div className="grid gap-6 lg:grid-cols-2">
            <Section title="Institutions by status">
              <ul className="flex flex-col gap-3">
                {Object.entries(d.tenants.by_status).map(([status, n]) => (
                  <li key={status} className="flex items-center justify-between text-sm">
                    <Badge tone={STATUS_TONE[status] ?? "neutral"} dot>
                      {status}
                    </Badge>
                    <span className="tabular font-medium">{formatNumber(n)}</span>
                  </li>
                ))}
              </ul>
            </Section>
            <Section title="Institutions by plan">
              <ul className="flex flex-col gap-3">
                {Object.entries(d.tenants.by_plan).map(([plan, n]) => (
                  <li key={plan} className="flex items-center justify-between text-sm">
                    <span className="capitalize">{plan}</span>
                    <span className="tabular font-medium">{formatNumber(n)}</span>
                  </li>
                ))}
              </ul>
            </Section>
          </div>
          <Section title="Background jobs" description="Queued, running and dead-lettered work by queue.">
            {d.queues.length === 0 ? (
              <p className="text-sm text-fg-subtle">No queued, running or failed jobs.</p>
            ) : (
              <TableContainer className="shadow-none">
                <Table>
                  <THead>
                    <tr>
                      <Th>Queue</Th>
                      <Th>Status</Th>
                      <Th className="text-right">Jobs</Th>
                      <Th className="text-right">Oldest waiting</Th>
                    </tr>
                  </THead>
                  <TBody>
                    {d.queues.map((row) => (
                      <tr key={`${row.queue}-${row.status}`}>
                        <Td className="font-mono text-[13px]">{row.queue}</Td>
                        <Td>
                          <Badge
                            tone={
                              row.status === "dead" ? "danger" : row.status === "running" ? "info" : "neutral"
                            }
                          >
                            {row.status}
                          </Badge>
                        </Td>
                        <Td className="tabular text-right">{row.count}</Td>
                        <Td className="tabular text-right text-fg-subtle">
                          {row.status === "queued" ? `${Math.round(row.oldest_seconds)} s` : "—"}
                        </Td>
                      </tr>
                    ))}
                  </TBody>
                </Table>
              </TableContainer>
            )}
          </Section>
          <Section
            title="API process metrics"
            description={`Measured by ${d.process_metrics.scope}. Use Prometheus for the fleet-wide view.`}
          >
            <dl className="grid gap-4 sm:grid-cols-3">
              <div>
                <dt className="text-[13px] text-fg-subtle">Requests served</dt>
                <dd className="tabular text-lg font-semibold">
                  {formatNumber(d.process_metrics.requests_total)}
                </dd>
              </div>
              <div>
                <dt className="text-[13px] text-fg-subtle">Server errors (5xx)</dt>
                <dd className="tabular text-lg font-semibold">
                  {formatNumber(d.process_metrics.errors_5xx)}
                </dd>
              </div>
              <div>
                <dt className="text-[13px] text-fg-subtle">Redis cache hit rate</dt>
                <dd className="tabular text-lg font-semibold">
                  {d.process_metrics.redis_cache_hit_rate === null
                    ? "No data"
                    : `${(d.process_metrics.redis_cache_hit_rate * 100).toFixed(1)}%`}
                </dd>
              </div>
            </dl>
            {Object.keys(d.process_metrics.p95_upper_bound_ms_by_route_class).length > 0 && (
              <div className="mt-5 border-t border-border pt-4">
                <p className="mb-2 text-[13px] font-medium">p95 latency (histogram bucket upper bound)</p>
                <ul className="flex flex-wrap gap-2">
                  {Object.entries(d.process_metrics.p95_upper_bound_ms_by_route_class).map(([k, v]) => (
                    <li key={k}>
                      <Badge>
                        {k}: ≤ {v === null ? "∞" : `${v} ms`}
                      </Badge>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </Section>
        </div>
      )}
    </>
  );
}
