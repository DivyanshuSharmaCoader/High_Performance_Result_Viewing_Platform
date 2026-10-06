import { ApiError } from "@scorecode/api-client";
import { Button, Callout, Dialog, DialogContent } from "@scorecode/ui";
import type { ReactNode } from "react";

import { PlanLimitCallout } from "./limit-callout";

/**
 * Standard create/edit dialog: a form body, Cancel/Submit footer, and a form-level error area that knows
 * how to present plan limits (402) and conflicts. Field-level errors are shown by the form itself.
 */
export function FormDialog({
  open,
  onOpenChange,
  title,
  description,
  submitLabel,
  submitting,
  error,
  formId,
  children,
  size = "md",
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  description?: ReactNode;
  submitLabel: string;
  submitting: boolean;
  error: unknown;
  formId: string;
  children: ReactNode;
  size?: "sm" | "md" | "lg";
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        title={title}
        description={description}
        size={size}
        dismissible={!submitting}
        footer={
          <>
            <Button variant="secondary" onClick={() => onOpenChange(false)} disabled={submitting}>
              Cancel
            </Button>
            <Button type="submit" form={formId} loading={submitting}>
              {submitLabel}
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-5">
          {error instanceof ApiError && error.status === 402 ? (
            <PlanLimitCallout error={error} />
          ) : error instanceof ApiError && !error.field ? (
            <Callout tone="danger">{error.detail}</Callout>
          ) : null}
          {children}
        </div>
      </DialogContent>
    </Dialog>
  );
}
