import { api, type DeepHealth } from "@scorecode/api-client";
import { Badge, Button, PageHeader, Skeleton, formatDateTime } from "@scorecode/ui";
import { useQuery } from "@tanstack/react-query";
import { Database, HardDrive, Mail, RefreshCw, Zap } from "lucide-react";

const ICONS: Record<string, typeof Database> = {
  database: Database,
  redis: Zap,
  object_storage: HardDrive,
  email: Mail,
};
const LABELS: Record<string, string> = {
  database: "PostgreSQL",
  redis: "Redis cache",
  object_storage: "Object storage",
  email: "Email (SMTP)",
};
const EXPLAIN: Record<string, string> = {
  database: "Source of truth for all data and the job queue. Down means the API is down.",
  redis: "Optional cache and shared rate limits. If down, the app keeps working on local caches.",
  object_storage: "Logos, uploads and marksheet PDFs. If down, results still display; downloads fail.",
  email: "Outgoing notifications. If down, emails retry with backoff; in-app notifications are unaffected.",
};

export default function HealthPage() {
  const q = useQuery({
    queryKey: ["health"],
    queryFn: () => api.get<DeepHealth>("/api/v1/platform/health/deep"),
    refetchInterval: 15_000,
  });
  return (
    <>
      <PageHeader
        title="System health"
        description="Live checks of every dependency, refreshed every 15 seconds."
        actions={
          <Button
            variant="secondary"
            leadingIcon={<RefreshCw />}
            loading={q.isFetching}
            onClick={() => void q.refetch()}
          >
            Check now
          </Button>
        }
      />
      {q.isPending || !q.data ? (
        <div className="grid gap-4 md:grid-cols-2">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-32 rounded-xl" />
          ))}
        </div>
      ) : (
        <>
          <div className="grid gap-4 md:grid-cols-2">
            {q.data.checks.map((c) => {
              const Icon = ICONS[c.name] ?? Database;
              const tone =
                c.status === "up" ? "success" : c.status === "not_configured" ? "neutral" : "danger";
              return (
                <div key={c.name} className="rounded-xl border border-border bg-surface p-5 shadow-xs">
                  <div className="flex items-center gap-3">
                    <span className="flex size-9 items-center justify-center rounded-lg bg-surface-2 text-fg-subtle">
                      <Icon className="size-4" />
                    </span>
                    <span className="flex-1 text-sm font-semibold">{LABELS[c.name] ?? c.name}</span>
                    <Badge tone={tone} dot>
                      {c.status === "up"
                        ? "Operational"
                        : c.status === "not_configured"
                          ? "Not configured"
                          : "Down"}
                    </Badge>
                  </div>
                  <p className="mt-3 text-[13px] leading-5 text-fg-subtle">{EXPLAIN[c.name]}</p>
                  <p className="tabular mt-3 text-xs text-fg-subtle">
                    {c.latency_ms} ms{c.error ? ` · ${c.error}` : ""}
                    {c.circuit_breaker ? ` · circuit breaker ${c.circuit_breaker}` : ""}
                  </p>
                </div>
              );
            })}
          </div>
          <p className="mt-4 text-xs text-fg-subtle">Last checked {formatDateTime(q.data.checked_at)}</p>
        </>
      )}
    </>
  );
}
