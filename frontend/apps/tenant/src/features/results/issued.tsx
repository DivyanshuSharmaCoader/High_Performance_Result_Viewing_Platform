import { api, ApiError, type Marksheet, type Publication } from "@scorecode/api-client";
import { Button, ConfirmDialog, toast } from "@scorecode/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, ShieldOff } from "lucide-react";
import { useState } from "react";

import { useReauth } from "../../components/reauth";
import { toastError } from "../../lib/forms";
import { goTo } from "../../lib/navigate";
import { useCan } from "../../lib/session";

/** The live publication of an exam, if any (shared with the publication panel's query). */
export const useLivePublication = (examId: string) =>
  useQuery({
    queryKey: ["publications", examId],
    queryFn: () => api.get<Publication[]>(`/api/v1/admin/exams/${examId}/publications`),
    select: (list) => list.find((p) => p.status === "published") ?? null,
  });

const STATUS: Record<Marksheet["status"], string> = {
  rendered: "Ready. It's the PDF the student downloads, with its verification QR code.",
  pending: "Being prepared…",
  failed: "Couldn't be prepared. Use “Try again” in the Publication section.",
};

/** One student's issued marksheet: download it, or revoke its verification (fraud or a serious error). */
export function IssuedMarksheet({
  examId,
  publication,
  studentId,
}: {
  examId: string;
  publication: Publication;
  studentId: string;
}) {
  const qc = useQueryClient();
  const withReauth = useReauth();
  const canManage = useCan("publications.manage");
  const base = `/api/v1/admin/exams/${examId}/publications/${publication.id}`;
  const key = ["publications", examId, publication.id, "marksheet", studentId];
  const q = useQuery({
    queryKey: key,
    queryFn: () => api.get<Marksheet>(`${base}/marksheets/${studentId}`),
    refetchInterval: (s) => (s.state.data?.status === "pending" ? 4000 : false),
  });
  const [busy, setBusy] = useState(false);
  const [revoking, setRevoking] = useState(false);
  const revoke = useMutation({
    mutationFn: (reason: string) =>
      withReauth(() => api.post(`${base}/verification/${studentId}/revoke`, { reason })),
    onSuccess: () => {
      setRevoking(false);
      toast.success("Verification revoked. Scanning this marksheet now shows “Revoked”.");
    },
    onError: (e) => {
      setRevoking(false);
      if (!(e instanceof ApiError && e.code === "reauth-cancelled")) toastError(e);
    },
  });
  const download = async () => {
    setBusy(true);
    try {
      const fresh = await qc.fetchQuery({
        queryKey: key,
        queryFn: () => api.get<Marksheet>(`${base}/marksheets/${studentId}`),
        staleTime: 0,
      });
      if (fresh.url) goTo(fresh.url);
    } catch (e) {
      toastError(e);
    } finally {
      setBusy(false);
    }
  };
  if (!q.data) return null;
  return (
    <section aria-label="Issued marksheet" className="mt-5 rounded-xl border border-border p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-fg">Issued marksheet · version {publication.version}</h3>
          <p className="text-[13px] text-fg-muted">{STATUS[q.data.status]}</p>
        </div>
        <Button
          size="sm"
          variant="secondary"
          leadingIcon={<Download />}
          loading={busy}
          disabled={q.data.status !== "rendered"}
          onClick={() => void download()}
        >
          Download PDF
        </Button>
      </div>
      {q.data.verification && (
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-border pt-3">
          <p className="text-[12px] text-fg-subtle">
            Verification code <span className="font-mono text-fg-muted">{q.data.verification.code}</span>
          </p>
          {canManage && (
            <Button size="sm" variant="ghost" leadingIcon={<ShieldOff />} onClick={() => setRevoking(true)}>
              Revoke verification…
            </Button>
          )}
        </div>
      )}
      <ConfirmDialog
        open={revoking}
        onOpenChange={setRevoking}
        title="Revoke this marksheet's verification?"
        description="Anyone who scans its QR code will see “Revoked”. This can't be undone; to correct a result, publish a revised version instead. The reason stays private, in the audit log."
        confirmLabel="Revoke verification"
        variant="danger"
        requireReason
        loading={revoke.isPending}
        onConfirm={(reason) => revoke.mutate(reason)}
      />
    </section>
  );
}
