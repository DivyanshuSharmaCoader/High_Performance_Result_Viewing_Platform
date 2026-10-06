import { AlertCircle } from "lucide-react";
import { cloneElement, isValidElement, useId, type ReactElement, type ReactNode } from "react";

import { cn } from "../lib/cn";

export interface FieldProps {
  label: ReactNode;
  children: ReactElement<Record<string, unknown>>;
  description?: ReactNode;
  error?: string | undefined;
  required?: boolean;
  optional?: boolean;
  className?: string;
  /** Extra content on the label row (e.g. "Forgot password?" link). */
  aside?: ReactNode;
}

/** Label + control + help text + error, wired for screen readers (aria-describedby / aria-invalid). */
export function Field({
  label,
  children,
  description,
  error,
  required,
  optional,
  className,
  aside,
}: FieldProps) {
  const id = useId();
  const controlId = (children.props.id as string | undefined) ?? `${id}-control`;
  const descId = description ? `${id}-desc` : undefined;
  const errId = error ? `${id}-err` : undefined;
  const describedBy = [descId, errId].filter(Boolean).join(" ") || undefined;
  const control = isValidElement(children)
    ? cloneElement(children, {
        id: controlId,
        "aria-describedby": describedBy,
        "aria-invalid": error ? true : undefined,
        "aria-required": required || undefined,
      })
    : children;
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <div className="flex items-baseline justify-between gap-3">
        <label htmlFor={controlId} className="text-[13px] font-medium text-fg">
          {label}
          {required && (
            <span className="ml-0.5 text-danger" aria-hidden>
              *
            </span>
          )}
          {optional && (
            <>
              {" "}
              <span className="ml-1 font-normal text-fg-subtle">(optional)</span>
            </>
          )}
        </label>
        {aside}
      </div>
      {control}
      {description && !error && (
        <p id={descId} className="text-[13px] leading-5 text-fg-subtle">
          {description}
        </p>
      )}
      {error && (
        <p id={errId} role="alert" className="flex items-start gap-1.5 text-[13px] leading-5 text-danger">
          <AlertCircle className="mt-0.5 size-3.5 shrink-0" aria-hidden />
          {error}
        </p>
      )}
    </div>
  );
}
