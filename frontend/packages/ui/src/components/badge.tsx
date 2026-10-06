import type { HTMLAttributes, ReactNode } from "react";

import { cn } from "../lib/cn";

const tones = {
  neutral: "bg-surface-2 text-fg-muted ring-border",
  brand: "bg-brand-soft text-brand-ink ring-brand-muted",
  success: "bg-success-soft text-success ring-success-border",
  warning: "bg-warning-soft text-warning ring-warning-border",
  danger: "bg-danger-soft text-danger ring-danger-border",
  info: "bg-info-soft text-info ring-info-border",
} as const;

export type Tone = keyof typeof tones;

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: Tone;
  dot?: boolean;
  icon?: ReactNode;
}

export function Badge({ tone = "neutral", dot, icon, className, children, ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex h-[22px] items-center gap-1.5 whitespace-nowrap rounded-full px-2 text-xs font-medium ring-1 ring-inset [&_svg]:size-3",
        tones[tone],
        className,
      )}
      {...props}
    >
      {dot && <span className="size-1.5 rounded-full bg-current" aria-hidden />}
      {icon}
      {children}
    </span>
  );
}
