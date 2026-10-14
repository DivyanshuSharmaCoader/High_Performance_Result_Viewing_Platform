import { api, ApiError, type Closure, type DataExport, type ExportLink } from "@scorecode/api-client";
import {
  Badge,
  Button,
  Callout,
  ConfirmDialog,
  EmptyState,
  Section,
  Skeleton,
  formatDateTime,
  formatNumber,
  formatRelative,
  toast,
} from "@scorecode/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, Download, FileArchive, Trash2, Undo2 } from "lucide-react";
import { useState } from "react";

import { useReauth } from "../../components/reauth";
import { toastError } from "../../lib/forms";
import { goTo } from "../../lib/navigate";
import { useCan } from "../../lib/session";
import { useTenant } from "../../lib/tenant";

const URL = "/api/v1/admin/exports";
const STATUS = {
  queued: { label: "Waiting", tone: "info" },
  running: { label: "Preparing", tone: "info" },
  ready: { label: "Ready", tone: "success" },
  failed: { label: "Failed", tone: "danger" },
  expired: { label: "Expired", tone: "neutral" },
} as const;

const size = (b: number | null | undefined) =>
  b == null
    ? ""
    : b < 1024 * 1024
      ? `${formatNumber(Math.ceil(b / 1024))} KB`
      : `${(b / 1024 / 1024).toFixed(1)} MB`;

