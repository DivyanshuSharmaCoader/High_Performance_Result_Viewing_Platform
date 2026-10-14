import {
  api,
  ApiError,
  type Page,
  type PlansCatalog,
  type PlatformAuditEntry,
  type TenantDetail,
} from "@scorecode/api-client";
import {
  Badge,
  Button,
  Callout,
  ConfirmDialog,
  DescriptionList,
  Dialog,
  DialogContent,
  EmptyState,
  Field,
  Input,
  PageHeader,
  Section,
  Select,
  Skeleton,
  TBody,
  THead,
  Table,
  TableContainer,
  Td,
  Textarea,
  Th,
  formatDate,
  formatDateTime,
  formatNumber,
  formatRelative,
  toast,
} from "@scorecode/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ExternalLink, Pause, Play, Plus, SlidersHorizontal, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router";

import { useCan } from "../lib/session";
import { STATUS_TONE } from "./tenants";

const USAGE_LABELS: Record<string, string> = {
  active_students: "Active students",
  staff_users: "Staff accounts",
  admin_users: "Administrators",
  storage_bytes: "Storage",
  published_exams_year: "Publications this year",
};

function showValue(v: unknown): string {
  if (v === null || v === undefined) return "Unlimited";
  if (typeof v === "boolean") return v ? "On" : "Off";
  if (Array.isArray(v)) return v.join(", ");
  if (typeof v === "number") return v.toLocaleString("en-IN");
  return String(v);
}

