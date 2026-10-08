import { api, ApiError, newIdempotencyKey, type Publication } from "@scorecode/api-client";
import {
  Badge,
  Button,
  Callout,
  ConfirmDialog,
  Dialog,
  DialogContent,
  Field,
  Input,
  ProgressBar,
  Section,
  formatDateTime,
  formatNumber,
  formatRelative,
  toast,
} from "@scorecode/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, Eye, EyeOff, FileCheck2, Lock, RefreshCw, Rocket, Undo2 } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import { useReauth } from "../../components/reauth";
import { toastError } from "../../lib/forms";
import { useCan, useSession } from "../../lib/session";

const STATUS = {
  scheduled: { label: "Scheduled", tone: "info" },
  published: { label: "Live", tone: "success" },
  superseded: { label: "Replaced", tone: "neutral" },
  withdrawn: { label: "Withdrawn", tone: "warning" },
  cancelled: { label: "Cancelled", tone: "neutral" },
} as const;

const pubsUrl = (examId: string) => `/api/v1/admin/exams/${examId}/publications`;

/** "2026-10-09T10:00" in the browser's zone, at least `minutes` ahead, rounded to 5 minutes. */
function soonest(minutes = 15): string {
  const d = new Date(Date.now() + minutes * 60_000);
  d.setMinutes(Math.ceil(d.getMinutes() / 5) * 5, 0, 0);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function PublishPanel({
  examId,
  examStatus,
  students,
}: {
  examId: string;
  examStatus: string;
  students: number;
}) {
  const qc = useQueryClient();
  const withReauth = useReauth();
  const canPublish = useCan("publications.manage");
  const canSchedule = Boolean(useSession().features.scheduled_publication);
  const pubs = useQuery({
    queryKey: ["publications", examId],
    queryFn: () => api.get<Publication[]>(pubsUrl(examId)),
    // Follow marksheet rendering while it runs; stop polling once nothing is pending.
    refetchInterval: (q) => (q.state.data?.some((p) => (p.marksheets?.pending ?? 0) > 0) ? 3000 : false),
  });
  const [action, setAction] = useState<null | "now" | "withdraw" | "cancel">(null);
  const [scheduling, setScheduling] = useState(false);
  const [at, setAt] = useState("");
  const [minAt, setMinAt] = useState("");
  const [key, setKey] = useState("");
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["publications", examId] });
    void qc.invalidateQueries({ queryKey: ["results", examId] });
    void qc.invalidateQueries({ queryKey: ["exams"] });
  };
  const run = useMutation({
    mutationFn: async (v: {
      kind: "now" | "schedule" | "withdraw" | "cancel";
      reason?: string;
      id?: string;
    }) => {
      if (v.kind === "now" || v.kind === "schedule") {
        const body = v.kind === "schedule" ? { at: new Date(at).toISOString() } : {};
        return withReauth(() => api.post<Publication>(pubsUrl(examId), body, { idempotencyKey: key }));
      }
      if (v.kind === "withdraw") {
        return withReauth(() =>
          api.post<Publication>(`${pubsUrl(examId)}/${v.id}/withdraw`, { reason: v.reason }),
        );
      }
      return api.post<Publication>(`${pubsUrl(examId)}/${v.id}/cancel`);
    },
    onSuccess: (p, v) => {
      setAction(null);
      setScheduling(false);
      refresh();
      toast.success(
        v.kind === "now"
          ? `Published to ${formatNumber(p.students)} students`
          : v.kind === "schedule"
            ? `Scheduled for ${formatDateTime(p.scheduled_at)}`
            : v.kind === "withdraw"
              ? "Results withdrawn — students no longer see them"
              : "Schedule cancelled",
      );
    },
    onError: (e) => {
      setAction(null);
      if (!(e instanceof ApiError && e.code === "reauth-cancelled")) toastError(e);
    },
  });
  const open = (a: "now") => {
    setKey(newIdempotencyKey());
    setAction(a);
  };
  const list = pubs.data ?? [];
  const live = list.find((p) => p.status === "published");
  const scheduled = list.find((p) => p.status === "scheduled");
  const current = live ?? scheduled;
  const ready = examStatus === "approved" || examStatus === "withdrawn";

  let body;
  if (live) {
    body = (
      <Callout tone="success" title={`Live since ${formatDateTime(live.published_at)}`}>
        Version {live.version}, seen by {formatNumber(live.students)} students. Each one sees only their own
        result.
      </Callout>
    );
  } else if (scheduled) {
    body = (
      <Callout tone="info" title={`Goes live ${formatDateTime(scheduled.scheduled_at)}`}>
        {formatRelative(scheduled.scheduled_at)}, automatically. Nothing is visible to students until then.
      </Callout>
    );
  } else if (ready) {
    body = (
      <p className="text-sm text-fg-muted">
        {examStatus === "withdrawn"
          ? "These results were withdrawn. Publishing again makes a new version; students see only the latest."
          : `Approved and ready. Publishing makes each of the ${formatNumber(students)} students' results visible to them — and only to them.`}
      </p>
    );
  } else {
    return null;
  }

  return (
    <Section
      title="Publication"
      actions={
        canPublish && (
          <div className="flex flex-wrap gap-2">
            {live && (
              <Button
                size="sm"
                variant="danger-outline"
                leadingIcon={<EyeOff />}
                onClick={() => setAction("withdraw")}
              >
                Withdraw
              </Button>
            )}
            {scheduled && (
              <Button
                size="sm"
                variant="secondary"
                leadingIcon={<Undo2 />}
                onClick={() => setAction("cancel")}
              >
                Cancel schedule
              </Button>
            )}
            {ready && !scheduled && (
              <>
                <Button
                  size="sm"
                  variant="secondary"
                  leadingIcon={canSchedule ? <CalendarClock /> : <Lock />}
                  disabled={!canSchedule}
                  title={canSchedule ? undefined : "Scheduled publication is part of Growth and Pro"}
                  onClick={() => {
                    setKey(newIdempotencyKey());
                    setAt(soonest());
                    setMinAt(soonest(2));
                    setScheduling(true);
                  }}
                >
                  Schedule…
                </Button>
                <Button size="sm" leadingIcon={<Rocket />} onClick={() => open("now")}>
                  {examStatus === "withdrawn" ? "Publish again" : "Publish now"}
                </Button>
              </>
            )}
          </div>
        )
      }
    >
      {body}
      {current && <Marksheets examId={examId} pub={current} canRetry={canPublish} onRetried={refresh} />}
      {!canSchedule && ready && !scheduled && canPublish && (
        <p className="mt-3 text-[13px] text-fg-subtle">
          Want results to go live at a set time, like 10:00 on result day?{" "}
          <Link to="/admin/plan" className="font-medium text-brand-ink hover:underline">
            Scheduling comes with Growth and Pro — or the free trial.
          </Link>
        </p>
      )}
      {list.length > 0 && (
        <ol className="mt-4 flex flex-col gap-2 border-t border-border pt-4 text-[13px]">
          {list.map((p) => (
            <li key={p.id} className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <Badge tone={STATUS[p.status].tone}>{STATUS[p.status].label}</Badge>
              <span className="font-medium text-fg">Version {p.version}</span>
              <span className="text-fg-subtle">
                {p.published_at
                  ? `published ${formatDateTime(p.published_at)}`
                  : p.scheduled_at
                    ? `for ${formatDateTime(p.scheduled_at)}`
                    : formatDateTime(p.created_at)}
              </span>
              {p.withdraw_reason && <span className="w-full text-fg-muted">“{p.withdraw_reason}”</span>}
            </li>
          ))}
        </ol>
      )}

      <ConfirmDialog
        open={action === "now"}
        onOpenChange={(v) => !v && setAction(null)}
        title={`Publish to ${formatNumber(students)} students now?`}
        description="Each student sees their own result straight away. You can withdraw later, with a reason, but students may already have seen it."
        confirmLabel="Publish now"
        loading={run.isPending}
        onConfirm={() => run.mutate({ kind: "now" })}
      />
      <ConfirmDialog
        open={action === "withdraw"}
        onOpenChange={(v) => !v && setAction(null)}
        title="Withdraw these results?"
        description="Students stop seeing them at once. The reason is kept in the audit log."
        confirmLabel="Withdraw results"
        variant="danger"
        requireReason
        loading={run.isPending}
        onConfirm={(reason) => live && run.mutate({ kind: "withdraw", reason, id: live.id })}
      />
      <ConfirmDialog
        open={action === "cancel"}
        onOpenChange={(v) => !v && setAction(null)}
        title="Cancel the scheduled publication?"
        description="Nothing goes live. You can publish or schedule again whenever you're ready."
        confirmLabel="Cancel schedule"
        cancelLabel="Keep it"
        loading={run.isPending}
        onConfirm={() => scheduled && run.mutate({ kind: "cancel", id: scheduled.id })}
      />
      <Dialog open={scheduling} onOpenChange={setScheduling}>
        <DialogContent
          title="Schedule publication"
          description="Results go live at this time on their own — your team doesn't need to be online."
          footer={
            <>
              <Button variant="secondary" onClick={() => setScheduling(false)}>
                Cancel
              </Button>
              <Button
                leadingIcon={<Eye />}
                loading={run.isPending}
                disabled={!at}
                onClick={() => run.mutate({ kind: "schedule" })}
              >
                Schedule
              </Button>
            </>
          }
        >
          <Field label="Go live at" description="Your browser's time zone. At least a few minutes from now.">
            <Input type="datetime-local" value={at} min={minAt} onChange={(e) => setAt(e.target.value)} />
          </Field>
        </DialogContent>
      </Dialog>
    </Section>
  );
}

