import { Dialog as D } from "radix-ui";
import { X } from "lucide-react";
import { useState, type ReactNode } from "react";

import { cn } from "../lib/cn";
import { Button, type ButtonVariant } from "./button";
import { Field } from "./field";
import { Input, Textarea } from "./input";

export const Dialog = D.Root;
export const DialogTrigger = D.Trigger;
export const DialogClose = D.Close;

export interface DialogContentProps {
  title: ReactNode;
  description?: ReactNode;
  children?: ReactNode;
  footer?: ReactNode;
  size?: "sm" | "md" | "lg" | "xl";
  className?: string;
  /** Prevent closing by clicking outside (e.g. while a request is in flight). */
  dismissible?: boolean;
}

const widths = { sm: "max-w-md", md: "max-w-lg", lg: "max-w-2xl", xl: "max-w-4xl" };

export function DialogContent({
  title,
  description,
  children,
  footer,
  size = "md",
  className,
  dismissible = true,
}: DialogContentProps) {
  return (
    <D.Portal>
      <D.Overlay className="fixed inset-0 z-50 bg-overlay backdrop-blur-[2px] data-[state=open]:animate-fade-in" />
      <D.Content
        onPointerDownOutside={(e) => !dismissible && e.preventDefault()}
        onEscapeKeyDown={(e) => !dismissible && e.preventDefault()}
        className={cn(
          "fixed left-1/2 top-1/2 z-50 flex max-h-[min(90dvh,860px)] w-[calc(100vw-2rem)] -translate-x-1/2 -translate-y-1/2 flex-col",
          "rounded-xl border border-border bg-surface shadow-xl focus:outline-none data-[state=open]:animate-scale-in",
          widths[size],
          className,
        )}
      >
        <div className="flex items-start justify-between gap-4 border-b border-border px-6 pb-4 pt-5">
          <div className="min-w-0">
            <D.Title className="text-base font-semibold text-fg">{title}</D.Title>
            {description ? (
              <D.Description className="mt-1 text-sm leading-6 text-fg-subtle">{description}</D.Description>
            ) : (
              <D.Description className="sr-only">
                {typeof title === "string" ? title : "Dialog"}
              </D.Description>
            )}
          </div>
          {dismissible && (
            <D.Close
              className="-mr-2 -mt-1 rounded-md p-1.5 text-fg-subtle hover:bg-surface-2 hover:text-fg"
              aria-label="Close"
            >
              <X className="size-4" />
            </D.Close>
          )}
        </div>
        {children && <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">{children}</div>}
        {footer && (
          <div className="flex flex-col-reverse gap-2 border-t border-border bg-surface-2/60 px-6 py-3.5 sm:flex-row sm:justify-end rounded-b-xl">
            {footer}
          </div>
        )}
      </D.Content>
    </D.Portal>
  );
}

export interface ConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  description?: ReactNode;
  children?: ReactNode;
  confirmLabel: string;
  cancelLabel?: string;
  variant?: ButtonVariant;
  /** Require a reason (stored in the audit log) — docs/09 ConfirmWithReasonDialog. */
  requireReason?: boolean;
  reasonLabel?: string;
  /** Require typing this exact text to enable the confirm button (destructive actions). */
  confirmText?: string;
  loading?: boolean;
  onConfirm: (reason: string) => void | Promise<void>;
}

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  children,
  confirmLabel,
  cancelLabel = "Cancel",
  variant = "primary",
  requireReason,
  reasonLabel = "Reason (recorded in the audit log)",
  confirmText,
  loading,
  onConfirm,
}: ConfirmDialogProps) {
  const [reason, setReason] = useState("");
  const [typed, setTyped] = useState("");
  const reasonOk = !requireReason || reason.trim().length >= 3;
  const typedOk = !confirmText || typed.trim() === confirmText;
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) {
          setReason("");
          setTyped("");
        }
        onOpenChange(next);
      }}
    >
      <DialogContent
        title={title}
        description={description}
        size="sm"
        dismissible={!loading}
        footer={
          <>
            <Button variant="secondary" onClick={() => onOpenChange(false)} disabled={loading}>
              {cancelLabel}
            </Button>
            <Button
              variant={variant}
              loading={loading}
              disabled={!reasonOk || !typedOk}
              onClick={() => void onConfirm(reason.trim())}
            >
              {confirmLabel}
            </Button>
          </>
        }
      >
        {(children || requireReason || confirmText) && (
          <div className="flex flex-col gap-4">
            {children}
            {requireReason && (
              <Field label={reasonLabel} required>
                <Textarea
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  rows={3}
                  maxLength={500}
                  autoFocus
                />
              </Field>
            )}
            {confirmText && (
              <Field
                label={
                  <>
                    Type <span className="font-mono">{confirmText}</span> to confirm
                  </>
                }
              >
                <Input value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" />
              </Field>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