function ChangePlanDialog({
  tenant,
  open,
  onOpenChange,
}: {
  tenant: TenantDetail;
  open: boolean;
  onOpenChange: (o: boolean) => void;
}) {
  const qc = useQueryClient();
  const catalog = useQuery({
    queryKey: ["plans"],
    queryFn: () => api.get<PlansCatalog>("/api/v1/platform/plans"),
    enabled: open,
  });
  const [plan, setPlan] = useState(tenant.current_plan ?? "free");
  const [status, setStatus] = useState("active");
  const [periodEnd, setPeriodEnd] = useState("");
  const [billingRef, setBillingRef] = useState("");
  const [reason, setReason] = useState("");
  const change = useMutation({
    mutationFn: () =>
      api.put(`/api/v1/platform/tenants/${tenant.id}/plan`, {
        plan_code: plan,
        status,
        period_end: periodEnd ? new Date(`${periodEnd}T23:59:59`).toISOString() : null,
        billing_ref: billingRef || null,
        reason,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["tenant", tenant.id] });
      void qc.invalidateQueries({ queryKey: ["tenants"] });
      toast.success("Plan updated", {
        description: "The institution sees the new entitlements immediately.",
      });
      onOpenChange(false);
    },
  });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        title="Change plan"
        description="Billing is manual in this release: record the invoice or payment reference."
        footer={
          <>
            <Button variant="secondary" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button
              loading={change.isPending}
              disabled={reason.trim().length < 3}
              onClick={() => change.mutate()}
            >
              Change plan
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-4">
          {change.error instanceof ApiError && <Callout tone="danger">{change.error.detail}</Callout>}
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Plan">
              <Select value={plan} onChange={(e) => setPlan(e.target.value)}>
                {(catalog.data?.plans ?? []).map((p) => (
                  <option key={p.code} value={p.code}>
                    {p.name}
                    {p.price_paise_yearly
                      ? ` · ₹${(p.price_paise_yearly / 100).toLocaleString("en-IN")}/yr`
                      : ""}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Status">
              <Select value={status} onChange={(e) => setStatus(e.target.value)}>
                <option value="active">Active</option>
                <option value="trialing">Trial</option>
                <option value="past_due">Payment due (grace)</option>
              </Select>
            </Field>
            <Field label="Period ends" optional>
              <Input type="date" value={periodEnd} onChange={(e) => setPeriodEnd(e.target.value)} />
            </Field>
            <Field label="Invoice / payment reference" optional>
              <Input
                value={billingRef}
                onChange={(e) => setBillingRef(e.target.value)}
                placeholder="INV-2026-014"
              />
            </Field>
          </div>
          <Field label="Reason (recorded in both audit logs)" required>
            <Textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={2} />
          </Field>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function OverrideDialog({
  tenant,
  open,
  onOpenChange,
}: {
  tenant: TenantDetail;
  open: boolean;
  onOpenChange: (o: boolean) => void;
}) {
  const qc = useQueryClient();
  const catalog = useQuery({
    queryKey: ["plans"],
    queryFn: () => api.get<PlansCatalog>("/api/v1/platform/plans"),
    enabled: open,
  });
  const [key, setKey] = useState("max_students");
  const [raw, setRaw] = useState("");
  const [expires, setExpires] = useState("");
  const [reason, setReason] = useState("");
  const feature = catalog.data?.features.find((f) => f.key === key);
  const value = (): unknown => {
    if (!feature) return null;
    if (feature.kind === "boolean") return raw === "true";
    if (feature.kind === "limit") return raw.trim() === "" ? null : Number(raw);
    return raw
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
  };
  const save = useMutation({
    mutationFn: () =>
      api.put(`/api/v1/platform/tenants/${tenant.id}/overrides/${key}`, {
        value: value(),
        expires_at: expires ? new Date(`${expires}T23:59:59`).toISOString() : null,
        reason,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["tenant", tenant.id] });
      toast.success("Override saved");
      onOpenChange(false);
    },
  });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        title="Adjust a limit or feature"
        description="Overrides beat the plan value until they expire — e.g. a temporary student boost during admissions."
        footer={
          <>
            <Button variant="secondary" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button
              loading={save.isPending}
              disabled={reason.trim().length < 3}
              onClick={() => save.mutate()}
            >
              Save override
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-4">
          {save.error instanceof ApiError && <Callout tone="danger">{save.error.detail}</Callout>}
          <Field label="Feature">
            <Select
              value={key}
              onChange={(e) => {
                setKey(e.target.value);
                setRaw("");
              }}
            >
              {(catalog.data?.features ?? []).map((f) => (
                <option key={f.key} value={f.key}>
                  {f.description}
                </option>
              ))}
            </Select>
          </Field>
          {feature?.kind === "boolean" ? (
            <Field label="Value">
              <Select value={raw} onChange={(e) => setRaw(e.target.value)}>
                <option value="true">On</option>
                <option value="false">Off</option>
              </Select>
            </Field>
          ) : (
            <Field
              label="Value"
              description={feature?.kind === "limit" ? "Leave empty for unlimited." : "Comma-separated list."}
            >
              <Input
                value={raw}
                onChange={(e) => setRaw(e.target.value)}
                inputMode={feature?.kind === "limit" ? "numeric" : "text"}
              />
            </Field>
          )}
          <Field label="Expires" optional description="After this date the plan value applies again.">
            <Input type="date" value={expires} onChange={(e) => setExpires(e.target.value)} />
          </Field>
          <Field label="Reason" required>
            <Textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={2} />
          </Field>
        </div>
      </DialogContent>
    </Dialog>
  );
}

const TRIAL_TONE = { active: "info", ended: "neutral", converted: "success", revoked: "warning" } as const;
const FLAG_LABEL: Record<string, string> = {
  phone: "phone seen before",
  name: "same institution name",
  subnet: "busy network",
};

function TrialSection({ t, canManage }: { t: TenantDetail; canManage: boolean }) {
  const qc = useQueryClient();
  const [action, setAction] = useState<"grant" | "revoke" | null>(null);
  const run = useMutation({
    mutationFn: ({ kind, reason }: { kind: "grant" | "revoke"; reason: string }) =>
      api.post(`/api/v1/platform/tenants/${t.id}/trial${kind === "revoke" ? "/revoke" : ""}`, { reason }),
    onSuccess: (_d, v) => {
      void qc.invalidateQueries({ queryKey: ["tenant", t.id] });
      void qc.invalidateQueries({ queryKey: ["tenant-audit", t.id] });
      toast.success(v.kind === "grant" ? "Trial started" : "Trial revoked — back on Free");
      setAction(null);
    },
    onError: (e) => {
      setAction(null);
      toast.error(e instanceof ApiError ? e.detail : "That didn't work");
    },
  });
  const trial = t.trial;
  return (
    <Section
      title="Free trial"
      description="One per institution, ever. Started by the owner, or by staff after a review."
      actions={
        canManage &&
        (trial === null ? (
          <Button size="sm" variant="secondary" onClick={() => setAction("grant")}>
            Start trial
          </Button>
        ) : trial.status === "active" ? (
          <Button size="sm" variant="danger-outline" onClick={() => setAction("revoke")}>
            Revoke
          </Button>
        ) : null)
      }
    >
      {trial === null ? (
        <p className="text-sm text-fg-subtle">Not used yet.</p>
      ) : (
        <div className="flex flex-col gap-3 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={TRIAL_TONE[trial.status]} dot>
              {trial.status}
            </Badge>
            {trial.granted && <Badge tone="neutral">Started by staff</Badge>}
            {trial.risk_score > 0 && (
              <Badge tone="warning">
                Risk {trial.risk_score}: {trial.flags.map((f) => FLAG_LABEL[f] ?? f).join(", ")}
              </Badge>
            )}
          </div>
          <p className="text-fg-muted">
            {formatDate(trial.started_at)} → {formatDate(trial.ends_at)}
            {trial.ended_at && (
              <>
                {" "}
                · ended {formatDate(trial.ended_at)}
                {trial.end_reason ? ` (${trial.end_reason})` : ""}
              </>
            )}
          </p>
        </div>
      )}
      <ConfirmDialog
        open={action !== null}
        onOpenChange={(o) => !o && setAction(null)}
        title={
          action === "grant" ? "Start the 30-day trial for this institution?" : "Revoke the running trial?"
        }
        description={
          action === "grant"
            ? "Use this after checking a trial the automatic review held back. It still counts as their one trial."
            : "The institution returns to Free now. Nothing is deleted."
        }
        confirmLabel={action === "grant" ? "Start trial" : "Revoke trial"}
        variant={action === "revoke" ? "danger" : "primary"}
        requireReason
        loading={run.isPending}
        onConfirm={(reason) => {
          if (action) run.mutate({ kind: action, reason });
        }}
      />
    </Section>
  );
}

export default function TenantDetailPage() {
  const { id = "" } = useParams();
  const qc = useQueryClient();
  const canManage = useCan("platform.tenants.manage");
  const [planOpen, setPlanOpen] = useState(false);
  const [overrideOpen, setOverrideOpen] = useState(false);
  const [statusAction, setStatusAction] = useState<"suspend" | "reactivate" | null>(null);
  const [erasing, setErasing] = useState(false);
  const [removeKey, setRemoveKey] = useState<string | null>(null);
  const tenant = useQuery({
    queryKey: ["tenant", id],
    queryFn: () => api.get<TenantDetail>(`/api/v1/platform/tenants/${id}`),
  });
  const audit = useQuery({
    queryKey: ["tenant-audit", id],
    queryFn: () =>
      api.get<Page<PlatformAuditEntry>>("/api/v1/platform/audit-logs", {
        query: { tenant_id: id, limit: 10 },
      }),
    retry: false,
  });
  const setStatus = useMutation({
    mutationFn: ({ action, reason }: { action: "suspend" | "reactivate"; reason: string }) =>
      api.post(`/api/v1/platform/tenants/${id}/${action}`, { reason }),
    onSuccess: (_d, v) => {
      void qc.invalidateQueries({ queryKey: ["tenant", id] });
      void qc.invalidateQueries({ queryKey: ["tenant-audit", id] });
      toast.success(
        v.action === "suspend"
          ? "Institution suspended — all sessions were signed out"
          : "Institution reactivated",
      );
      setStatusAction(null);
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.detail : "Couldn't change status"),
  });
  const erase = useMutation({
    mutationFn: (reason: string) =>
      api.post(`/api/v1/platform/tenants/${id}/erase`, { confirm: tenant.data?.slug ?? "", reason }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["tenant", id] });
      void qc.invalidateQueries({ queryKey: ["tenant-audit", id] });
      toast.success("Erasure approved — the portal is offline; the data is erased within minutes");
      setErasing(false);
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.detail : "Couldn't approve the erasure"),
  });
  const removeOverride = useMutation({
    mutationFn: ({ key, reason }: { key: string; reason: string }) =>
      api.delete(`/api/v1/platform/tenants/${id}/overrides/${key}`, { query: { reason } }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["tenant", id] });
      toast.success("Override removed");
      setRemoveKey(null);
    },
  });

  if (tenant.isPending) return <Skeleton className="h-96 rounded-xl" />;
  if (tenant.error || !tenant.data) {
    return (
      <EmptyState title="Institution not found" action={<Link to="/tenants">Back to institutions</Link>} />
    );
  }
  const t = tenant.data;
  return (
    <>
      <PageHeader
        breadcrumb={
          <Link to="/tenants" className="inline-flex items-center gap-1 hover:text-fg">
            <ArrowLeft className="size-3.5" /> Institutions
          </Link>
        }
        title={t.name}
        meta={
          <>
            <Badge tone={STATUS_TONE[t.status] ?? "neutral"} dot>
              {t.status}
            </Badge>
            <Badge tone="brand">
              {t.subscriptions.find((s) => ["active", "trialing", "past_due"].includes(s.status))
                ?.plan_name ?? "No plan"}
            </Badge>
            <a
              href={`${window.location.protocol}//${t.host}${window.location.port ? `:${window.location.port}` : ""}`}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 font-mono text-xs text-fg-subtle hover:text-fg"
            >
              {t.host} <ExternalLink className="size-3" />
            </a>
          </>
        }
        actions={
          canManage && (
            <>
              <Button
                variant="secondary"
                leadingIcon={<SlidersHorizontal />}
                onClick={() => setPlanOpen(true)}
              >
                Change plan
              </Button>
              {t.status === "suspended" ? (
                <Button leadingIcon={<Play />} onClick={() => setStatusAction("reactivate")}>
                  Reactivate
                </Button>
              ) : (
                <Button
                  variant="danger-outline"
                  leadingIcon={<Pause />}
                  onClick={() => setStatusAction("suspend")}
                >
                  Suspend
                </Button>
              )}
            </>
          )
        }
      />
      {t.status === "suspended" && t.status_reason && (
        <Callout tone="danger" title="Suspended" className="mb-6">
          {t.status_reason}
        </Callout>
      )}
      {t.closure && t.status !== "closed" && (
        <Callout
          tone="warning"
          className="mb-6"
          title={
            t.status === "closing"
              ? "Erasure approved — the data is being erased"
              : `The institution asked to close its account on ${formatDateTime(t.closure.requested_at)}`
          }
        >
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span>
              {t.closure.reason && <>“{t.closure.reason}” · </>}
              {t.closure.erasable
                ? "Its 30 days to export and change its mind have passed."
                : `It can export and change its mind until ${formatDateTime(t.closure.delete_after)}.`}
            </span>
            {canManage && t.closure.erasable && t.status !== "closing" && (
              <Button variant="danger" size="sm" onClick={() => setErasing(true)}>
                Erase permanently…
              </Button>
            )}
          </div>
        </Callout>
      )}
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="flex min-w-0 flex-col gap-6">
          <Section title="Usage">
            <dl className="grid gap-4 sm:grid-cols-3">
              {Object.entries(USAGE_LABELS).map(([k, label]) => (
                <div key={k}>
                  <dt className="text-[13px] text-fg-subtle">{label}</dt>
                  <dd className="tabular text-lg font-semibold">
                    {k === "storage_bytes"
                      ? `${((t.usage[k] ?? 0) / 1024 / 1024).toFixed(1)} MB`
                      : formatNumber(t.usage[k] ?? 0)}
                  </dd>
                </div>
              ))}
            </dl>
          </Section>
          <TrialSection t={t} canManage={canManage} />
          <Section
            title="Overrides"
            description="Per-institution exceptions to the plan."
            actions={
              canManage && (
                <Button
                  size="sm"
                  variant="secondary"
                  leadingIcon={<Plus />}
                  onClick={() => setOverrideOpen(true)}
                >
                  Add override
                </Button>
              )
            }
          >
            {t.overrides.length === 0 ? (
              <p className="text-sm text-fg-subtle">This institution uses its plan's values.</p>
            ) : (
              <ul className="divide-y divide-border">
                {t.overrides.map((o) => (
                  <li key={o.feature_key} className="flex items-start gap-3 py-3 first:pt-0 last:pb-0">
                    <div className="min-w-0 flex-1">
                      <p className="text-sm">
                        <span className="font-mono text-[13px]">{o.feature_key}</span> →{" "}
                        <span className="font-medium">{showValue(o.value)}</span>
                      </p>
                      <p className="mt-0.5 text-[13px] text-fg-subtle">
                        {o.reason}
                        {o.expires_at ? ` · until ${formatDate(o.expires_at)}` : " · no expiry"}
                      </p>
                    </div>
                    {canManage && (
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label={`Remove ${o.feature_key} override`}
                        onClick={() => setRemoveKey(o.feature_key)}
                      >
                        <Trash2 />
                      </Button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Section>
          <Section title="Subscription history">
            <TableContainer className="shadow-none">
              <Table>
                <THead>
                  <tr>
                    <Th>Plan</Th>
                    <Th>Status</Th>
                    <Th>From</Th>
                    <Th>Until</Th>
                    <Th>Reference</Th>
                  </tr>
                </THead>
                <TBody>
                  {t.subscriptions.map((s) => (
                    <tr key={s.id}>
                      <Td className="font-medium">{s.plan_name}</Td>
                      <Td>
                        <Badge
                          tone={
                            s.status === "active"
                              ? "success"
                              : s.status === "cancelled"
                                ? "neutral"
                                : "warning"
                          }
                        >
                          {s.status}
                        </Badge>
                      </Td>
                      <Td className="text-fg-subtle">{formatDate(s.period_start)}</Td>
                      <Td className="text-fg-subtle">{formatDate(s.period_end)}</Td>
                      <Td className="font-mono text-xs text-fg-subtle">{s.billing_ref ?? "—"}</Td>
                    </tr>
                  ))}
                </TBody>
              </Table>
            </TableContainer>
          </Section>
        </div>
        <div className="flex flex-col gap-6">
          <Section title="Details">
            <DescriptionList
              className="sm:grid-cols-1"
              items={[
                { term: "Official name", detail: t.official_name },
                { term: "Type", detail: <span className="capitalize">{t.type}</span> },
                { term: "Contact", detail: t.contact_email ?? "—" },
                { term: "Users", detail: `${t.users.staff} staff · ${t.users.students} students` },
                { term: "Created", detail: formatDateTime(t.created_at) },
                { term: "Last activity", detail: formatRelative(t.last_activity_at) },
              ]}
            />
          </Section>
          <Section title="Staff actions">
            {audit.isPending ? (
              <Skeleton className="h-24" />
            ) : audit.data && audit.data.items.length > 0 ? (
              <ol className="flex flex-col gap-3 text-sm">
                {audit.data.items.map((a) => (
                  <li key={a.id}>
                    <span className="font-mono text-[13px]">{a.action}</span>
                    <span className="block text-[13px] text-fg-subtle">
                      {a.actor_label} · {formatRelative(a.occurred_at)}
                      {a.reason ? ` — ${a.reason}` : ""}
                    </span>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="text-sm text-fg-subtle">
                {audit.error ? "Your role can't view the platform audit log." : "No staff actions yet."}
              </p>
            )}
          </Section>
        </div>
      </div>
      {planOpen && <ChangePlanDialog tenant={t} open={planOpen} onOpenChange={setPlanOpen} />}
      {overrideOpen && <OverrideDialog tenant={t} open={overrideOpen} onOpenChange={setOverrideOpen} />}
      <ConfirmDialog
        open={statusAction !== null}
        onOpenChange={(o) => !o && setStatusAction(null)}
        title={statusAction === "suspend" ? `Suspend ${t.name}?` : `Reactivate ${t.name}?`}
        description={
          statusAction === "suspend"
            ? "Everyone at this institution is signed out and sees a “temporarily unavailable” page. No data is deleted."
            : "The portal becomes available again. Users sign in as usual."
        }
        confirmLabel={statusAction === "suspend" ? "Suspend institution" : "Reactivate"}
        variant={statusAction === "suspend" ? "danger" : "primary"}
        requireReason
        reasonLabel="Reason (visible in the institution's audit log)"
        confirmText={statusAction === "suspend" ? t.slug : undefined}
        loading={setStatus.isPending}
        onConfirm={(reason) => {
          if (statusAction) setStatus.mutate({ action: statusAction, reason });
        }}
      />
      <ConfirmDialog
        open={erasing}
        onOpenChange={(o) => !o && setErasing(false)}
        title={`Erase ${t.name} permanently?`}
        description="The portal goes offline now and every record and file of this institution is deleted within minutes. A tombstone, the subscription records and the platform audit log remain; encrypted backups expire on their own schedule. This can't be undone."
        confirmLabel="Erase permanently"
        variant="danger"
        requireReason
        reasonLabel="Reason (kept in the platform audit log)"
        confirmText={t.slug}
        loading={erase.isPending}
        onConfirm={(reason) => erase.mutate(reason)}
      />
      <ConfirmDialog
        open={removeKey !== null}
        onOpenChange={(o) => !o && setRemoveKey(null)}
        title="Remove this override?"
        description="The plan's value applies again immediately."
        confirmLabel="Remove override"
        variant="danger"
        requireReason
        loading={removeOverride.isPending}
        onConfirm={(reason) => {
          if (removeKey) removeOverride.mutate({ key: removeKey, reason });
        }}
      />
    </>
  );
}
