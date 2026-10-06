import { Toaster as Sonner, toast } from "sonner";

export { toast };

export function Toaster() {
  return (
    <Sonner
      position="bottom-right"
      closeButton
      duration={4500}
      toastOptions={{
        classNames: {
          toast:
            "!rounded-lg !border !border-border !bg-surface !text-fg !shadow-lg !font-sans !text-sm !gap-2.5",
          description: "!text-fg-subtle",
          actionButton: "!bg-brand !text-brand-fg",
          closeButton: "!bg-surface !border-border !text-fg-subtle",
          success: "[&_[data-icon]]:!text-success",
          error: "[&_[data-icon]]:!text-danger-solid",
          warning: "[&_[data-icon]]:!text-warning",
        },
      }}
    />
  );
}
