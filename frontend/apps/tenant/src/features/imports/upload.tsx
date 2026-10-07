import { ApiError } from "@scorecode/api-client";
import { Button, Dialog, DialogContent, FileDropzone, Spinner, toast } from "@scorecode/ui";
import { useMutation } from "@tanstack/react-query";
import { FileDown } from "lucide-react";
import type { ReactNode } from "react";
import { useNavigate } from "react-router";

import { toastError } from "../../lib/forms";
import { templateUrl, uploadImport, useImportsHome } from "./api";

export const MAX_BYTES = 10 * 1024 * 1024;
export const ACCEPT = ".xlsx,.csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv";

type Fields = Record<string, string | undefined>;

/** Upload, then open the review page. The same bytes resume the open import; committed bytes are refused. */
export function useUploadImport(onUploaded?: () => void) {
  const navigate = useNavigate();
  const { base } = useImportsHome();
  return useMutation({
    mutationFn: ({ file, fields }: { file: File; fields: Fields }) => uploadImport(file, fields),
    onSuccess: (job) => {
      onUploaded?.();
      if (job.resumed) toast.info("You've uploaded this file before — continuing where you left off.");
      void navigate(`${base}/${job.id}`);
    },
    onError: (e) => {
      if (e instanceof ApiError && e.status === 409 && typeof e.body.import_id === "string") {
        const id = e.body.import_id;
        toast.error("Already imported", {
          description: e.detail,
          action: { label: "View", onClick: () => void navigate(`${base}/${id}`) },
        });
        return;
      }
      toastError(e);
    },
  });
}

export function UploadZone({
  uploading,
  onFile,
  hint,
  disabled,
}: {
  uploading: string | null;
  onFile: (file: File) => void;
  hint?: ReactNode;
  disabled?: boolean;
}) {
  if (uploading !== null) {
    return (
      <div
        className="flex items-center justify-center gap-3 rounded-xl border-2 border-dashed border-border-strong px-6 py-10 text-sm text-fg-muted"
        role="status"
      >
        <Spinner className="size-5" label="" /> Uploading {uploading}…
      </div>
    );
  }
  return (
    <FileDropzone accept={ACCEPT} maxBytes={MAX_BYTES} onFile={onFile} hint={hint} disabled={disabled} />
  );
}

/** "Import from Excel" for one paper: download the roster pre-filled for a cohort, fill it, upload it. */
export function MarksImportDialog({
  examId,
  paperId,
  cohortId,
  title,
  onClose,
}: {
  examId: string;
  paperId: string;
  cohortId?: string;
  title: string;
  onClose: () => void;
}) {
  const upload = useUploadImport(onClose);
  return (
    <Dialog open onOpenChange={(o) => !o && !upload.isPending && onClose()}>
      <DialogContent
        title={title}
        description="Every row is checked first. Nothing is saved until you've reviewed it and confirmed."
      >
        <ol className="mb-4 flex flex-col gap-2 text-[13px] text-fg-muted">
          <li>
            <span className="font-semibold text-fg">1.</span> Download the template — it already lists the
            students, with a column for each component.
          </li>
          <li>
            <span className="font-semibold text-fg">2.</span> Fill in marks, or <strong>AB</strong>,{" "}
            <strong>EX</strong>, <strong>MP</strong>, <strong>WH</strong>. Blank cells leave saved marks
            alone.
          </li>
          <li>
            <span className="font-semibold text-fg">3.</span> Upload it here. Your own spreadsheet works too,
            as long as it has an enrollment number column.
          </li>
        </ol>
        <Button variant="secondary" size="sm" className="mb-4" asChild>
          <a href={templateUrl("marks", { exam_id: examId, paper_id: paperId, cohort_id: cohortId })}>
            <FileDown aria-hidden /> Download template
          </a>
        </Button>
        <UploadZone
          uploading={upload.isPending ? (upload.variables?.file.name ?? "") : null}
          onFile={(file) =>
            upload.mutate({ file, fields: { kind: "marks", exam_id: examId, paper_id: paperId } })
          }
        />
      </DialogContent>
    </Dialog>
  );
}