/** Marksheet PDFs of the current publication: rendered by the worker right after publishing (or ahead of a
 * scheduled release), each with its own verification QR code. */
function Marksheets({
  examId,
  pub,
  canRetry,
  onRetried,
}: {
  examId: string;
  pub: Publication;
  canRetry: boolean;
  onRetried: () => void;
}) {
  const retry = useMutation({
    mutationFn: () => api.post<{ queued: number }>(`${pubsUrl(examId)}/${pub.id}/marksheets/retry`),
    onSuccess: (r) => {
      toast.success(`Trying ${formatNumber(r.queued)} marksheets again`);
      onRetried();
    },
    onError: toastError,
  });
  const m = pub.marksheets;
  if (!m || m.total === 0) return null;
  if (m.pending > 0) {
    const pct = ((m.rendered + m.failed) / m.total) * 100;
    return (
      <div className="mt-4 flex flex-col gap-2" aria-live="polite">
        <div className="flex items-baseline justify-between gap-3 text-[13px]">
          <span className="font-medium text-fg">Preparing marksheet PDFs…</span>
          <span className="tabular-nums text-fg-subtle">
            {formatNumber(m.rendered)} of {formatNumber(m.total)}
          </span>
        </div>
        <ProgressBar value={pct} label="Marksheets prepared" />
        <p className="text-[12px] text-fg-subtle">
          This runs in the background — you can leave this page. Each marksheet carries its own QR code for
          verification.
        </p>
      </div>
    );
  }
  if (m.failed > 0) {
    return (
      <Callout
        tone="warning"
        className="mt-4"
        title={`${formatNumber(m.failed)} of ${formatNumber(m.total)} marksheets couldn't be prepared`}
      >
        <div className="flex flex-wrap items-center gap-3">
          <span>Those students still see their result online; only the PDF is missing.</span>
          {canRetry && (
            <Button
              size="sm"
              variant="secondary"
              leadingIcon={<RefreshCw />}
              loading={retry.isPending}
              onClick={() => retry.mutate()}
            >
              Try again
            </Button>
          )}
        </div>
      </Callout>
    );
  }
  return (
    <p className="mt-4 flex items-center gap-2 text-[13px] text-fg-muted">
      <FileCheck2 className="size-4 text-success" aria-hidden />
      All {formatNumber(m.total)} marksheets are ready to download, each with a QR code anyone can verify.
    </p>
  );
}
