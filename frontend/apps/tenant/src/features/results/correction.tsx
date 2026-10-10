import {
  api,
  ApiError,
  type CorrectionChange,
  type CorrectionPreview,
  type CorrectionState,
  type Exam,
} from "@scorecode/api-client";
import {
  Badge,
  Button,
  Callout,
  ConfirmDialog,
  Section,
  TBody,
  THead,
  Table,
  TableContainer,
  Td,
  Th,
  formatNumber,
  formatRelative,
  noun,
  toast,
} from "@scorecode/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, PenLine, Undo2 } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import { useReauth } from "../../components/reauth";
import { toastError } from "../../lib/forms";
import { useCan } from "../../lib/session";
import { OUTCOME } from "./api";

export const correctionUrl = (examId: string) => `/api/v1/admin/exams/${examId}/correction`;

/** Who the corrected results change, against the live version. Refetched when a new run completes. */
export function useCorrectionPreview(examId: string, runId: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: ["correction-preview", examId, runId ?? "none"],
    queryFn: () => api.get<CorrectionPreview>(`${correctionUrl(examId)}/preview`),
    enabled,
  });
}

export function useRefreshAfterCorrection(examId: string) {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: ["exams"] });
    void qc.invalidateQueries({ queryKey: ["results", examId] });
    void qc.invalidateQueries({ queryKey: ["publications", examId] });
    void qc.invalidateQueries({ queryKey: ["correction-preview", examId] });
    void qc.invalidateQueries({ queryKey: ["marking"] });
  };
}

function summary(s: CorrectionChange["before"]): string {
  if (!s) return "—";
  const parts: (string | null)[] = [OUTCOME[s.outcome as keyof typeof OUTCOME]?.label ?? s.outcome];
  if (s.percentage != null) parts.push(`${s.percentage}%`);
  if (s.grade) parts.push(s.grade);
  if (s.sgpa != null) parts.push(`SGPA ${s.sgpa}`);
  return parts.filter(Boolean).join(" · ");
}

/** Shown while a correction of published results is in progress (P18.3). */
export function CorrectionPanel({
  exam,
  runId,
  hasCorrectedRun,
}: {
  exam: Exam;
  runId: string | undefined;
  hasCorrectedRun: boolean;
}) {
  const canManage = useCan("publications.manage");
  const refresh = useRefreshAfterCorrection(exam.id);
  const [confirming, setConfirming] = useState(false);
  const preview = useCorrectionPreview(exam.id, runId, true);
  const cancel = useMutation({
    mutationFn: () => api.delete<CorrectionState>(correctionUrl(exam.id)),
    onSuccess: () => {
      setConfirming(false);
      refresh();
      toast.success("Correction cancelled — the live results are unchanged");
    },
    onError: (e) => {
      setConfirming(false);
      toastError(e);
    },
  });
  const p = preview.data;
  return (
    <Section
      title="Correcting published results"
      actions={
        canManage && (
          <Button size="sm" variant="secondary" leadingIcon={<Undo2 />} onClick={() => setConfirming(true)}>
            Cancel correction
          </Button>
        )
      }
    >
      <Callout
        tone="warning"
        title={p ? `Students still see version ${p.live_version}` : "Students still see the live version"}
      >
        <p>
          Nothing changes for students until you publish the corrected results. Started{" "}
          {formatRelative(exam.correction_started_at)}
          {exam.correction_reason && <> — “{exam.correction_reason}”</>}.
        </p>
        <ol className="mt-2 list-decimal pl-5 text-[13px]">
          <li>
            Change the marks in{" "}
            <Link to={`/admin/exams/${exam.id}`} className="font-medium text-brand-ink hover:underline">
              the exam&apos;s papers
            </Link>{" "}
            (or upload a corrected file).
          </li>
          <li>Process and approve the results below.</li>
          <li>Publish the corrected results. Only students whose result changed are told.</li>
        </ol>
      </Callout>

      {hasCorrectedRun && p && (
        <div className="mt-4 flex flex-col gap-3">
          <p className="text-sm text-fg">
            {p.changed === 0 ? (
              "No student's result changes compared with the live version."
            ) : (
              <>
                <span className="font-semibold">
                  {formatNumber(p.changed)} of {formatNumber(p.students)} {noun(p.students, "student")}
                </span>{" "}
                {p.changed === 1 ? "has a different result" : "have a different result"} from the live
                version.
              </>
            )}
          </p>
          {p.changes.length > 0 && (
            <TableContainer>
              <Table aria-label="Students whose result changes">
                <THead>
                  <tr>
                    <Th>Student</Th>
                    <Th>Live now</Th>
                    <Th className="w-6" aria-label="becomes" />
                    <Th>After the correction</Th>
                  </tr>
                </THead>
                <TBody>
                  {p.changes.map((c) => (
                    <tr key={c.enrollment_no}>
                      <Td>
                        <span className="font-medium text-fg">{c.full_name}</span>{" "}
                        <span className="tabular text-fg-subtle">{c.enrollment_no}</span>
                      </Td>
                      <Td className="text-fg-muted">{summary(c.before)}</Td>
                      <Td aria-hidden>
                        <ArrowRight className="size-4 text-fg-subtle" />
                      </Td>
                      <Td>
                        {c.after ? (
                          summary(c.after)
                        ) : (
                          <Badge tone="warning">Not in the corrected results</Badge>
                        )}
                      </Td>
                    </tr>
                  ))}
                </TBody>
              </Table>
            </TableContainer>
          )}
          {p.changed > p.changes.length && (
            <p className="text-[13px] text-fg-subtle">
              Showing the first {formatNumber(p.changes.length)}. The audit log records the full count.
            </p>
          )}
        </div>
      )}

      <ConfirmDialog
        open={confirming}
        onOpenChange={(v) => !v && setConfirming(false)}
        title="Cancel this correction?"
        description="The live results stay exactly as they are. This works only if no mark was changed; otherwise change the marks back first, or publish the corrected results."
        confirmLabel="Cancel correction"
        cancelLabel="Keep correcting"
        loading={cancel.isPending}
        onConfirm={() => cancel.mutate()}
      />
    </Section>
  );
}

/** "Correct results…" on a published exam: a reason, then re-authentication. */
export function StartCorrectionButton({ examId, liveVersion }: { examId: string; liveVersion: number }) {
  const refresh = useRefreshAfterCorrection(examId);
  const withReauth = useReauth();
  const [open, setOpen] = useState(false);
  const start = useMutation({
    mutationFn: (reason: string) =>
      withReauth(() => api.post<CorrectionState>(correctionUrl(examId), { reason })),
    onSuccess: () => {
      setOpen(false);
      refresh();
      toast.success("Correction started — change the marks, then process again");
    },
    onError: (e) => {
      setOpen(false);
      if (!(e instanceof ApiError && e.code === "reauth-cancelled")) toastError(e);
    },
  });
  return (
    <>
      <Button size="sm" variant="secondary" leadingIcon={<PenLine />} onClick={() => setOpen(true)}>
        Correct results…
      </Button>
      <ConfirmDialog
        open={open}
        onOpenChange={setOpen}
        title="Correct the published results?"
        description={`Students keep seeing version ${liveVersion} while you change marks, process and approve again. Publishing the corrected results replaces it, and only students whose result changed are told.`}
        confirmLabel="Start correction"
        requireReason
        reasonLabel="What needs correcting (recorded in the audit log)"
        loading={start.isPending}
        onConfirm={(reason) => start.mutate(reason)}
      />
    </>
  );
}