/** Settings → Your data (P18.5): every record of the institution, as a ZIP of CSV files. Owner only. */
export function DataExportPage() {
  const can = useCan("data.export");
  const closeable = useCan("account.close");
  const qc = useQueryClient();
  const withReauth = useReauth();
  const exports = useQuery({
    queryKey: ["exports"],
    queryFn: () => api.get<DataExport[]>(URL),
    enabled: can,
    refetchInterval: (q) =>
      q.state.data?.some((x) => x.status === "queued" || x.status === "running") ? 3000 : false,
  });
  const request = useMutation({
    mutationFn: () => withReauth(() => api.post<DataExport>(URL)),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["exports"] });
      toast.success("Preparing your export — it appears here in a minute or two");
    },
    onError: (e) => !(e instanceof ApiError && e.code === "reauth-cancelled") && toastError(e),
  });
  const download = useMutation({
    mutationFn: (id: string) => withReauth(() => api.post<ExportLink>(`${URL}/${id}/link`)),
    onSuccess: (link) => goTo(link.url),
    onError: (e) => !(e instanceof ApiError && e.code === "reauth-cancelled") && toastError(e),
  });

  if (!can) {
    return (
      <Callout tone="info" title="Only the institution's owner can export all of its data">
        Ask your owner to export it from Settings → Your data.
      </Callout>
    );
  }
  const list = exports.data ?? [];
  const busy = list.some((x) => x.status === "queued" || x.status === "running");
  return (
    <>
      <Section
        title="Export all your data"
        description="Students, staff, structure, exams, every mark, every published result, verification codes and the audit log, as CSV files you can open in Excel. Passwords and other secrets are never included."
        actions={
          <Button
            leadingIcon={<Archive />}
            loading={request.isPending}
            disabled={busy}
            onClick={() => request.mutate()}
          >
            {busy ? "Preparing…" : "Export everything"}
          </Button>
        }
      >
        <p className="mb-4 text-[13px] text-fg-muted">
          Your data is yours: export it whenever you like, as often as five times a day. Each export is kept
          for seven days, then deleted. Downloading asks for your password and is recorded in the audit log.
        </p>
        {exports.isPending ? (
          <Skeleton className="h-24 w-full" />
        ) : list.length === 0 ? (
          <EmptyState
            compact
            icon={<FileArchive />}
            title="No exports yet"
            description="Your exports will be listed here."
          />
        ) : (
          <ul className="divide-y divide-border rounded-xl border border-border">
            {list.map((x) => (
              <li key={x.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-3">
                <Badge tone={STATUS[x.status].tone}>{STATUS[x.status].label}</Badge>
                <span className="text-sm text-fg">Requested {formatDateTime(x.created_at)}</span>
                {x.status === "ready" && (
                  <span className="text-[13px] text-fg-subtle">
                    {size(x.size_bytes)}
                    {x.counts &&
                      ` · ${formatNumber(Object.values(x.counts).reduce((a: number, b) => a + Number(b), 0))} rows`}
                    {x.expires_at && ` · deleted ${formatRelative(x.expires_at)}`}
                  </span>
                )}
                {x.status === "failed" && (
                  <span className="text-[13px] text-danger">
                    Something went wrong. Try again; we&apos;re told automatically.
                  </span>
                )}
                {x.status === "ready" && (
                  <Button
                    size="sm"
                    variant="secondary"
                    className="ml-auto"
                    leadingIcon={<Download />}
                    loading={download.isPending && download.variables === x.id}
                    onClick={() => download.mutate(x.id)}
                  >
                    Download
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
      </Section>
      {closeable && <CloseAccountSection />}
    </>
  );
}

/** Settings → Your data → Close the account (P18.14). Owner only: 30 days to export and to change one's
 * mind; then ScoreCode staff approve and everything is erased. */
export function CloseAccountSection() {
  const tenant = useTenant();
  const qc = useQueryClient();
  const withReauth = useReauth();
  const [open, setOpen] = useState(false);
  const state = useQuery({
    queryKey: ["closure"],
    queryFn: () => api.get<Closure>("/api/v1/admin/closure"),
  });
  const done = (message: string) => {
    void qc.invalidateQueries({ queryKey: ["closure"] });
    setOpen(false);
    toast.success(message);
  };
  const request = useMutation({
    mutationFn: (reason: string) =>
      withReauth(() => api.post<Closure>("/api/v1/admin/closure", { reason, confirm: tenant.tenant.slug })),
    onSuccess: () => done("Closing is scheduled — every administrator has been emailed"),
    onError: (e) => {
      setOpen(false);
      if (!(e instanceof ApiError && e.code === "reauth-cancelled")) toastError(e);
    },
  });
  const cancel = useMutation({
    mutationFn: () => withReauth(() => api.delete<Closure>("/api/v1/admin/closure")),
    onSuccess: () => done("Closure cancelled — nothing will be erased"),
    onError: (e) => !(e instanceof ApiError && e.code === "reauth-cancelled") && toastError(e),
  });
  if (!state.data) return null;
  const c = state.data;
  return (
    <Section
      title="Close the account"
      description="Ends your use of ScoreCode and erases your institution's data."
      className="mt-6"
    >
      {c.requested ? (
        <Callout tone="danger" title={`Your data will be erased after ${formatDateTime(c.delete_after)}`}>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span>
              Until then everything keeps working. Export your data above if you want to keep it. After that
              date, ScoreCode staff confirm and every record and file is deleted.
            </span>
            <Button
              size="sm"
              variant="secondary"
              leadingIcon={<Undo2 />}
              loading={cancel.isPending}
              onClick={() => cancel.mutate()}
            >
              Cancel closure
            </Button>
          </div>
        </Callout>
      ) : (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="max-w-2xl text-[13px] text-fg-muted">
            You have 30 days after asking to export your data and to change your mind; every administrator is
            emailed. Then everything is erased: students, marks, results, marksheets, staff accounts and the
            audit log. Encrypted backups expire within about a month. No fee, no notice period.
          </p>
          <Button variant="danger-outline" leadingIcon={<Trash2 />} onClick={() => setOpen(true)}>
            Close the account…
          </Button>
        </div>
      )}
      <ConfirmDialog
        open={open}
        onOpenChange={setOpen}
        title="Close your ScoreCode account?"
        description="Your data is erased 30 days from now unless you cancel. Export it first if you want to keep it."
        confirmLabel="Close the account"
        variant="danger"
        requireReason
        reasonLabel="Why are you leaving? (recorded in the audit log)"
        confirmText={tenant.tenant.slug}
        loading={request.isPending}
        onConfirm={(reason) => request.mutate(reason)}
      />
    </Section>
  );
}
