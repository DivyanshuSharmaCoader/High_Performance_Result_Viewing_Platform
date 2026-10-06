import { Slot } from "radix-ui";
import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";

import { cn } from "../lib/cn";
import { Spinner } from "./spinner";

const base =
  "relative inline-flex select-none items-center justify-center gap-2 whitespace-nowrap font-medium " +
  "transition-[background-color,border-color,color,box-shadow,opacity] duration-150 " +
  "disabled:pointer-events-none disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 " +
  "[&_svg]:shrink-0";

const variants = {
  primary: "bg-brand text-brand-fg shadow-xs hover:bg-brand-hover focus-visible:outline-brand",
  secondary:
    "bg-surface text-fg border border-border-strong shadow-xs hover:bg-surface-2 focus-visible:outline-brand",
  ghost: "text-fg-muted hover:bg-surface-2 hover:text-fg focus-visible:outline-brand",
  danger: "bg-danger-solid text-white shadow-xs hover:opacity-90 focus-visible:outline-danger-solid",
  "danger-outline":
    "border border-danger-border bg-surface text-danger hover:bg-danger-soft focus-visible:outline-danger-solid",
  link: "text-brand-ink underline-offset-4 hover:underline px-0 h-auto",
} as const;

const sizes = {
  sm: "h-8 rounded-md px-3 text-[13px] [&_svg]:size-3.5",
  md: "h-9 rounded-md px-3.5 text-sm [&_svg]:size-4",
  lg: "h-11 rounded-lg px-5 text-[15px] [&_svg]:size-[18px]",
  icon: "size-9 rounded-md [&_svg]:size-4",
  "icon-sm": "size-8 rounded-md [&_svg]:size-4",
} as const;

export type ButtonVariant = keyof typeof variants;
export type ButtonSize = keyof typeof sizes;

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  asChild?: boolean;
  leadingIcon?: ReactNode;
  trailingIcon?: ReactNode;
}

export function buttonClasses(
  variant: ButtonVariant = "primary",
  size: ButtonSize = "md",
  className?: string,
) {
  return cn(base, variants[variant], variant === "link" ? "" : sizes[size], className);
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = "primary",
    size = "md",
    loading = false,
    asChild = false,
    leadingIcon,
    trailingIcon,
    className,
    children,
    disabled,
    type,
    ...props
  },
  ref,
) {
  const classes = buttonClasses(variant, size, className);
  if (asChild) {
    return (
      <Slot.Root ref={ref} className={classes} {...props}>
        {children}
      </Slot.Root>
    );
  }
  return (
    <button
      ref={ref}
      type={type ?? "button"}
      className={classes}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...props}
    >
      {loading ? <Spinner className="size-4" label="Working" /> : leadingIcon}
      {children}
      {!loading && trailingIcon}
    </button>
  );
});
