import { Search, X } from "lucide-react";
import {
  forwardRef,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";

import { cn } from "../lib/cn";

export const controlClasses =
  "w-full rounded-md border border-border-strong bg-surface text-fg shadow-xs " +
  "placeholder:text-fg-disabled transition-[border-color,box-shadow] duration-150 " +
  "hover:border-fg-disabled focus:outline-none focus-visible:outline-none " +
  "focus:border-brand focus:ring-[3px] focus:ring-brand/15 " +
  "disabled:cursor-not-allowed disabled:bg-surface-2 disabled:text-fg-subtle " +
  "aria-[invalid=true]:border-danger-solid aria-[invalid=true]:focus:ring-danger-solid/15";

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  leading?: ReactNode;
  trailing?: ReactNode;
  /** Sizing classes for the wrapper when leading/trailing adornments are used. */
  containerClassName?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { className, leading, trailing, containerClassName, ...props },
  ref,
) {
  if (!leading && !trailing) {
    return <input ref={ref} className={cn(controlClasses, "h-9 px-3 text-sm", className)} {...props} />;
  }
  return (
    <div className={cn("relative", containerClassName)}>
      {leading && (
        <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-fg-subtle [&_svg]:size-4">
          {leading}
        </span>
      )}
      <input
        ref={ref}
        className={cn(controlClasses, "h-9 px-3 text-sm", leading && "pl-9", trailing && "pr-9", className)}
        {...props}
      />
      {trailing && <span className="absolute inset-y-0 right-2 flex items-center">{trailing}</span>}
    </div>
  );
});

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  function Textarea({ className, rows = 3, ...props }, ref) {
    return (
      <textarea
        ref={ref}
        rows={rows}
        className={cn(controlClasses, "px-3 py-2 text-sm leading-6", className)}
        {...props}
      />
    );
  },
);

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(function Select(
  { className, children, ...props },
  ref,
) {
  return (
    <select
      ref={ref}
      className={cn(
        controlClasses,
        "h-9 appearance-none bg-[length:16px] bg-[right_10px_center] bg-no-repeat pl-3 pr-9 text-sm",
        "bg-[url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%23667085' stroke-width='2'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' d='m6 9 6 6 6-6'/%3E%3C/svg%3E\")]",
        className,
      )}
      {...props}
    >
      {children}
    </select>
  );
});

export interface SearchInputProps extends Omit<InputProps, "onChange" | "value"> {
  value: string;
  onValueChange: (value: string) => void;
}

export function SearchInput({
  value,
  onValueChange,
  placeholder = "Search",
  className,
  ...props
}: SearchInputProps) {
  return (
    <Input
      type="search"
      role="searchbox"
      value={value}
      placeholder={placeholder}
      onChange={(e) => onValueChange(e.target.value)}
      leading={<Search aria-hidden />}
      trailing={
        value ? (
          <button
            type="button"
            onClick={() => onValueChange("")}
            className="rounded p-1 text-fg-subtle hover:bg-surface-2 hover:text-fg"
            aria-label="Clear search"
          >
            <X className="size-3.5" />
          </button>
        ) : null
      }
      className="[&::-webkit-search-cancel-button]:hidden"
      containerClassName={cn("w-full", className)}
      {...props}
    />
  );
}
